from __future__ import annotations as _annotations

import random
import string
import time
from copy import deepcopy

from agents import RunContextWrapper, function_tool
from chatkit.types import ProgressUpdateEvent

from airline.actor import actor_from_run
from airline.hydrate import apply_booking_row
from airline.mcp_integration import USE_MCP_TOOLS
from airline.session_scope import (
    is_admin_session,
    is_logged_in,
    normalize_on_behalf_of_username,
    require_session_actor,
    require_session_username,
)
from services import tool_facade as api

from .context import AirlineAgentChatContext
from .demo_data import active_itinerary, apply_itinerary_defaults, get_itinerary_for_flight


async def _log_tool(name: str, inp: dict, out: str, *, status: str = "ok", ms: int | None = None) -> None:
    try:
        from db.observability import obs_writer
        from pipeline.request_context import get_request_context

        ctx = get_request_context()
        await obs_writer.log_tool_call(
            ctx.trace_id,
            name,
            inp,
            {"result": out},
            status=status,
            latency_ms=ms,
        )
    except Exception:
        pass


def _username(context: RunContextWrapper[AirlineAgentChatContext]) -> str | None:
    return context.context.state.username


# --- PG + RAG（USE_MCP_TOOLS=false 时由 Agent 直接 function_tool 调用）---


@function_tool(
    name_override="faq_lookup_tool", description_override="查询订票手册（RAG）。"
)
async def faq_lookup_tool(question: str) -> str:
    return await api.faq_lookup(question)


@function_tool(
    name_override="flight_status_tool",
    description_override="查询航班状态。",
)
async def flight_status_tool(
    context: RunContextWrapper[AirlineAgentChatContext], flight_number: str
) -> str:
    await context.context.stream(ProgressUpdateEvent(text=f"正在查询航班 {flight_number} 状态…"))
    out = await api.flight_status(flight_number)
    if not out.startswith("未找到航班"):
        ctx_state = context.context.state
        ctx_state.flight_number = flight_number
        await context.context.stream(ProgressUpdateEvent(text=f"已获取航班 {flight_number} 状态"))
        return out
    if is_logged_in(context):
        await context.context.stream(ProgressUpdateEvent(text=f"未找到航班 {flight_number}"))
        return out
    return await _flight_status_mock(context, flight_number)


async def _flight_status_mock(
    context: RunContextWrapper[AirlineAgentChatContext], flight_number: str
) -> str:
    ctx_state = context.context.state
    ctx_state.flight_number = flight_number
    match = get_itinerary_for_flight(flight_number)
    if match:
        scenario_key, itinerary = match
        apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
        segments = itinerary.get("segments", [])
        segment = next(
            (seg for seg in segments if seg.get("flight_number", "").lower() == flight_number.lower()),
            None,
        )
        if segment:
            route = f"{segment.get('origin', '未知')} 至 {segment.get('destination', '未知')}"
            details = [
                f"航班 {flight_number}（{route}）",
                f"状态：{segment.get('status', '准点')}",
            ]
            if segment.get("gate"):
                details.append(f"登机口：{segment['gate']}")
            if segment.get("departure") and segment.get("arrival"):
                details.append(f"计划 {segment['departure']} -> {segment['arrival']}")
            if scenario_key == "disrupted" and segment.get("flight_number") == "PA441":
                details.append("该延误将导致错过后续 NY802 联程，建议改签。")
            await context.context.stream(
                ProgressUpdateEvent(text=f"已获取航班 {flight_number} 状态")
            )
            return " | ".join(details)
    await context.context.stream(ProgressUpdateEvent(text=f"航班 {flight_number} 无异常"))
    return f"航班 {flight_number} 准点，预计从 A10 登机口出发。"


