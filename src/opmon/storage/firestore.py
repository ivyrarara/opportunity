"""Firestore 저장소 구현 (명세 §8).

격리 원칙(§1): 마늘과 별도 Firebase 프로젝트 권장. 컬렉션명에 "채용/job" 흔적 없이
중립적으로 둔다(기본값: postings / crawl_state / crawl_errors — 일반 크롤러 용어).

자격증명은 환경변수로 주입한다(코드/레포에 키 금지):
  GOOGLE_APPLICATION_CREDENTIALS = 서비스계정 JSON 경로
  OPMON_FIRESTORE_PROJECT        = 프로젝트 id (선택; 미지정 시 ADC 기본)

google-cloud-firestore 미설치/미설정이어도 이 모듈 import 자체는 안전하다
(라이브러리·클라이언트는 실제 사용 시점에 지연 로드).
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Iterable

from ..models import PostingRecord
from ..state import CrawlState, StateStore
from .base import CrawlErrorEntry, CrawlErrorStore, PostingStore

POSTINGS_COLLECTION = os.environ.get("OPMON_POSTINGS_COLLECTION", "postings")
STATE_COLLECTION = os.environ.get("OPMON_STATE_COLLECTION", "crawl_state")
ERRORS_COLLECTION = os.environ.get("OPMON_ERRORS_COLLECTION", "crawl_errors")

_STATE_FIELDS = set(CrawlState.__dataclass_fields__)  # type: ignore[attr-defined]


def firestore_client(project: str | None = None):
    """Firestore 클라이언트를 지연 생성. 라이브러리 없으면 명확히 실패."""
    try:
        from google.cloud import firestore  # type: ignore
    except ImportError as exc:  # pragma: no cover - 환경 의존
        raise RuntimeError(
            "google-cloud-firestore 미설치. `pip install google-cloud-firestore` 후 "
            "GOOGLE_APPLICATION_CREDENTIALS 환경변수를 설정하세요."
        ) from exc
    project = project or os.environ.get("OPMON_FIRESTORE_PROJECT")
    return firestore.Client(project=project) if project else firestore.Client()


class FirestorePostingStore(PostingStore):
    def __init__(self, client=None, *, collection: str = POSTINGS_COLLECTION) -> None:
        self._client = client or firestore_client()
        self._col = self._client.collection(collection)

    def existing_job_ids(self, site: str, job_ids: Iterable[str]) -> set[str]:
        job_ids = list(job_ids)
        if not job_ids:
            return set()
        refs = [self._col.document(f"{site}__{jid}") for jid in job_ids]
        existing: set[str] = set()
        for snap in self._client.get_all(refs):
            if snap.exists:
                data = snap.to_dict() or {}
                jid = data.get("job_id")
                if jid is not None:
                    existing.add(jid)
        return existing

    def add(self, records: list[PostingRecord]) -> None:
        batch = self._client.batch()
        for r in records:
            batch.set(self._col.document(r.doc_id), r.to_document())
        batch.commit()


class FirestoreStateStore(StateStore):
    def __init__(self, client=None, *, collection: str = STATE_COLLECTION) -> None:
        self._client = client or firestore_client()
        self._col = self._client.collection(collection)

    def get(self, company_id: str) -> CrawlState:
        snap = self._col.document(company_id).get()
        if not snap.exists:
            return CrawlState()
        data = snap.to_dict() or {}
        return CrawlState(**{k: v for k, v in data.items() if k in _STATE_FIELDS})

    def update(self, company_id: str, **fields) -> CrawlState:
        merged = replace(self.get(company_id), **fields)
        self._col.document(company_id).set(_state_to_document(merged))
        return merged


class FirestoreCrawlErrorStore(CrawlErrorStore):
    def __init__(self, client=None, *, collection: str = ERRORS_COLLECTION) -> None:
        self._client = client or firestore_client()
        self._col = self._client.collection(collection)

    def record(self, entries: list[CrawlErrorEntry]) -> None:
        batch = self._client.batch()
        for e in entries:
            batch.set(self._col.document(), e.to_document())  # auto-id
        batch.commit()


def _state_to_document(state: CrawlState) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(state)
