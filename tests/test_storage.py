"""4단계: 저장소 · 중복제거 · crawl_errors 테스트."""

from __future__ import annotations

import itertools

from opmon.aggregate import Action
from opmon.dedup import persist_error_actions, store_new_postings
from opmon.models import MatchResult, Posting, PostingRecord
from opmon.outcomes import Outcome
from opmon.storage.firestore import (
    FirestoreCrawlErrorStore,
    FirestorePostingStore,
    FirestoreStateStore,
)
from opmon.storage.memory import InMemoryCrawlErrorStore, InMemoryPostingStore

CLOCK = lambda: 1234.5  # noqa: E731


def _rec(site: str, job_id: str, title: str = "AI 기획자", category: str = "AI") -> PostingRecord:
    return PostingRecord(site=site, job_id=job_id, title=title, url=f"https://x/{job_id}", category=category)


# --- PostingRecord 직렬화 -----------------------------------------------


def test_posting_record_roundtrip():
    r = _rec("nhn", "111")
    r.matched_keywords = ["AI"]
    r.min_experience_ok = None
    back = PostingRecord.from_document(r.to_document())
    assert back == r


def test_posting_record_doc_id():
    assert _rec("nhn", "111").doc_id == "nhn__111"


def test_from_document_ignores_extra_keys():
    doc = _rec("nhn", "111").to_document()
    doc["_stray"] = "ignore me"  # Firestore가 붙일 수 있는 잉여 필드
    r = PostingRecord.from_document(doc)
    assert r.job_id == "111"


def test_from_match_builds_record():
    mr = MatchResult(
        posting=Posting(job_id="9", title="브랜딩 매니저", url="u", posted_date="2026-08-01"),
        category="브랜딩", matched_keywords=["브랜딩"], highlights=["영어가능"], min_experience_ok=None,
    )
    r = PostingRecord.from_match(mr, site="hybe")
    assert r.site == "hybe" and r.job_id == "9" and r.category == "브랜딩"
    assert r.highlights == ["영어가능"] and r.min_experience_ok is None


# --- 중복제거 (site + job_id) -------------------------------------------


def test_store_new_only_saves_new():
    store = InMemoryPostingStore()
    first = store_new_postings([_rec("nhn", "1"), _rec("nhn", "2")], store, now=CLOCK)
    assert {r.job_id for r in first} == {"1", "2"}
    assert len(store) == 2
    # 두 번째 실행: 1은 이미 있음, 3만 신규
    second = store_new_postings([_rec("nhn", "1"), _rec("nhn", "3")], store, now=CLOCK)
    assert {r.job_id for r in second} == {"3"}
    assert len(store) == 3


def test_store_new_sets_first_seen():
    store = InMemoryPostingStore()
    new = store_new_postings([_rec("nhn", "1")], store, now=CLOCK)
    assert new[0].first_seen == 1234.5


def test_store_new_dedupes_within_run():
    store = InMemoryPostingStore()
    new = store_new_postings([_rec("nhn", "1"), _rec("nhn", "1")], store, now=CLOCK)
    assert len(new) == 1 and len(store) == 1


def test_same_job_id_different_site_not_dup():
    store = InMemoryPostingStore()
    new = store_new_postings([_rec("nhn", "1"), _rec("kakao", "1")], store, now=CLOCK)
    assert len(new) == 2  # site가 다르면 별개


def test_store_new_empty():
    store = InMemoryPostingStore()
    assert store_new_postings([], store, now=CLOCK) == []


# --- crawl_errors (log action만 기록) -----------------------------------


def test_persist_error_actions_records_only_logs():
    error_store = InMemoryCrawlErrorStore()
    actions = [
        Action(kind="log", company_id="nhn", outcome=Outcome.SUSPICIOUS_EMPTY, meta={"reason": "x"}),
        Action(kind="alert", company_id="nhn", severity="warn", text="⚠️", outcome=Outcome.SUSPICIOUS_EMPTY),
        Action(kind="log", company_id="skt", outcome=Outcome.BLOCKED, meta={"status": 403}),
    ]
    entries = persist_error_actions(actions, error_store, now=CLOCK)
    assert len(entries) == 2  # alert는 기록 안 함
    assert {e.site for e in entries} == {"nhn", "skt"}
    assert error_store.entries[0].outcome == "suspicious_empty"
    assert error_store.entries[0].ts == 1234.5


# --- Firestore 어댑터 (가짜 클라이언트) ---------------------------------


class _FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, client, coll, doc_id):
        self._c, self._coll, self.id = client, coll, doc_id

    def get(self):
        return _FakeSnap(self.id, self._c.data[self._coll].get(self.id))

    def set(self, data, merge=False):
        cur = self._c.data[self._coll].get(self.id) if merge else None
        base = dict(cur) if cur else {}
        base.update(data)
        self._c.data[self._coll][self.id] = base


class _FakeCollection:
    def __init__(self, client, name):
        self._c, self._name = client, name
        client.data.setdefault(name, {})

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = f"auto_{next(self._c._ids)}"
        return _FakeDocRef(self._c, self._name, doc_id)


class _FakeBatch:
    def __init__(self, client):
        self._ops = []

    def set(self, ref, data):
        self._ops.append((ref, data))

    def commit(self):
        for ref, data in self._ops:
            ref.set(data)


class FakeFirestore:
    def __init__(self):
        self.data: dict[str, dict] = {}
        self._ids = itertools.count()

    def collection(self, name):
        return _FakeCollection(self, name)

    def get_all(self, refs):
        return [ref.get() for ref in refs]

    def batch(self):
        return _FakeBatch(self)


def test_firestore_posting_store_dedup_and_add():
    client = FakeFirestore()
    store = FirestorePostingStore(client=client, collection="postings")
    assert store.existing_job_ids("nhn", ["1", "2"]) == set()
    store.add([_rec("nhn", "1"), _rec("nhn", "2")])
    assert store.existing_job_ids("nhn", ["1", "2", "3"]) == {"1", "2"}
    # 문서 키가 site__job_id 인지
    assert "nhn__1" in client.data["postings"]


def test_firestore_state_store_roundtrip_and_merge():
    client = FakeFirestore()
    store = FirestoreStateStore(client=client, collection="crawl_state")
    from opmon.state import CrawlState

    assert store.get("nhn") == CrawlState()
    store.update("nhn", baseline_count=5, recent_counts=[5])
    store.update("nhn", consecutive_zero=2)
    st = store.get("nhn")
    assert st.baseline_count == 5 and st.consecutive_zero == 2 and st.recent_counts == [5]


def test_firestore_error_store_records():
    client = FakeFirestore()
    store = FirestoreCrawlErrorStore(client=client, collection="crawl_errors")
    from opmon.storage.base import CrawlErrorEntry

    store.record([CrawlErrorEntry(site="nhn", outcome="blocked", meta={"status": 403}, ts=1.0)])
    assert len(client.data["crawl_errors"]) == 1
