"""알림 디스패치 (명세 §9).

신규 공고 메시지(사이트별 묶음) + aggregator alert 메시지를 Notifier로 보낸다.

seed=True(시드 모드, §2-2/§10-7)면 공고 알림은 억제하고 DB만 채운 것으로 간주한다.
단 운영 이상 alert(차단/의심 등)는 시드 모드에서도 보낸다 — 초기 접근 문제를 놓치지 않기 위함.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..aggregate import Action
from ..config import TargetsConfig
from ..models import PostingRecord
from .base import Notifier
from .format import build_new_posting_messages


@dataclass
class DispatchResult:
    posting_messages_sent: int = 0
    alert_messages_sent: int = 0
    suppressed_by_seed: int = 0


def send_notifications(
    new_records: list[PostingRecord],
    actions: list[Action],
    cfg: TargetsConfig,
    notifier: Notifier,
    *,
    seed: bool = False,
) -> DispatchResult:
    result = DispatchResult()

    posting_messages = build_new_posting_messages(new_records, cfg)
    if seed:
        result.suppressed_by_seed = len(posting_messages)
    else:
        result.posting_messages_sent = notifier.send_many(posting_messages)

    alert_texts = [a.text for a in actions if a.kind == "alert" and a.text]
    result.alert_messages_sent = notifier.send_many(alert_texts)

    return result
