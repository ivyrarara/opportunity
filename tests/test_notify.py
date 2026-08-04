"""5단계: 알림 포맷 · Notifier · dispatch 테스트."""

from __future__ import annotations

import httpx

from opmon.aggregate import Action
from opmon.config import load_targets
from opmon.models import PostingRecord
from opmon.notify.dispatch import send_notifications
from opmon.notify.format import build_new_posting_messages, render_posting
from opmon.notify.memory import InMemoryNotifier
from opmon.notify.telegram import TelegramNotifier
from opmon.outcomes import Outcome

CFG = load_targets()


def _rec(site, job_id, category, title, kws, highlights=None, exp_ok=True):
    return PostingRecord(
        site=site, job_id=job_id, title=title, url=f"https://x/{job_id}",
        category=category, matched_keywords=kws, highlights=highlights or [],
        min_experience_ok=exp_ok,
    )


# --- 포맷 ---------------------------------------------------------------


def test_render_posting_basic():
    r = _rec("hybe", "1", "브랜딩", "브랜딩 매니저", ["BX", "브랜드 아이덴티티"], ["영어가능"])
    out = render_posting(r, "하이브")
    assert out.splitlines()[0] == "🆕 [브랜딩] 하이브 🌐영어가능"
    assert "브랜딩 매니저" in out
    assert "매칭 키워드: BX, 브랜드 아이덴티티" in out
    assert "https://x/1" in out
    assert "⚠️경력확인필요" not in out


def test_render_posting_experience_flag():
    r = _rec("nhn", "2", "패키지/인쇄", "패키지 디자이너", ["패키지"], exp_ok=None)
    out = render_posting(r, "NHN")
    assert "⚠️경력확인필요" in out.splitlines()[1]


def test_render_posting_no_highlight():
    r = _rec("nhn", "3", "AI", "AI 기획자", ["AI"])
    assert render_posting(r, "NHN").splitlines()[0] == "🆕 [AI] NHN"


def test_build_messages_grouped_by_site():
    records = [
        _rec("nhn", "1", "AI", "AI 기획자", ["AI"]),
        _rec("nhn", "2", "브랜딩", "브랜딩 매니저", ["BX"]),
        _rec("hybe", "3", "브랜딩", "BX 리드", ["BX"]),
    ]
    msgs = build_new_posting_messages(records, CFG)
    assert len(msgs) == 2  # nhn 묶음 1 + hybe 묶음 1
    assert msgs[0].count("🆕") == 2  # nhn 2건 한 메시지
    assert "NHN" in msgs[0] and "하이브" in msgs[1]


def test_build_messages_unknown_site_uses_id():
    msgs = build_new_posting_messages([_rec("unknown_co", "1", "AI", "T", ["AI"])], CFG)
    assert "unknown_co" in msgs[0]


# --- InMemoryNotifier ---------------------------------------------------


def test_in_memory_notifier_collects():
    n = InMemoryNotifier()
    assert n.send("a") is True
    assert n.send_many(["b", "c"]) == 2
    assert n.messages == ["a", "b", "c"]


# --- dispatch -----------------------------------------------------------


def _alert(cid, text):
    return Action(kind="alert", company_id=cid, severity="warn", text=text, outcome=Outcome.BLOCKED)


def test_dispatch_sends_postings_and_alerts():
    n = InMemoryNotifier()
    records = [_rec("nhn", "1", "AI", "AI 기획자", ["AI"])]
    actions = [
        _alert("skt", "⚠️ skt 차단(blocked): 403"),
        Action(kind="log", company_id="skt", outcome=Outcome.BLOCKED, meta={}),  # 전송 안 함
    ]
    res = send_notifications(records, actions, CFG, n)
    assert res.posting_messages_sent == 1
    assert res.alert_messages_sent == 1
    assert len(n.messages) == 2  # log는 제외


def test_dispatch_seed_suppresses_postings_but_sends_alerts():
    n = InMemoryNotifier()
    records = [_rec("nhn", "1", "AI", "AI 기획자", ["AI"])]
    actions = [_alert("skt", "⚠️ skt 차단(blocked): 403")]
    res = send_notifications(records, actions, CFG, n, seed=True)
    assert res.posting_messages_sent == 0
    assert res.suppressed_by_seed == 1
    assert res.alert_messages_sent == 1  # 운영 이상 알림은 시드에서도 전송
    assert len(n.messages) == 1


# --- TelegramNotifier (MockTransport) -----------------------------------


def _tg_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_telegram_send_ok():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    with _tg_client(handler) as c:
        tg = TelegramNotifier("TOKEN", "CHAT", client=c)
        assert tg.send("hello") is True
    assert "/botTOKEN/sendMessage" in seen["url"]
    assert seen["body"]["chat_id"] == "CHAT"
    assert seen["body"]["text"] == "hello"


def test_telegram_send_http_error_returns_false():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "bad"})

    with _tg_client(handler) as c:
        tg = TelegramNotifier("T", "C", client=c)
        assert tg.send("x") is False


def test_telegram_send_transport_error_returns_false():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with _tg_client(handler) as c:
        tg = TelegramNotifier("T", "C", client=c)
        assert tg.send("x") is False


def test_telegram_requires_token():
    import pytest

    with pytest.raises(ValueError):
        TelegramNotifier("", "C")
