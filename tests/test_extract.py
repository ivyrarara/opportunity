"""다층 추출기(§6-5) 테스트."""

from __future__ import annotations

from pathlib import Path

from opmon.extract import (
    derive_job_id,
    extract_with_fingerprint,
    from_jsonld,
    normalize_url,
    parse_declared,
)
from opmon.fingerprints import JOBKOREA_M_FINGERPRINT

from bs4 import BeautifulSoup

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = "https://m.jobkorea.co.kr"


def _nhn() -> str:
    return (FIXTURES / "jobkorea_nhn_synthetic.html").read_text(encoding="utf-8")


def _empty() -> str:
    return (FIXTURES / "jobkorea_empty_synthetic.html").read_text(encoding="utf-8")


# --- job_id 도출 / URL 정규화 -------------------------------------------


def test_derive_job_id_from_site_id():
    jid = derive_job_id("/Recruit/GI_Read/45201001?Oem_Code=C1", JOBKOREA_M_FINGERPRINT, base=BASE)
    assert jid == "45201001"  # 추적 파라미터 무시하고 사이트 고유 ID


def test_derive_job_id_hash_fallback_ignores_query():
    a = derive_job_id("https://x.com/jobs/view?sess=aaa&ref=1", JOBKOREA_M_FINGERPRINT)
    b = derive_job_id("https://x.com/jobs/view?sess=bbb&ref=2", JOBKOREA_M_FINGERPRINT)
    assert a == b  # 쿼리스트링 제거 후 해시 → 동일
    assert a.startswith("u_")


def test_normalize_url_strips_query_and_trailing_slash():
    assert normalize_url("https://x.com/a/b/?q=1#frag") == "https://x.com/a/b"


# --- declared count -----------------------------------------------------


def test_parse_declared_counts_six():
    assert parse_declared(_nhn(), JOBKOREA_M_FINGERPRINT) == 6


def test_parse_declared_zero():
    assert parse_declared(_empty(), JOBKOREA_M_FINGERPRINT) == 0


def test_parse_declared_none_when_absent():
    assert parse_declared("<html>no count here</html>", JOBKOREA_M_FINGERPRINT) is None


# --- 전체 추출 ----------------------------------------------------------


def test_extract_nhn_six_items_via_link_pattern():
    declared, postings, meta = extract_with_fingerprint(_nhn(), JOBKOREA_M_FINGERPRINT, base=BASE)
    assert declared == 6
    assert meta["parsed"] == 6
    # L3 링크패턴(selector[0])에서 잡혀야 한다 (JSON-LD 없음)
    assert meta["item_layer"] == "selector[0]"
    assert meta.get("fragile", False) is False


def test_extract_populates_posting_fields():
    _, postings, _ = extract_with_fingerprint(_nhn(), JOBKOREA_M_FINGERPRINT, base=BASE)
    by_id = {p.job_id: p for p in postings}
    a = by_id["45201001"]
    assert a.title == "AI 서비스 기획자 (경력 5~10년)"
    # 표시용 URL은 원본 유지(추적 파라미터 포함), job_id만 정규화해 안정화
    assert a.url == "https://m.jobkorea.co.kr/Recruit/GI_Read/45201001?Oem_Code=C1&logpath=1"
    assert a.employment_type == "정규직"
    assert a.experience_text == "경력 5~10년"
    assert a.dept == "AI플랫폼실"


def test_extract_empty_returns_zero():
    declared, postings, meta = extract_with_fingerprint(_empty(), JOBKOREA_M_FINGERPRINT, base=BASE)
    assert declared == 0
    assert postings == []
    assert meta["parsed"] == 0


def test_extract_dedupes_same_job_id():
    # 같은 GI_Read 링크가 두 번 → 1건으로
    html = (
        '<div id="content"><ul class="list-default">'
        '<li><a class="list-post" href="/Recruit/GI_Read/999"><span class="title">A</span></a></li>'
        '<li><a class="list-post" href="/Recruit/GI_Read/999?x=1"><span class="title">A</span></a></li>'
        "</ul></div>"
    )
    _, postings, meta = extract_with_fingerprint(html, JOBKOREA_M_FINGERPRINT, base=BASE)
    assert meta["parsed"] == 1


# --- JSON-LD 계층 -------------------------------------------------------


def test_from_jsonld_jobposting():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"UX 리서처",
     "url":"/Recruit/GI_Read/7777","datePosted":"2026-08-01",
     "employmentType":"FULL_TIME",
     "experienceRequirements":{"@type":"OccupationalExperienceRequirements","monthsOfExperience":72}}
    </script>
    """
    soup = BeautifulSoup(html, "html.parser")
    posts = from_jsonld(soup, ["JobPosting", "ItemList"], BASE, JOBKOREA_M_FINGERPRINT)
    assert len(posts) == 1
    assert posts[0].title == "UX 리서처"
    assert posts[0].job_id == "7777"
    assert posts[0].experience_text == "6년"  # 72개월 → 6년


def test_extract_prefers_jsonld_layer():
    html = (
        '<div id="content"><p>총 1건</p>'
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"AI 엔지니어","url":"/Recruit/GI_Read/8888"}'
        "</script>"
        '<ul class="list-default"><li><a class="list-post" href="/Recruit/GI_Read/9999">'
        '<span class="title">낚시</span></a></li></ul></div>'
    )
    _, postings, meta = extract_with_fingerprint(html, JOBKOREA_M_FINGERPRINT, base=BASE)
    assert meta["item_layer"] == "jsonld"
    assert [p.job_id for p in postings] == ["8888"]
