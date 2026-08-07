"""BC Public Service HRSmart 어댑터 테스트 (fixture 기반)."""

from __future__ import annotations

import httpx

from opmon.adapters import hrsmart
from opmon.adapters.base import RunContext
from opmon.adapters.hrsmart import classify_and_parse, listing_url, parse_listing, run
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {"host": "bcpublicservice.hua.hrsmart.com", "path": "/hr/ats/JobSearch/search"}
BASE = listing_url(SCFG)


def _title_link(title, pid):
    return f'<a href="/hr/ats/Posting/view/{pid}">{title}</a>'


# 제목이 링크인 케이스 + 버튼("View")이 링크이고 제목은 셀인 케이스 둘 다 포함.
LISTING_HTML = "<html><body><table>" + "".join([
    f"<tr><td>{_title_link('User Experience Designer', '112738')}</td><td>Victoria</td></tr>",
    f"<tr><td>{_title_link('Service Design Specialist', '118497')}</td><td>Vancouver</td></tr>",
    # 버튼형: 제목은 plain 셀, 링크 텍스트는 'View'
    f"<tr><td>Accessibility Advisor</td><td>{_title_link('View', '120001')}</td></tr>",
    f"<tr><td>{_title_link('Financial Officer', '119000')}</td><td>Victoria</td></tr>",
]) + "</table></body></html>"


def _client(html, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, text=html)))


def test_parse_gets_titles_including_button_row():
    posts = parse_listing(LISTING_HTML, BASE)
    by_id = {p.job_id: p.title for p in posts}
    assert by_id["112738"] == "User Experience Designer"
    assert by_id["120001"] == "Accessibility Advisor"   # 버튼 링크 → 행 셀에서 제목 보완
    assert posts[0].url.startswith("https://bcpublicservice.hua.hrsmart.com/hr/ats/Posting/view/")


def test_relevance_filter_design_and_accessibility():
    outcome, meta, relevant = classify_and_parse(LISTING_HTML, BASE)
    assert outcome == Outcome.OK_WITH_RESULTS
    titles = {p.title for p in relevant}
    assert "User Experience Designer" in titles
    assert "Service Design Specialist" in titles
    assert "Accessibility Advisor" in titles
    assert "Financial Officer" not in titles


def test_empty_marker_trusted():
    html = "<html><body>No results found for your search.</body></html>"
    outcome, meta, relevant = classify_and_parse(html, BASE)
    assert outcome == Outcome.OK_EMPTY_TRUSTED and relevant == []


def test_no_anchor_no_marker_suspicious():
    html = "<html><body>" + ("x" * 3000) + "</body></html>"
    outcome, meta, _ = classify_and_parse(html, BASE)
    assert outcome == Outcome.SUSPICIOUS_EMPTY


def _company():
    return Company(id="bc_public_service", name="BC Public Service", adapter=Adapter.HRSMART)


def test_run_matches(monkeypatch):
    monkeypatch.setattr(hrsmart, "get_hrsmart_config", lambda cid: SCFG)
    with _client(LISTING_HTML) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    titles = {m.posting.title for m in res.matches}
    assert "User Experience Designer" in titles and "Accessibility Advisor" in titles


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(hrsmart, "get_hrsmart_config", lambda cid: None)
    assert run(_company(), CFG, RunContext()).skipped is True


def test_run_blocked_403(monkeypatch):
    monkeypatch.setattr(hrsmart, "get_hrsmart_config", lambda cid: SCFG)
    with _client("", status=403) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.BLOCKED