@function_tool(
    name_override="get_matching_flights",
    description_override="延误或取消时查找备选航班。",
)
async def get_matching_flights(
    context: RunContextWrapper[AirlineAgentChatContext],
    origin: str | None = None,
    destination: str | None = None,
) -> str:
    await context.context.stream(ProgressUpdateEvent(text="正在搜索备选航班…"))
    rows_out = await api.search_flights(origin, destination)
    if not rows_out.startswith("没有匹配"):
        await context.context.stream(ProgressUpdateEvent(text="已从数据库返回航班列表"))
        await _log_tool("get_matching_flights", {"origin": origin, "destination": destination}, rows_out)
        return rows_out
    if is_logged_in(context):
        await context.context.stream(ProgressUpdateEvent(text="没有匹配的航班"))
        return rows_out
    return await _matching_flights_mock(context, origin, destination)


async def _matching_flights_mock(
    context: RunContextWrapper[AirlineAgentChatContext],
    origin: str | None,
    destination: str | None,
) -> str:
    ctx_state = context.context.state
    scenario_key, itinerary = active_itinerary(ctx_state)
    apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
    options = itinerary.get("rebook_options", [])
    if not options:
        await context.context.stream(ProgressUpdateEvent(text="行程准点，无需备选"))
        return "所有航班均准点运行，无需备选航班。"
    filtered = [
        opt
        for opt in options
        if (origin is None or origin.lower() in opt.get("origin", "").lower())
        and (destination is None or destination.lower() in opt.get("destination", "").lower())
    ]
    final_options = filtered or options
    await context.context.stream(
        ProgressUpdateEvent(text=f"找到 {len(final_options)} 个备选航班")
    )
    lines = []
    for opt in final_options:
        lines.append(
            f"{opt.get('flight_number')} {opt.get('origin')} -> {opt.get('destination')} "
            f"出发 {opt.get('departure')} 到达 {opt.get('arrival')} | 座位 {opt.get('seat', '自动分配')} | {opt.get('note', '')}"
        )
    if scenario_key == "disrupted":
        lines.append("以上选项次日抵达奥斯汀，过夜酒店及餐食由航司承担。")
    ctx_state.itinerary = ctx_state.itinerary or deepcopy(itinerary.get("segments", []))
    return "备选航班：\n" + "\n".join(lines)


@function_tool
async def update_seat(
    context: RunContextWrapper[AirlineAgentChatContext],
    confirmation_number: str,
    new_seat: str,
    on_behalf_of_username: str | None = None,
) -> str:
    if not is_logged_in(context):
        apply_itinerary_defaults(context.context.state)
        context.context.state.confirmation_number = confirmation_number
        context.context.state.seat_number = new_seat
        return f"已将确认号 {confirmation_number} 的座位更新为 {new_seat}。"
    uname = require_session_username(context)
    behalf = normalize_on_behalf_of_username(context, on_behalf_of_username)
    try:
        out = await api.update_seat(uname, confirmation_number, new_seat, on_behalf_of_username=behalf)
    except (PermissionError, ValueError) as exc:
        return str(exc)
    context.context.state.confirmation_number = confirmation_number
    context.context.state.seat_number = new_seat
    return out


@function_tool(
    name_override="cancel_flight",
    description_override=(
        "取消订单。确认号须属于会话绑定账户；管理员代客目标由系统自动识别并绑定，"
        "也可显式传 on_behalf_of_username。"
    ),
)
async def cancel_flight(
    context: RunContextWrapper[AirlineAgentChatContext],
    confirmation_number: str | None = None,
    on_behalf_of_username: str | None = None,
) -> str:
    if not is_logged_in(context):
        apply_itinerary_defaults(context.context.state)
        fn = context.context.state.flight_number
        assert fn is not None, "Flight number is required"
        confirmation = context.context.state.confirmation_number or "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
        context.context.state.confirmation_number = confirmation
        return f"已成功取消航班 {fn}，确认号 {confirmation}。"
    confirmation = (confirmation_number or context.context.state.confirmation_number or "").strip()
    if not confirmation:
        return "请提供确认号，或先通过 list_bookings / list_customer_bookings 查询。"
    uname = require_session_username(context)
    behalf = normalize_on_behalf_of_username(context, on_behalf_of_username)
    try:
        return await api.cancel_booking(uname, confirmation, on_behalf_of_username=behalf)
    except (PermissionError, ValueError) as exc:
        return str(exc)


