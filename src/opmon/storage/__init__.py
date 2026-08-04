"""저장소 계층 (명세 §8).

추상 인터페이스(base) + 인메모리 구현(memory) + Firestore 구현(firestore).
상위 로직은 인터페이스에만 의존하므로, 테스트/드라이런은 인메모리로,
운영은 Firestore로 바꿔 끼운다. 실제 자격증명 연결은 배포 시점(§12).
"""

from .base import CrawlErrorEntry, CrawlErrorStore, PostingStore
from .memory import InMemoryCrawlErrorStore, InMemoryPostingStore

__all__ = [
    "PostingStore",
    "CrawlErrorStore",
    "CrawlErrorEntry",
    "InMemoryPostingStore",
    "InMemoryCrawlErrorStore",
]
