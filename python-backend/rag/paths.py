"""Repository paths for RAG and other backend resources."""

from __future__ import annotations

import os
from pathlib import Path

_MARKERS = ("CONTEXT.md", "docker-compose.yml")


def project_root() -> Path:
    """仓库根目录（含 CONTEXT.md 与 docker-compose.yml 的目录）。"""
    env = os.environ.get("PROJECT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    start = Path(__file__).resolve().parent
    for directory in (start, *start.parents):
        if all((directory / name).is_file() for name in _MARKERS):
            return directory
    return Path(__file__).resolve().parent.parent.parent


def policy_manual_dir() -> Path:
    """Policy Manual 语料目录（K1：docs/manual）。"""
    override = os.environ.get("POLICY_MANUAL_DIR", "").strip()
    if override:
        return Path(override).resolve()
    return project_root() / "docs" / "manual"
