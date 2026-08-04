"""어댑터 레지스트리.

adapter 이름 → 러너. 여기 등록된 어댑터만 오케스트레이터가 실행하고,
미등록(generic_list/spa/greenhouse/hyundai)은 스킵한다. 8·9단계에서 등록되면 자동 합류.
"""

from __future__ import annotations

from . import jobkorea
from .base import AdapterRunner

REGISTRY: dict[str, AdapterRunner] = {
    "jobkorea": jobkorea.run,
    # "generic_list": ...   # 8단계
    # "spa": ...            # 8단계
    # "greenhouse": ...     # 8단계
    # "hyundai": ...        # 9단계
}


def get_runner(adapter_name: str) -> AdapterRunner | None:
    return REGISTRY.get(adapter_name)
