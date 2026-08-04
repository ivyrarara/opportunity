"""인메모리 저장소 구현 (테스트·드라이런용)."""

from __future__ import annotations

from typing import Iterable

from ..models import PostingRecord
from .base import CrawlErrorEntry, CrawlErrorStore, PostingStore


class InMemoryPostingStore(PostingStore):
    def __init__(self) -> None:
        self._docs: dict[str, PostingRecord] = {}  # doc_id → record

    def existing_job_ids(self, site: str, job_ids: Iterable[str]) -> set[str]:
        return {jid for jid in job_ids if f"{site}__{jid}" in self._docs}

    def add(self, records: list[PostingRecord]) -> None:
        for r in records:
            self._docs[r.doc_id] = r

    # 테스트 편의
    def all(self) -> list[PostingRecord]:
        return list(self._docs.values())

    def __len__(self) -> int:
        return len(self._docs)


class InMemoryCrawlErrorStore(CrawlErrorStore):
    def __init__(self) -> None:
        self.entries: list[CrawlErrorEntry] = []

    def record(self, entries: list[CrawlErrorEntry]) -> None:
        self.entries.extend(entries)
