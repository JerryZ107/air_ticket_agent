from __future__ import annotations as _annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import llm_config  # noqa: F401 — 加载 .env 并配置 DeepSeek/OpenAI 客户端

from chatkit.server import StreamingResult
from chatkit.types import (
    AssistantMessageItem,
    InferenceOptions,
    ThreadItemDoneEvent,
    UserMessageItem,
    UserMessageTextContent,
)
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from auth.dependencies import get_current_user, get_token_from_request
from db.observability import obs_writer
from db.pool import close_pool, init_pool
from db.repository.auth import UserRecord, auth_repo
from pipeline.request_context import RequestContext, clear_request_context, get_request_context, set_request_context
from rag.indexer import embed_missing_chunks, index_manuals

from airline.agents import (
    booking_cancellation_agent,
    faq_agent,
    flight_information_agent,
    refunds_compensation_agent,
    seat_special_services_agent,
    triage_agent,
)
from airline.mcp_integration import (
    USE_MCP_TOOLS,
    attach_mcp_server,
    create_airline_mcp_server,
)
from airline.context import (
    AirlineAgentChatContext,
    AirlineAgentContext,
    create_initial_context,
    public_context,
)
from server import AirlineServer

SESSION_COOKIE = "session_token"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    mcp_server = None
    try:
        n = await index_manuals()
        print(f"RAG indexed {n} chunks from docs/manual")
        try:
            emb = await embed_missing_chunks()
            if emb:
                print(f"RAG embeddings updated for {emb} chunks")
        except Exception as exc:
            print(f"RAG embeddings skipped: {exc}")
    except Exception as exc:
        print(f"RAG index skipped: {exc}")

    if USE_MCP_TOOLS:
        if not os.getenv("AIRLINE_SESSION_USERNAME"):
            print(
                "WARNING: AIRLINE_USE_MCP_TOOLS=true 但未设置 AIRLINE_SESSION_USERNAME，"
                "MCP 写操作将因缺少会话用户而失败；多用户部署请改为 AIRLINE_USE_MCP_TOOLS=false"
            )
        try:
            mcp_server = create_airline_mcp_server()
            await mcp_server.connect()
            attach_mcp_server(
                mcp_server,
                [
                    booking_cancellation_agent,
                    seat_special_services_agent,
                ],
            )
            app.state.mcp_server = mcp_server
            print("MCP airline-booking server connected (stdio subprocess)")
        except Exception as exc:
            print(f"MCP connect skipped: {exc}")

    yield

    if mcp_server is not None:
        await mcp_server.cleanup()
    await close_pool()


app = FastAPI(lifespan=lifespan)

# Disable tracing for zero data retention orgs
os.environ.setdefault("OPENAI_TRACING_DISABLED", "1")

# CORS configuration (adjust as needed for deployment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_server = AirlineServer()


def get_server() -> AirlineServer:
    return chat_server


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    thread_id: str
    reply: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str | None
    role: str


class MeResponse(BaseModel):
    username: str
    display_name: str | None
    role: str


def _http_ctx(request: Request, user: UserRecord, thread_id: str | None = None) -> dict[str, Any]:
    trace_id = uuid4()
    rctx = RequestContext(trace_id=trace_id, user_id=user.id, username=user.username, role=user.role, thread_id=thread_id)
    set_request_context(rctx)
    return {"request": request, "user": user, "trace_id": str(trace_id)}


async def _start_trace(ctx: dict[str, Any], path: str) -> None:
    user: UserRecord = ctx["user"]
    trace_id = get_request_context().trace_id
    await obs_writer.start_trace(trace_id, user.id, ctx.get("thread_id"), path)


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    from auth.rate_limit import is_locked, register_failure, reset

    client_ip = request.client.host if request.client else None
    if is_locked(body.username, client_ip):
        raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")
    user = await auth_repo.verify_login(body.username.strip(), body.password)
    if user is None:
        register_failure(body.username, client_ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    reset(body.username, client_ip)
    trace_id = uuid4()
    rctx = RequestContext(
        trace_id=trace_id,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )
    set_request_context(rctx)
    await obs_writer.start_trace(trace_id, user.id, None, "/api/auth/login")
    token = await auth_repo.create_session(user)
    await obs_writer.end_trace(trace_id, "ok")
    clear_request_context()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "0") == "1",
        max_age=7 * 24 * 3600,
    )
    return LoginResponse(
        token=token,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


@app.post("/api/auth/logout")
async def logout(
    response: Response,
    token: str | None = Depends(get_token_from_request),
) -> Dict[str, str]:
    if token:
        await auth_repo.logout(token)
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "ok"}


@app.get("/api/auth/me", response_model=MeResponse)
async def me(user: UserRecord = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=user.username, display_name=user.display_name, role=user.role)


