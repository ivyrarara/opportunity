"""§3 매칭·필터 판정 테스트."""

from __future__ import annotations

import pytest

from opmon.config import load_targets
from opmon.matching import (
    evaluate_experience,
    evaluate_posting,
    experience_lower_bound,
    is_excluded,
    match_categories,
    match_highlights,
)
from opmon.models import Posting

CFG = load_targets()


# --- 경력 파싱 ----------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("경력 5~10년", 5),
        ("경력 5년 이상", 5),
        ("경력 7년", 7),
        ("경력 1~3년", 1),
        ("3년 이상", 3),
        ("신입", None),
        ("경력무관", None),
        (None, None),
        ("복지 좋은 회사", None),
    ],
)
def test_experience_lower_bound(text, expected):
    assert experience_lower_bound(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("경력 5~10년", True),   # 하한 5 >= 5
        ("경력 7년", True),
        ("경력 5년 이상", True),
        ("경력 1~3년", False),   # 하한 1 < 5
        ("경력 3년 이상", False),
        ("신입", False),         # 명시 마커 → 미달
        ("경력무관", False),
        (None, None),            # 확인불가 → 포함 + 플래그
        ("우대사항: 성실함", None),
    ],
)
def test_evaluate_experience(text, expected):
    assert evaluate_experience(text, CFG.min_experience_years) == expected


# --- 제외어 (제목 + 고용형태만) -----------------------------------------


def test_is_excluded_by_employment_type():
    p = Posting(job_id="1", title="UX 디자이너 채용", url="u", employment_type="계약직")
    assert is_excluded(p, CFG.exclude_keywords) == "계약직"


def test_is_excluded_by_title():
    p = Posting(job_id="1", title="단기 그래픽 디자이너", url="u", employment_type="정규직")
    assert is_excluded(p, CFG.exclude_keywords) == "단기"


def test_not_excluded_when_only_in_dept():
    # 제외어가 부서/상세에만 있으면 제외하지 않음 (본문 오탐 방지, §2-3)
    p = Posting(job_id="1", title="UX 디자이너", url="u", employment_type="정규직", dept="계약직관리팀")
    assert is_excluded(p, CFG.exclude_keywords) is None


# --- 카테고리 / 하이라이트 ----------------------------------------------


def test_match_categories_ai():
    cat, kws = match_categories("AI 서비스 기획자", CFG)
    assert cat == "AI"
    assert "AI" in kws


def test_match_categories_none():
    cat, kws = match_categories("재무 회계 담당자", CFG)
    assert cat is None
    assert kws == []


def test_match_highlights_english():
    assert match_highlights("경력 8년, 비즈니스 영어 가능", CFG) == ["영어가능"]


# --- evaluate_posting 통합 ----------------------------------------------


def test_evaluate_match_ok():
    p = Posting(job_id="1", title="AI 서비스 기획자", url="u",
                employment_type="정규직", experience_text="경력 5~10년")
    r = evaluate_posting(p, CFG)
    assert r is not None
    assert r.category == "AI"
    assert r.min_experience_ok is True


def test_evaluate_excluded_returns_none():
    p = Posting(job_id="1", title="UX 디자이너", url="u", employment_type="계약직",
                experience_text="경력 5년 이상")
    assert evaluate_posting(p, CFG) is None


def test_evaluate_experience_below_returns_none():
    p = Posting(job_id="1", title="브랜드 디자이너", url="u", employment_type="정규직",
                experience_text="신입")
    assert evaluate_posting(p, CFG) is None


def test_evaluate_experience_unknown_flags():
    p = Posting(job_id="1", title="시니어 패키지 디자이너", url="u",
                employment_type="정규직", dept="인쇄 감리팀")
    r = evaluate_posting(p, CFG)
    assert r is not None
    assert r.category == "패키지/인쇄"
    assert r.min_experience_ok is None  # ⚠️경력확인필요


def test_evaluate_no_category_returns_none():
    p = Posting(job_id="1", title="재무 회계 담당자", url="u",
                employment_type="정규직", experience_text="경력 7년")
    assert evaluate_posting(p, CFG) is None


def test_evaluate_branding_with_highlight():
    p = Posting(job_id="1", title="브랜딩 매니저 (BX)", url="u",
                employment_type="정규직", experience_text="경력 8년, 비즈니스 영어 가능")
    r = evaluate_posting(p, CFG)
    assert r is not None
    assert r.category == "브랜딩"
    assert "영어가능" in r.highlights


def test_short_acronym_no_substring_false_positive():
    # 대문자 약어가 큰 단어 속에 substring 오탐되면 안 됨(실측 사례).
    #   "AI" ⊄ "AIA"(보험)·"AICC"(콜센터)
    assert match_categories("AIA 퍼미션센터 상담원 모집", CFG) == (None, [])
    assert match_categories("BC카드 AICC 특수파트 환경미화 보조", CFG) == (None, [])
    # 그러나 경계가 성립하는 정상 표기는 매칭돼야 함.
    cat, mk = match_categories("생성형 AI 디자인", CFG)
    assert cat == "AI" and "AI" in mk
    cat2, mk2 = match_categories("AI기획 담당", CFG)  # 한글 인접 허용
    assert cat2 == "AI" and "AI" in mk2
