"""회사별 크롤 상태 (명세 §8-2 crawl_state).

위장 탐지(aggregator §5-4)가 이력 축으로 쓰는 상태.
추상 StateStore + 테스트/드라이런용 InMemoryStateStore. Firestore 구현은 4단계에서 얹는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace


@dataclass
class CrawlState:
    """crawl_state/{company_id} (§8-2)."""

    baseline_count: int | None = None       # 최근 성공 실행 공고 수의 중앙값
    last_ok_ts: float | None = None
    consecutive_suspicious: int = 0
    consecutive_zero: int = 0
    render_cache_hash: str | None = None     # SPA render 경로용, 성공 시에만 갱신
    # baseline 중앙값 계산용 최근 성공 카운트 창 (§8-2 스키마 확장, 롤링 median 재료).
    recent_counts: list[int] = field(default_factory=list)


class StateStore(ABC):
    """회사별 CrawlState 조회/갱신 인터페이스."""

    @abstractmethod
    def get(self, company_id: str) -> CrawlState:
        """없으면 기본값 CrawlState를 반환한다(예외 아님)."""

    @abstractmethod
    def update(self, company_id: str, **fields) -> CrawlState:
        """주어진 필드만 병합 갱신하고 갱신된 상태를 반환한다."""


class InMemoryStateStore(StateStore):
    """프로세스 메모리 저장 (테스트·드라이런용)."""

    def __init__(self) -> None:
        self._data: dict[str, CrawlState] = {}

    def get(self, company_id: str) -> CrawlState:
        return self._data.get(company_id, CrawlState())

    def update(self, company_id: str, **fields) -> CrawlState:
        current = self.get(company_id)
        updated = replace(current, **fields)
        self._data[company_id] = updated
        return updated
