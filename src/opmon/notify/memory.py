"""인메모리 Notifier (테스트·드라이런). 전송 대신 수집만."""

from __future__ import annotations

from .base import Notifier


class InMemoryNotifier(Notifier):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> bool:
        self.messages.append(text)
        return True