@function_tool(
    name_override="book_new_flight",
    description_override="为当前登录用户预订新航班；若上下文已有本人确认号则走 Saga 改签（确认号不变）。",
)
async def book_new_flight(
    context: RunContextWrapper[AirlineAgentChatContext], flight_number: str | None = None
) -> str:
    await context.context.stream(ProgressUpdateEvent(text="正在预订航班…"))
    ctx_state = context.context.state
    if is_logged_in(context) and ctx_state.confirmation_number and flight_number:
        uname = require_session_username(context)
        return await api.rebook_flight(uname, ctx_state.confirmation_number, flight_number)
    if is_logged_in(context):
        return "请先通过 list_bookings 确认本人订单与确认号，或提供要预订的新航班号。"
    return await _book_new_flight_mock(context, flight_number)


@function_tool(
    name_override="rebook_flight",
    description_override="为当前登录用户改签订单（确认号不变）；确认号须为本人订单。",
)
async def rebook_flight_tool(
    context: RunContextWrapper[AirlineAgentChatContext],
    confirmation_number: str,
    new_flight_number: str,
    new_seat: str = "自动分配",
    on_behalf_of_username: str | None = None,
) -> str:
    if not is_logged_in(context):
        return "未登录，无法改签。"
    uname = require_session_username(context)
    behalf = normalize_on_behalf_of_username(context, on_behalf_of_username)
    try:
        out = await api.rebook_flight(
            uname,
            confirmation_number,
            new_flight_number,
            new_seat,
            on_behalf_of_username=behalf,
        )
    except (PermissionError, ValueError) as exc:
        return str(exc)
    ctx_state = context.context.state
    ctx_state.confirmation_number = confirmation_number
    ctx_state.flight_number = new_flight_number
    if new_seat and new_seat != "自动分配":
        ctx_state.seat_number = new_seat
    return out


async def _book_new_flight_mock(
    context: RunContextWrapper[AirlineAgentChatContext], flight_number: str | None
) -> str:
    ctx_state = context.context.state
    scenario_key, itinerary = active_itinerary(ctx_state)
    apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
    options = itinerary.get("rebook_options", [])
    selection = None
    if flight_number:
        selection = next(
            (opt for opt in options if opt.get("flight_number", "").lower() == flight_number.lower()),
            None,
        )
    if selection is None and options:
        selection = options[0]
    if selection is None:
        seat = ctx_state.seat_number or "自动分配"
        confirmation = ctx_state.confirmation_number or "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
        ctx_state.confirmation_number = confirmation
        await context.context.stream(ProgressUpdateEvent(text="已预订占位航班"))
        return (
            f"已预订航班 {flight_number or '待定'}，确认号 {confirmation}，座位 {seat}。"
        )
    ctx_state.flight_number = selection.get("flight_number")
    ctx_state.seat_number = selection.get("seat") or ctx_state.seat_number or "自动分配"
    ctx_state.itinerary = ctx_state.itinerary or deepcopy(itinerary.get("segments", []))
    updated_itinerary = [
        seg
        for seg in ctx_state.itinerary
        if not (
            scenario_key == "disrupted"
            and seg.get("origin", "").startswith("New York")
            and seg.get("destination", "").startswith("Austin")
        )
    ]
    updated_itinerary.append(
        {
            "flight_number": selection["flight_number"],
            "origin": selection.get("origin", ""),
            "destination": selection.get("destination", ""),
            "departure": selection.get("departure", ""),
            "arrival": selection.get("arrival", ""),
            "status": "已确认改签航班",
            "gate": "待定",
        }
    )
    ctx_state.itinerary = updated_itinerary
    confirmation = ctx_state.confirmation_number or "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )
    ctx_state.confirmation_number = confirmation
    await context.context.stream(
        ProgressUpdateEvent(
            text=f"已改签至 {selection['flight_number']}，座位 {ctx_state.seat_number}",
        )
    )
    return (
        f"已改签至 {selection['flight_number']}，{selection.get('origin')} -> {selection.get('destination')}。"
        f"出发 {selection.get('departure')}，到达 {selection.get('arrival')}（次日抵达奥斯汀）。"
        f"座位：{ctx_state.seat_number}，确认号 {confirmation}。"
    )


