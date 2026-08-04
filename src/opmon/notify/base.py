"""전송 추상화 (명세 §9)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    """알림 전송 인터페이스. 텍스트 메시지 1건을 보낸다."""

    @abstractmethod
    def send(self, text: str) -> bool:
        """전송 성공 여부를 반환. 실패해도 예외로 파이프라인을 죽이지 않는다."""

    def send_many(self, texts: list[str]) -> int:
        """여러 메시지 전송. 성공 건수 반환."""
        return sum(1 for t in texts if self.send(t))
