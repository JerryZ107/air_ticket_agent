"""LLM 配置：支持 DeepSeek（OpenAI 兼容接口）或原生 OpenAI。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents import set_default_openai_api, set_default_openai_client, set_tracing_disabled

from pipeline.logging_client import wrap_openai_client

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key, default)
    return value.strip().strip('"').strip("'") if value else default


# DeepSeek V4 分层路由（OpenAI 兼容接口）
API_KEY = _env("DEEPSEEK_API_KEY") or _env("OPENAI_API_KEY")
BASE_URL = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

MODEL_FLASH = _env("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash")
MODEL_PRO = _env("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro")
_EMBEDDING_PRESETS: dict[str, int] = {
    "bge-m3": 1024,
    "m3e-base": 768,
    "zhinao": 768,
    "chinesemodernbert-embedding": 768,
}


def _resolve_embedding_dim(model: str) -> int:
    explicit = _env("EMBEDDING_DIM", "")
    if explicit:
        return int(explicit)
    low = model.lower()
    for key, dim in _EMBEDDING_PRESETS.items():
        if key in low:
            return dim
    return 1024


EMBEDDING_BACKEND = _env("EMBEDDING_BACKEND", "local").lower()  # local | openai
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = _resolve_embedding_dim(EMBEDDING_MODEL)
EMBEDDING_DEVICE = _env("EMBEDDING_DEVICE", "cpu")
# huggingface | modelscope（国内推荐 modelscope）
EMBEDDING_DOWNLOAD = _env("EMBEDDING_DOWNLOAD", "modelscope").lower()
EMBEDDING_HF_ENDPOINT = _env("HF_ENDPOINT", "https://hf-mirror.com")

# 默认模型：Flash（轻量任务）；写操作 Agent 显式指定 MODEL_PRO
MODEL = _env("DEEPSEEK_MODEL") or MODEL_FLASH
GUARDRAIL_MODEL = _env("DEEPSEEK_GUARDRAIL_MODEL") or MODEL_FLASH
USE_DEEPSEEK = bool(_env("DEEPSEEK_API_KEY"))


def configure_llm() -> None:
    """注册全局 OpenAI 兼容客户端（DeepSeek 等）。"""
    if not API_KEY:
        return
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL.rstrip("/"))
    client = wrap_openai_client(client)
    set_default_openai_client(client, use_for_tracing=False)
    # DeepSeek 使用 Chat Completions API，非 OpenAI Responses API
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)


configure_llm()
