"""Vaughan Njoyn 어댑터 테스트 (fixture 기반, 네트워크 없음)."""

from __future__ import annotations

import httpx

from opmon.adapters import njoyn
from opmon.adapters.base import RunContext
from opmon.adapters.njoyn import classify_and_parse, listing_url, parse_listing, run
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {"host": "cityofvaughan.njoyn.com", "clid": "74035", "lang": "1"}
BASE = listing_url(SCFG)


def _link(text, jobid):
    return (
        f'<a href="xweb.asp?clid=74035&Page=JobDetails&Jobid={jobid}'
        f'&BRID=453711&lang=1">{text}</a>'
    )


def _row(title, jobid, dept="General", etype="Permanent Full Time"):
    """실제 Njoyn 행 구조: [ID(링크), 제목(plain), 부서, 고용형태, 게시일, 마감일,
    View Job Details(링크)]. ID·버튼만 jobdetails 링크이고 제목은 plain text."""
    return (
        "<tr>"
        f"<td>{_link(jobid, jobid)}</td>"
        f"<td>{title}</td>"
        f"<td>{dept}</td>"
        f"<td>{etype}</td>"
        "<td>August 4, 2026</td>"
        "<td>August 25, 2026</td>"
        f"<td>{_link('View Job Details', jobid)}</td>"
        "</tr>"
    )


LISTING_HTML = "<html><body><table>" + "".join([
    _row("Coordinator, Marketing, Creative and Production Services", "J0726-0469"),
    # 짧은 제목 — 옛 '가장 긴 셀' 방식이면 'Permanent Full Time'으로 오판했을 케이스.
    _row("UX Designer", "J0726-0470", dept="IT"),
    _row("Accessibility Advisor", "J0726-0471", dept="Corporate"),
    _row("Firefighter", "J0726-0472", dept="Fire"),
    _row("Corporate Financial Analyst", "J0726-0473", dept="Finance"),
]) + "</table></body></html>"


def _client(html, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, text=html)))


# --- parse / classify ----------------------------------------------------


def test_parse_extracts_all_jobdetails_anchors():
    posts = parse_listing(LISTING_HTML, BASE)
    assert len(posts) == 5
    p = posts[0]
    assert p.job_id == "J0726-0469"
    # 제목이 ID 셀 링크(J0726-0469)가 아니라 실제 제목으로 잡혀야 한다.
    assert p.title == "Coordinator, Marketing, Creative and Production Services"
    assert p.url.startswith("https://cityofvaughan.njoyn.com/cl4/xweb/xweb.asp?")
    assert "Page=JobDetails" in p.url


def test_relevance_filter_keeps_design_and_accessibility():
    outcome, meta, relevant = classify_and_parse(LISTING_HTML, BASE)
    assert outcome == Outcome.OK_WITH_RESULTS
    assert meta["anchors"] == 5 and meta["relevant"] == 3
    titles = {p.title for p in relevant}
    assert "Firefighter" not in titles and "Corporate Financial Analyst" not in titles
    assert "UX Designer" in titles and "Accessibility Advisor" in titles


def test_empty_marker_is_trusted_empty():
    html = "<html><body>There are currently no opportunities available.</body></html>"
    outcome, meta, relevant = classify_and_parse(html, BASE)
    assert outcome == Outcome.OK_EMPTY_TRUSTED and relevant == []


def test_no_anchor_no_marker_is_suspicious():
    html = "<html><body>" + ("x" * 3000) + "</body></html>"
    outcome, meta, _ = classify_and_parse(html, BASE)
    assert outcome == Outcome.SUSPICIOUS_EMPTY


def test_tiny_body_no_anchor_is_blocked():
    outcome, meta, _ = classify_and_parse("<html></html>", BASE)
    assert outcome == Outcome.BLOCKED


# --- run -----------------------------------------------------------------


def _company():
    return Company(id="vaughan", name="City of Vaughan", adapter=Adapter.NJOYN)


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(njoyn, "get_njoyn_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True


def test_run_matches_design_and_accessibility(monkeypatch):
    monkeypatch.setattr(njoyn, "get_njoyn_config", lambda cid: SCFG)
    with _client(LISTING_HTML) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["relevant"] == 3
    titles = {m.posting.title for m in res.matches}
    assert "UX Designer" in titles
    assert "Accessibility Advisor" in titles
    assert "Coordinator, Marketing, Creative and Production Services" in titles


def test_run_blocked_on_403(monkeypatch):
    monkeypatch.setattr(njoyn, "get_njoyn_config", lambda cid: SCFG)
    with _client("", status=403) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.BLOCKED
