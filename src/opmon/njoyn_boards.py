"""Njoyn(CGI) 채용포털 설정 — 온타리오 지자체 등.

Njoyn은 서버렌더 HTML(ASP)이라 표준 JSON API가 없다. 목록 페이지를 받아
상세 링크(`Page=JobDetails&Jobid=...`) 앵커를 href 패턴으로 뽑는다(클래스 비의존 → 개편에 강함).

  목록: https://{host}/cl4/xweb/xweb.asp?page=joblisting&clid={clid}&lang={lang}
  상세: ...&Page=JobDetails&Jobid=J0726-0469&BRID=...&lang=1  (tbtoken/chk는 세션값)

company id로 키잉. 없으면(=미설정) 어댑터가 skip.
"""

from __future__ import annotations

from typing import Any

NJOYN_BOARDS: dict[str, dict[str, Any]] = {
    # City of Vaughan — 집 앞. clid는 상세 URL에서 확정(clid=74035).
    "vaughan": {
        "host": "cityofvaughan.njoyn.com",
        "clid": "74035",
        "lang": "1",
    },
}


def get_njoyn_config(company_id: str) -> dict[str, Any] | None:
    return NJOYN_BOARDS.get(company_id)
