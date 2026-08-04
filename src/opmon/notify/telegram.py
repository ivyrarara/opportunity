"""텔레그램 Notifier (명세 §9, §1 격리).

신규 봇(BotFather)·중립적 이름은 배포 시점(§12)에 발급한다.
토큰/챗ID는 env로만 주입한다(코드/레포에 금지):
  OPMON_TELEGRAM_TOKEN, OPMON_TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import os

import httpx

from .base import Notifier

API_BASE = "https://api.telegram.org"


class TelegramNotifier(Notifier):
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
        api_base: str = API_BASE,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("텔레그램 token/chat_id가 필요합니다 (env 주입).")
        self._token = token
        self._chat_id = chat_id
        self._api_base = api_base
        self._own_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    @classmethod
    def from_env(cls, *, client: httpx.Client | None = None) -> "TelegramNotifier":
        token = os.environ.get("OPMON_TELEGRAM_TOKEN", "")
        chat_id = os.environ.get("OPMON_TELEGRAM_CHAT_ID", "")
        return cls(token, chat_id, client=client)

    def send(self, text: str) -> bool:
        url = f"{self._api_base}/bot{self._token}/sendMessage"
        try:
            resp = self._client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
        except httpx.HTTPError:
            return False
        if resp.status_code != 200:
            return False
        try:
            return bool(resp.json().get("ok"))
        except (ValueError, KeyError):
            return False

    def close(self) -> None:
        if self._own_client:
            self._client.close()
