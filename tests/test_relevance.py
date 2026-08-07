"""공용 관련성 필터 — 실측에서 나온 오탐을 회귀 방지로 고정."""

from __future__ import annotations

import pytest

from opmon.relevance import is_design_or_access

# 통과해야 하는 진짜 디자인/접근성 제목
KEEP = [
    "User Experience Designer",
    "Service Design Specialist",
    "Senior Brand Designer",
    "Associate Graphic Designer",
    "Coordinator, Marketing, Creative and Production Services",
    "Accessibility Advisor",
    "Digital Accessibility Lead (AODA/WCAG)",
    "Packaging Designer",
    "Art Director",
    "UX/UI Designer",
    "Brand Experience Manager",
]

# 걸러야 하는 오탐 (실측: Arc'teryx·BC Public Service·Canada Goose)
DROP = [
    "Senior Legal Counsel - Brand & Commercial",
    "LSO 5 DPE - Senior Engineering Manager, Highway Design Services",
    "LSO 4 DPE - Senior Highway Design Engineer",
    "Global Brand Management Coordinator",
    "Senior Manager, Brand Media - NAM",
    "Visual Merchandising Planner - NAM",
    "Brand Ambassador Experience",
    "Manager, Advanced Analytics & BI",
    "Project Specialist, Creative Strategy",
    "P&C Business Partner - Creative, Merch, Footwear",
    "Facility Operator I",
    "Auxiliary Nursing Assistant",   # 'ux' 부분문자열 오탐 방지
    "Building Maintenance Worker",   # 'ui' 부분문자열 오탐 방지
]


@pytest.mark.parametrize("title", KEEP)
def test_keeps_design_and_accessibility(title):
    assert is_design_or_access(title) is True


@pytest.mark.parametrize("title", DROP)
def test_drops_non_design(title):
    assert is_design_or_access(title) is False
