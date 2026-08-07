"""로컬 JSON 파일 저장소 라운드트립 테스트."""

from __future__ import annotations

from opmon.models import PostingRecord
from opmon.storage.base import CrawlErrorEntry
from opmon.storage.file import (
    JsonFileCrawlErrorStore,
    JsonFilePostingStore,
    JsonFileStateStore,
)


def _rec(site, jid, title="AI 기획자"):
    return PostingRecord(site=site, job_id=jid, title=title, url=f"https://x/{jid}",
                         category="AI", first_seen=1.0)


def test_posting_store_persists_across_instances(tmp_path):
    s1 = JsonFilePostingStore(tmp_path)
    s1.add([_rec("toss", "1"), _rec("toss", "2")])
    # 새 인스턴스가 디스크에서 복원
    s2 = JsonFilePostingStore(tmp_path)
    assert len(s2) == 2
    assert s2.existing_job_ids("toss", ["1", "2", "3"]) == {"1", "2"}
    assert s2.existing_job_ids("kakao", ["1"]) == set()  # site 분리


def test_posting_store_tolerates_list_format(tmp_path):
    # 저장소가 list(레코드 배열)로 잘못 기록돼도 죽지 않고 doc_id로 복원해야 한다.
    import json
    (tmp_path / "postings.json").write_text(json.dumps([
        {"site": "vaughan", "job_id": "J1", "title": "UX Designer",
         "url": "https://x/J1", "category": "Design(EN)"},
    ]), encoding="utf-8")
    s = JsonFilePostingStore(tmp_path)
    assert len(s) == 1
    assert s.existing_job_ids("vaughan", ["J1"]) == {"J1"}


def test_posting_store_dedup_semantics(tmp_path):
    s = JsonFilePostingStore(tmp_path)
    s.add([_rec("toss", "1")])
    # 2회차: 1은 기존, 2만 신규로 판별돼야
    assert s.existing_job_ids("toss", ["1", "2"]) == {"1"}
    s.add([_rec("toss", "2")])
    assert s.existing_job_ids("toss", ["1", "2"]) == {"1", "2"}


def test_state_store_persists(tmp_path):
    s1 = JsonFileStateStore(tmp_path)
    s1.update("toss", baseline_count=5, recent_counts=[5, 6, 5])
    s2 = JsonFileStateStore(tmp_path)
    st = s2.get("toss")
    assert st.baseline_count == 5
    assert st.recent_counts == [5, 6, 5]
    # 미등록 회사는 기본값
    assert s2.get("unknown").baseline_count is None


def test_error_store_appends(tmp_path):
    s = JsonFileCrawlErrorStore(tmp_path)
    s.record([CrawlErrorEntry(site="toss", outcome="blocked", meta={"status": 403}, ts=1.0)])
    s.record([CrawlErrorEntry(site="kakao", outcome="suspicious_empty", ts=2.0)])
    lines = (tmp_path / "crawl_errors.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert "blocked" in lines[0] and "kakao" in lines[1]


def test_empty_add_is_noop(tmp_path):
    s = JsonFilePostingStore(tmp_path)
    s.add([])  # 빈 추가는 파일 안 만들어도 됨(크래시만 안 나면)
    assert len(s) == 0
