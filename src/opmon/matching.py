"""키워드 매칭 · 필터 판정 (명세 §3, §2).

판정 순서:
  ① exclude_keywords (제목 + 고용형태 필드로만) 매칭 시 즉시 제외
  ② min_experience_years 미만 요구 공고 제외 (경력 못 찾으면 포함 + 플래그)
  ③ 남은 공고 중 제목·상세에 카테고리 키워드가 하나라도 있으면 대상
매칭 키워드·카테고리는 함께 반환(알림 표시용).
"""

from __future__ import annotations

import re

from .config import TargetsConfig
from .models import MatchResult, Posting

# 경력 텍스트에서 하한 연차를 뽑기 위한 패턴들.
_RANGE_RE = re.compile(r"(\d+)\s*[~∼\-–]\s*(\d+)\s*년")  # "5~10년"
_MIN_RE = re.compile(r"(\d+)\s*년\s*이상")  # "5년 이상"
_SINGLE_RE = re.compile(r"경력\s*(\d+)\s*년")  # "경력 7년"
_ANY_YEAR_RE = re.compile(r"(\d+)\s*년")  # 최후: 아무 "N년"
# 경력을 확실히 '5년 미만'으로 만드는 명시 마커.
_LOW_MARKERS = ("신입", "경력무관", "경력 무관")


def experience_lower_bound(text: str | None) -> int | None:
    """경력 텍스트에서 요구 하한 연차를 추출. 못 찾으면 None.

    범위는 하한값, "N년 이상"은 N, "경력 N년"은 N을 하한으로 본다.
    """
    if not text:
        return None
    m = _RANGE_RE.search(text)
    if m:
        return int(m.group(1))
    m = _MIN_RE.search(text)
    if m:
        return int(m.group(1))
    m = _SINGLE_RE.search(text)
    if m:
        return int(m.group(1))
    m = _ANY_YEAR_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def evaluate_experience(text: str | None, min_years: int) -> bool | None:
    """경력 조건 판정 (§2-1).

    반환: True(충족) / False(미달 → 제외) / None(확인불가 → 포함하되 플래그).
    - 하한 연차를 찾으면 min_years와 비교.
    - "신입"/"경력무관" 등 명시 마커는 미달(False).
    - 아무 정보도 못 찾으면 None.
    """
    lb = experience_lower_bound(text)
    if lb is not None:
        return lb >= min_years
    if text:
        low = text.replace(" ", "")
        if any(marker.replace(" ", "") in low for marker in _LOW_MARKERS):
            return False
    return None


def is_excluded(posting: Posting, exclude_keywords: list[str]) -> str | None:
    """exclude_keywords 매칭 시 매칭된 키워드 반환, 아니면 None (§2-3).

    판정 대상: 제목 + 고용형태 필드만 (본문 전체 금지).
    """
    text = posting.filter_text()
    for kw in exclude_keywords:
        if kw and kw in text:
            return kw
    return None


# 짧은 ASCII 약어는 큰 단어 속에 substring으로 오탐된다(대소문자 구분 매칭이라
# 대문자 약어가 문제): "AI"→"AIA"(보험)·"AICC"(콜센터), "CI"→"SOCIAL"·"OFFICIAL",
# "UI"→"GUIDE". 이들은 앞뒤가 ASCII 글자가 아닐 때만(공백·기호·한글·숫자 경계) 매칭한다.
# 한글 인접("AI기획")은 허용, 라틴 단어 내부("AIA")는 차단.
_BOUNDARY_KEYWORDS = frozenset({"AI", "UI", "UX", "BI", "CI", "HMI"})


def _kw_in(kw: str, text: str) -> bool:
    if kw in _BOUNDARY_KEYWORDS:
        return re.search(r"(?<![A-Za-z])" + re.escape(kw) + r"(?![A-Za-z])", text) is not None
    return kw in text


def match_categories(text: str, cfg: TargetsConfig) -> tuple[str | None, list[str]]:
    """카테고리 키워드 매칭. (첫 매칭 카테고리, 매칭된 키워드 전체) 반환.

    여러 카테고리에 걸치면 keyword_sets 순서상 먼저 오는 카테고리를 대표로 삼되,
    매칭 키워드는 모두 모은다(알림 표시용).
    """
    matched: list[str] = []
    primary: str | None = None
    for ks in cfg.keyword_sets:
        for kw in ks.keywords:
            if _kw_in(kw, text):
                matched.append(kw)
                if primary is None:
                    primary = ks.category
    return primary, matched


def match_highlights(text: str, cfg: TargetsConfig) -> list[str]:
    """하이라이트 태그 매칭 (필터 아님, 표시용)."""
    tags: list[str] = []
    for ht in cfg.highlight_tags:
        if any(kw in text for kw in ht.keywords):
            tags.append(ht.tag)
    return tags


def evaluate_posting(posting: Posting, cfg: TargetsConfig) -> MatchResult | None:
    """공고 1건에 §3 판정 순서를 적용. 대상이면 MatchResult, 아니면 None."""
    # ① 제외어
    if is_excluded(posting, cfg.exclude_keywords) is not None:
        return None

    # ② 경력
    exp_ok = evaluate_experience(posting.experience_text, cfg.min_experience_years)
    if exp_ok is False:
        return None

    # ③ 카테고리 키워드
    text = posting.match_text()
    category, matched = match_categories(text, cfg)
    if category is None:
        return None

    return MatchResult(
        posting=posting,
        category=category,
        matched_keywords=matched,
        highlights=match_highlights(text, cfg),
        min_experience_ok=exp_ok,  # True 또는 None(확인불가)
    )
