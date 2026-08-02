from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class RetrievedChunk:
    id: UUID
    source_file: str
    content: str
    score: float
    channel: str = "unknown"