# --- 仅 UI / 演示，不走 repository ---


@function_tool(
    name_override="list_bookings",
    description_override="列出当前登录会话绑定账户的全部订单（不可查他人；管理员见全库最近订单）。",
)
async def list_bookings_tool(
    context: RunContextWrapper[AirlineAgentChatContext],
) -> str:
    if not is_logged_in(context):
        return "未登录，无法查询订单。"
    actor = require_session_actor(context)
    uname = require_session_username(context)
    out = await api.list_bookings(uname)
    from db.repository.bookings import booking_repo

    rows = await booking_repo.list_bookings_for_actor(actor)
    if rows:
        apply_booking_row(context.context.state, rows[0])
    await _log_tool("list_bookings", {"session_user": uname}, out)
    return out


@function_tool(
    name_override="list_customer_bookings",
    description_override="仅管理员：查询指定旅客用户名下的全部订单（代客前核对）。",
)
async def list_customer_bookings_tool(
    context: RunContextWrapper[AirlineAgentChatContext],
    customer_username: str,
) -> str:
    if not is_logged_in(context):
        return "未登录，无法查询。"
    if not is_admin_session(context):
        return "仅管理员可查询指定旅客订单。"
    admin = require_session_username(context)
    out = await api.list_customer_bookings(admin, customer_username)
    if "未找到订单" not in out:
        actor = require_session_actor(context)
        from db.repository.bookings import booking_repo

        rows = await booking_repo.list_bookings_for_customer(actor, customer_username)
        if rows:
            apply_booking_row(context.context.state, rows[0])
    await _log_tool("list_customer_bookings", {"customer": customer_username}, out)
    return out


@function_tool(
    name_override="get_trip_details",
    description_override=(
        "已登录用户：返回系统注入的全部订单快照（入口 Binder 已注入，无需重复查询）。"
        "未登录或演示剧本：读取 Binder 已注入的示例行程。"
    ),
)
async def get_trip_details(
    context: RunContextWrapper[AirlineAgentChatContext], message: str
) -> str:
    if is_logged_in(context):
        uname = require_session_username(context)
        state = context.context.state
        rows = state.bookings or []
        if rows:
            lines = []
            for b in rows:
                owner = f"旅客{b.get('owner_username')} " if b.get("owner_username") else ""
                lines.append(
                    f"{owner}{b.get('confirmation_no')} {b.get('flight_no')} "
                    f"{b.get('origin')}->{b.get('destination')} "
                    f"座位{b.get('seat')} ({b.get('status')})"
                )
            out = "订单列表：" + "；".join(lines)
            await _log_tool("get_trip_details", {"message": message, "session_user": uname}, out)
            return out
        # 防御：入口未注入（历史会话/直连调用）时回退查询并刷新状态
        actor = require_session_actor(context)
        bookings = await api.list_bookings(uname)
        await _log_tool("get_trip_details", {"message": message, "session_user": uname}, bookings)
        if "未找到订单" in bookings:
            return bookings
        from db.repository.bookings import booking_repo

        rows = await booking_repo.list_bookings_for_actor(actor)
        if rows:
            apply_booking_row(context.context.state, rows[0])
        return bookings
    # 未登录演示路径：场景已由 Binder 在入口预选并注入，这里只读取
    apply_itinerary_defaults(context.context.state)
    ctx = context.context.state
    segments = ctx.itinerary or []
    segment_summaries = []
    for seg in segments:
        segment_summaries.append(
            f"{seg.get('flight_number')} {seg.get('origin')} -> {seg.get('destination')} "
            f"状态: {seg.get('status')}"
        )
    summary = "；".join(segment_summaries) if segment_summaries else "暂无航段详情"
    label = "延误联程" if ctx.scenario == "disrupted" else "正常航班"
    return (
        f"已加载{label}行程：航班 {ctx.flight_number or '未知'}，确认号 {ctx.confirmation_number or '未知'}，"
        f"出发 {ctx.origin or '未知'}，目的地 {ctx.destination or '未知'}。{summary}"
    )


