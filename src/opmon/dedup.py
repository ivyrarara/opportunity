"""중복 제거 · 저장 연결 (명세 §8-1, §5-5).

- store_new_postings: site + job_id 기준으로 이미 있으면 스킵, 없으면 first_seen 채워 저장.
  반환은 "이번에 새로 저장된" 레코드 (알림 대상 후보; 시드 모드는 7단계에서 처리).
- persist_error_actions: aggregator의 log Action을 crawl_errors에 기록(§5-5 감사).
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from .aggregate import Action
from .models import PostingRecord
from .storage.base import CrawlErrorEntry, CrawlErrorStore, PostingStore


def store_new_postings(
    records: list[PostingRecord],
    store: PostingStore,
    *,
    now: Callable[[], float] = time.time,
) -> list[PostingRecord]:
    """중복 아닌 것만 저장하고 새로 저장된 레코드 목록을 반환."""
    if not records:
        return []

    by_site: dict[str, list[PostingRecord]] = defaultdict(list)
    for r in records:
        by_site[r.site].append(r)

    ts = now()
    new_records: list[PostingRecord] = []
    for site, recs in by_site.items():
        seen = store.existing_job_ids(site, [r.job_id for r in recs])
        fresh_ids: set[str] = set()
        for r in recs:
            # 같은 실행 안에서의 중복도 제거
            if r.job_id in seen or r.job_id in fresh_ids:
                continue
            fresh_ids.add(r.job_id)
            r.first_seen = ts
            new_records.append(r)

    if new_records:
        store.add(new_records)
    return new_records


def persist_error_actions(
    actions: list[Action],
    error_store: CrawlErrorStore,
    *,
    now: Callable[[], float] = time.time,
) -> list[CrawlErrorEntry]:
    """log Action → crawl_errors 기록. 기록한 엔트리 목록 반환."""
    ts = now()
    entries = [
        CrawlErrorEntry(
            site=a.company_id,
            outcome=a.outcome.value if a.outcome is not None else "unknown",
            meta=a.meta or {},
            ts=ts,
        )
        for a in actions
        if a.kind == "log"
    ]
    if entries:
        error_store.record(entries)
    return entries
