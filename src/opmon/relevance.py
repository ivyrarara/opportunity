"""제목 관련성 판정 — '디자인 또는 접근성' 직군만 통과.

지자체·공공·대형 브랜드 포털은 전 직군을 올리므로, 제목에 디자인 또는 접근성
토큰이 있는 공고만 남겨 노이즈를 줄인다(njoyn/lever/hrsmart 공용).
"""

from __future__ import annotations

DESIGN_TOKENS = (
    "designer", "design", "graphic", "visual", "packaging",
    "art direction", "art director", "illustrat", "creative", "brand",
    "ux", "ui", "motion", "multimedia",
)
ACCESS_TOKENS = ("accessib", "aoda", "wcag", "inclusive", "a11y")


def is_design_or_access(title: str) -> bool:
    t = (title or "").lower()
    return any(tok in t for tok in DESIGN_TOKENS) or any(tok in t for tok in ACCESS_TOKENS)