@function_tool(
    name_override="assign_special_service_seat",
    description_override="为医疗等需求分配前排或特殊服务座位。",
)
async def assign_special_service_seat(
    context: RunContextWrapper[AirlineAgentChatContext], seat_request: str = "前排医疗需求"
) -> str:
    ctx_state = context.context.state
    apply_itinerary_defaults(ctx_state)
    req_lower = seat_request.lower()
    preferred_seat = "1A" if ("front" in req_lower or "前排" in seat_request) else "2A"
    ctx_state.seat_number = preferred_seat
    ctx_state.special_service_note = seat_request
    confirmation = ctx_state.confirmation_number or "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )
    ctx_state.confirmation_number = confirmation
    return (
        f"已在航班 {ctx_state.flight_number or '后续航段'} 为您安排{seat_request}座位 {preferred_seat}。"
        f"确认号 {confirmation} 已标注特殊服务。"
    )


@function_tool(
    name_override="issue_compensation",
    description_override="创建补偿案例并发放酒店/餐券。",
)
async def issue_compensation(
    context: RunContextWrapper[AirlineAgentChatContext], reason: str = "延误导致错过后续航班"
) -> str:
    await context.context.stream(ProgressUpdateEvent(text="正在创建补偿案例…"))
    ctx_state = context.context.state
    scenario_key, itinerary = active_itinerary(ctx_state)
    apply_itinerary_defaults(ctx_state, scenario_key=scenario_key)
    case_id = ctx_state.compensation_case_id or f"CMP-{random.randint(1000, 9999)}"
    ctx_state.compensation_case_id = case_id
    voucher_values = list(itinerary.get("vouchers", {}).values())
    if voucher_values:
        ctx_state.vouchers = voucher_values
    else:
        ctx_state.vouchers = ctx_state.vouchers or []
    vouchers_text = "；".join(ctx_state.vouchers) if ctx_state.vouchers else "已记录补偿，无需额外券。"
    await context.context.stream(ProgressUpdateEvent(text=f"案例 {case_id} 券已发放"))
    return (
        f"已创建补偿案例 {case_id}，原因：{reason}。"
        f"已发放：{vouchers_text}。请保留酒店/餐食收据并附于本案例。"
    )


@function_tool(
    name_override="display_seat_map",
    description_override="向客户展示交互式座位图。",
)
async def display_seat_map(
    context: RunContextWrapper[AirlineAgentChatContext]
) -> str:
    return "DISPLAY_SEAT_MAP"


# 会话绑定与读操作走本地 function_tool；写操作在 MCP 启用时走 MCP 子进程，避免同名工具重复注册。
_MCP_SUPERSEDES_LOCAL = (
    cancel_flight,
    rebook_flight_tool,
    update_seat,
)

_LOCAL_ONLY_TOOLS = {
    "faq_agent": [],
    "flight_information_agent": [],
    "booking_cancellation_agent": [book_new_flight],
    "seat_special_services_agent": [assign_special_service_seat, display_seat_map],
    "refunds_compensation_agent": [issue_compensation],
    "triage_agent": [get_trip_details, list_customer_bookings_tool],
}


def tools_for_agent(agent_key: str, default: list) -> list:
    if not USE_MCP_TOOLS:
        return default
    out: list = []
    seen_names: set[str] = set()

    def append(tool) -> None:
        name = getattr(tool, "name", None) or ""
        if not name or name in seen_names:
            return
        seen_names.add(name)
        out.append(tool)

    for tool in default:
        if tool in _MCP_SUPERSEDES_LOCAL:
            continue
        append(tool)
    for tool in _LOCAL_ONLY_TOOLS.get(agent_key, []):
        append(tool)
    return out
