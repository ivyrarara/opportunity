"""알림 계층 (명세 §9).

포맷 렌더(format) + 전송 추상화(base) + 인메모리(memory) + 텔레그램(telegram) + dispatch.
봇 토큰은 env로만 주입한다(§1 격리). 실제 봇 생성은 배포 시점(§12).
"""

from .base import Notifier
from .memory import InMemoryNotifier

__all__ = ["Notifier", "InMemoryNotifier"]
