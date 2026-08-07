"""로컬 JSON 파일 저장소 (Firebase 없이 개인용 실행).

개인용 단일 사용자에겐 Firestore가 과합니다. 한 디렉터리에 상태를 파일로 두면
로컬/개인 서버에서 그대로 중복제거가 동작한다. (GitHub Actions처럼 파일시스템이
휘발되는 환경에서는 상태를 커밋백하거나 Firestore를 쓰세요.)

  <data_dir>/postings.json      # {doc_id: PostingRecord}  — 중복 판단
  <data_dir>/state.json         # {company_id: CrawlState} — 위장 탐지 이력
  <data_dir>/crawl_errors.jsonl # 이상 Outcome 감사 로그(append)

쓰기는 tmp→replace로 원자적 교체(중간 크래시에도 파일 안 깨짐).
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable

from ..models import PostingRecord
from ..state import CrawlState, StateStore
from .base import CrawlErrorEntry, CrawlErrorStore, PostingStore


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # 같은 디렉터리 내 rename → 원자적


class JsonFilePostingStore(PostingStore):
    def __init__(self, base_dir: str | Path) -> None:
        self._path = Path(base_dir) / "postings.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, PostingRecord] = {}
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
            # 방어: 저장소가 list(레코드 배열)로 잘못 기록돼도 죽지 않고 doc_id로 재키잉.
            if isinstance(raw, list):
                raw = {f"{r.get('site')}__{r.get('job_id')}": r for r in raw}
            self._docs = {k: PostingRecord.from_document(v) for k, v in raw.items()}

    def existing_job_ids(self, site: str, job_ids: Iterable[str]) -> set[str]:
        return {jid for jid in job_ids if f"{site}__{jid}" in self._docs}

    def add(self, records: list[PostingRecord]) -> None:
        if not records:
            return
        for r in records:
            self._docs[r.doc_id] = r
        _atomic_write(self._path, json.dumps(
            {k: v.to_document() for k, v in self._docs.items()},
            ensure_ascii=False,
        ))

    def __len__(self) -> int:
        return len(self._docs)


class JsonFileStateStore(StateStore):
    def __init__(self, base_dir: str | Path) -> None:
        self._path = Path(base_dir) / "state.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, CrawlState] = {}
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
            self._data = {k: CrawlState(**v) for k, v in raw.items()}

    def get(self, company_id: str) -> CrawlState:
        return self._data.get(company_id, CrawlState())

    def update(self, company_id: str, **fields) -> CrawlState:
        updated = replace(self.get(company_id), **fields)
        self._data[company_id] = updated
        _atomic_write(self._path, json.dumps(
            {k: asdict(v) for k, v in self._data.items()},
            ensure_ascii=False,
        ))
        return updated


class JsonFileCrawlErrorStore(CrawlErrorStore):
    def __init__(self, base_dir: str | Path) -> None:
        self._path = Path(base_dir) / "crawl_errors.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entries: list[CrawlErrorEntry]) -> None:
        if not entries:
            return
        with self._path.open("a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e.to_document(), ensure_ascii=False) + "\n")
