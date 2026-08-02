"""Local sentence-transformers (BGE-M3 / Zhinao) with HuggingFace or ModelScope download."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from llm_config import (
    API_KEY,
    BASE_URL,
    EMBEDDING_BACKEND,
    EMBEDDING_DIM,
    EMBEDDING_DEVICE,
    EMBEDDING_DOWNLOAD,
    EMBEDDING_HF_ENDPOINT,
    EMBEDDING_MODEL,
)

_model: Any = None
_model_lock = asyncio.Lock()

# HuggingFace id -> ModelScope id（国内镜像）
_MODELSCOPE_MAP: dict[str, str] = {
    "BAAI/bge-m3": "Xorbits/bge-m3",
    "bge-m3": "Xorbits/bge-m3",
    "qihoo360/Zhinao-ChineseModernBert-Embedding": "qihoo360/Zhinao-ChineseModernBert-Embedding",
    "qihoo360/360Zhinao-Embedding-Base": "qihoo360/360Zhinao-Embedding-Base",
    "moka-ai/m3e-base": "Jerry0/m3e-base",
}


def _resolve_model_path(model_id: str) -> str:
    if EMBEDDING_DOWNLOAD == "modelscope":
        from modelscope import snapshot_download

        ms_id = _MODELSCOPE_MAP.get(model_id, model_id)
        return snapshot_download(ms_id)
    if EMBEDDING_HF_ENDPOINT:
        os.environ.setdefault("HF_ENDPOINT", EMBEDDING_HF_ENDPOINT)
    return model_id


async def _get_local_model() -> Any:
    global _model
    if _model is not None:
        return _model
    async with _model_lock:
        if _model is not None:
            return _model

        def _load() -> Any:
            from sentence_transformers import SentenceTransformer

            path = _resolve_model_path(EMBEDDING_MODEL)
            return SentenceTransformer(path, device=EMBEDDING_DEVICE)

        _model = await asyncio.to_thread(_load)
        return _model


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    if not API_KEY:
        return []
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL.rstrip("/"))
    try:
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    except Exception:
        return []
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [_fit_dim(list(item.embedding)) for item in ordered]


def _fit_dim(vec: list[float]) -> list[float]:
    if len(vec) == EMBEDDING_DIM:
        return vec
    if len(vec) > EMBEDDING_DIM:
        return vec[:EMBEDDING_DIM]
    return vec + [0.0] * (EMBEDDING_DIM - len(vec))


async def _embed_local(texts: list[str]) -> list[list[float]]:
    model = await _get_local_model()

    def _encode() -> list[list[float]]:
        raw = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=min(32, len(texts)),
        )
        return [_fit_dim(row.tolist()) for row in raw]

    return await asyncio.to_thread(_encode)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if EMBEDDING_BACKEND == "openai":
        return await _embed_openai(texts)
    try:
        return await _embed_local(texts)
    except Exception:
        return []


def vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