@app.post("/api/chat", response_model=ChatResponse)
async def simple_chat(
    body: ChatRequest,
    request: Request,
    user: UserRecord = Depends(get_current_user),
    server: AirlineServer = Depends(get_server),
) -> ChatResponse:
    """简易聊天接口，不依赖 ChatKit CDN（国内网络友好）。"""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    ctx = _http_ctx(request, user, body.thread_id)
    await _start_trace(ctx, "/api/chat")

    thread = await server.ensure_thread(body.thread_id, ctx)
    ctx["thread_id"] = thread.id
    get_request_context().thread_id = thread.id

    seq = get_request_context().next_chat_sequence()
    await obs_writer.log_chat_message(
        user.id,
        thread.id,
        seq,
        "user",
        message,
        trace_id=get_request_context().trace_id,
    )

    user_msg = UserMessageItem(
        id=server.store.generate_item_id("message", thread, ctx),
        thread_id=thread.id,
        created_at=datetime.now(),
        content=[UserMessageTextContent(text=message)],
        inference_options=InferenceOptions(),
    )

    reply_parts: list[str] = []
    try:
        async for event in server.respond(thread, user_msg, ctx):
            if isinstance(event, ThreadItemDoneEvent):
                item = event.item
                if isinstance(item, AssistantMessageItem):
                    for part in item.content:
                        text = getattr(part, "text", "")
                        if isinstance(text, str) and text:
                            reply_parts.append(text)
    except Exception as exc:
        import logging

        logging.getLogger("airline.chat").exception("simple_chat failed")
        try:
            await obs_writer.end_trace(get_request_context().trace_id, "error", str(exc))
        finally:
            clear_request_context()
        # 不向客户端泄露内部异常细节
        raise HTTPException(status_code=500, detail="服务器处理失败，请稍后重试。") from exc

    reply = "".join(reply_parts).strip()
    if not reply:
        reply = "抱歉，未能生成回复，请重试。"

    seq2 = get_request_context().next_chat_sequence()
    await obs_writer.log_chat_message(
        user.id,
        thread.id,
        seq2,
        "assistant",
        reply,
        trace_id=get_request_context().trace_id,
    )
    await obs_writer.end_trace(get_request_context().trace_id, "ok")
    clear_request_context()

    return ChatResponse(thread_id=thread.id, reply=reply)


@app.post("/chatkit")
async def chatkit_endpoint(
    request: Request,
    user: UserRecord = Depends(get_current_user),
    server: AirlineServer = Depends(get_server),
) -> Response:
    ctx = _http_ctx(request, user)
    await _start_trace(ctx, "/chatkit")
    trace_id = get_request_context().trace_id
    payload = await request.body()
    result = await server.process(payload, ctx)
    if isinstance(result, StreamingResult):
        async def _stream_with_trace():
            try:
                async for chunk in result:
                    yield chunk
            finally:
                await obs_writer.end_trace(trace_id, "ok")
                clear_request_context()

        return StreamingResponse(_stream_with_trace(), media_type="text/event-stream")
    try:
        if hasattr(result, "json"):
            return Response(content=result.json, media_type="application/json")
        return Response(content=result)
    finally:
        await obs_writer.end_trace(trace_id, "ok")
        clear_request_context()


@app.get("/chatkit/state")
async def chatkit_state(
    request: Request,
    thread_id: str = Query(...),
    user: UserRecord = Depends(get_current_user),
    server: AirlineServer = Depends(get_server),
) -> Dict[str, Any]:
    ctx = _http_ctx(request, user, thread_id)
    # 只读轮询端点：不建 trace，避免每个轮询请求在 obs.traces 中留下 running 空记录
    try:
        return await server.snapshot(thread_id, ctx)
    finally:
        clear_request_context()


@app.get("/chatkit/bootstrap")
async def chatkit_bootstrap(
    request: Request,
    user: UserRecord = Depends(get_current_user),
    server: AirlineServer = Depends(get_server),
) -> Dict[str, Any]:
    ctx = _http_ctx(request, user)
    try:
        return await server.snapshot(None, ctx)
    finally:
        clear_request_context()


@app.get("/chatkit/state/stream")
async def chatkit_state_stream(
    request: Request,
    thread_id: str = Query(...),
    user: UserRecord = Depends(get_current_user),
    server: AirlineServer = Depends(get_server),
):
    ctx = _http_ctx(request, user, thread_id)
    thread = await server.ensure_thread(thread_id, ctx)
    queue = server.register_listener(thread.id)

    async def event_generator():
        try:
            initial = await server.snapshot(thread.id, ctx)
            yield f"data: {json.dumps(initial, default=str)}\n\n"
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        finally:
            server.unregister_listener(thread.id, queue)
            clear_request_context()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/trace/{trace_id}")
async def get_trace(
    trace_id: str,
    user: UserRecord = Depends(get_current_user),
) -> Dict[str, Any]:
    from uuid import UUID
    from db.pool import get_pool

    pool = get_pool()
    tid = UUID(trace_id)
    async with pool.acquire() as conn:
        trace = await conn.fetchrow("SELECT * FROM obs.traces WHERE id = $1", tid)
        if trace is None:
            raise HTTPException(404, "trace not found")
        if user.role != "admin" and trace["user_id"] != user.id:
            raise HTTPException(403, "无权查看该 trace")
        spans = await conn.fetch(
            "SELECT * FROM obs.trace_spans WHERE trace_id = $1 ORDER BY started_at",
            tid,
        )
        llm = await conn.fetch(
            "SELECT * FROM obs.llm_calls WHERE trace_id = $1 ORDER BY call_index",
            tid,
        )
        tools = await conn.fetch(
            "SELECT * FROM obs.tool_calls WHERE trace_id = $1 ORDER BY created_at",
            tid,
        )
    return {
        "trace": dict(trace),
        "spans": [dict(s) for s in spans],
        "llm_calls": [dict(r) for r in llm],
        "tool_calls": [dict(r) for r in tools],
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """健康检查：同时验证数据库连通性，避免'进程活着但业务全挂'的假健康。"""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "ok"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unreachable"},
        )


__all__ = [
    "AirlineAgentChatContext",
    "AirlineAgentContext",
    "app",
    "booking_cancellation_agent",
    "chat_server",
    "create_initial_context",
    "faq_agent",
    "flight_information_agent",
    "public_context",
    "refunds_compensation_agent",
    "seat_special_services_agent",
    "triage_agent",
]
