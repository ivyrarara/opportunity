"""제목 관련성 판정 — '디자인 또는 접근성' 직군만 통과 (공용).

지자체·공공·대형 브랜드 포털은 전 직군을 올린다. 순진하게 "design"/"brand"/"visual"
같은 넓은 부분문자열로 거르면 법무(Brand & Commercial), 인사(Creative Business
Partner), 토목(Highway Design), 마케팅(Brand Media)까지 걸린다.

그래서 오탐이 적은 '단어/구절'만 통과시킨다:
 - 단어: designer, graphic, packaging, illustrat…, creative, branding, typograph, multimedia
 - 구절: "service design", "brand experience", "graphic design", "art direction" 등
 - 접근성: accessib, aoda, wcag, inclusive, a11y …
 - UX/UI: 단어 경계로만( \bux\b / \bui\b — 'auxiliary' 같은 오탐 방지)

njoyn/lever/hrsmart/workday 어댑터가 매칭 전에 공용으로 쓴다.
"""

from __future__ import annotations

import re

_WORD_TOKENS = (
    "designer",       # UX/Graphic/Brand/Product Designer
    "graphic",        # graphic design(er)
    "packaging",
    "illustrat",      # illustrator / illustration
    "typograph",
    "creative",       # creative director/services/production
    "multimedia",
    "branding",
)
_PHRASE_TOKENS = (
    "brand design", "brand experience", "service design", "product design",
    "experience design", "communication design", "web design", "motion design",
    "visual design", "graphic design", "design system", "design lead",
    "design manager", "design director", "design specialist", "design strategist",
    "art direction", "art director", "creative direction", "motion graphic",
    "ux design", "ui design", "ux/ui", "ui/ux",
)
_ACCESS_TOKENS = ("accessib", "aoda", "wcag", "inclusive", "a11y", "barrier-free", "assistive")
_UXUI_RE = re.compile(r"\b(?:ux|ui)\b", re.IGNORECASE)


def is_design_or_access(title: str) -> bool:
    t = (title or "").lower()
    if any(w in t for w in _WORD_TOKENS):
        return True
    if any(p in t for p in _PHRASE_TOKENS):
        return True
    if any(a in t for a in _ACCESS_TOKENS):
        return True
    return bool(_UXUI_RE.search(t))
