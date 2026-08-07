"""어댑터 레지스트리.

adapter 이름 → 러너. 여기 등록된 어댑터만 오케스트레이터가 실행하고,
미등록(generic_list/spa/greenhouse/hyundai)은 스킵한다. 8·9단계에서 등록되면 자동 합류.
"""

from __future__ import annotations

from . import hyundai, jobkorea, njoyn, spa, workday
from .base import AdapterRunner

REGISTRY: dict[str, AdapterRunner] = {
    "jobkorea": jobkorea.run,
    "spa": spa.run,             # §7 — config(SPA_FINGERPRINTS) 없는 회사는 어댑터가 skip
    "greenhouse": spa.run,      # ATS는 SPA api 경로 재사용 (§7-1). config로 board만 다르게
    "hyundai": hyundai.run,     # §9 — NetFunnel 대기열, 실패 허용(config failure_tolerant)
    "workday": workday.run,     # 토론토 — Workday CXS POST API. config(WORKDAY_BOARDS) 없으면 skip
    "njoyn": njoyn.run,         # 지자체(Vaughan 등) — Njoyn HTML 목록. config(NJOYN_BOARDS) 없으면 skip
    # "generic_list": ...   # 후속 (SKT/젠틀몬스터/아모레)
}


def get_runner(adapter_name: str) -> AdapterRunner | None:
    return REGISTRY.get(adapter_name)
