"""저장소 추상 인터페이스 (명세 §8)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..models import PostingRecord


class PostingStore(ABC):
    """`postings` 컬렉션 (§8-1). 중복 판단: site + job_id."""

    @abstractmethod
    def existing_job_ids(self, site: str, job_ids: Iterable[str]) -> set[str]:
        """주어진 job_id 중 이미 저장된 것들의 집합을 반환."""

    @abstractmethod
    def add(self, records: list[PostingRecord]) -> None:
        """신규 레코드 저장 (first_seen은 호출 전에 채워져 있어야 함)."""


@dataclass
class CrawlErrorEntry:
    """`crawl_errors` 문서 (§8-3). 모든 이상 Outcome을 감사용으로 기록."""

    site: str | None
    outcome: str
    meta: dict[str, Any] = field(default_factory=dict)
    ts: float | None = None

    def to_document(self) -> dict:
        return {"site": self.site, "outcome": self.outcome, "meta": self.meta, "ts": self.ts}


class CrawlErrorStore(ABC):
    """`crawl_errors` 컬렉션 (§8-3)."""

    @abstractmethod
    def record(self, entries: list[CrawlErrorEntry]) -> None:
        ...
