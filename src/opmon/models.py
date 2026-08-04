"""공통 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Posting:
    """공고 1건 (어댑터 공통 반환 단위, 명세 §4).

    experience_text / employment_type는 사이트가 주면 채우고, 없으면 None.
    """

    job_id: str
    title: str
    url: str
    posted_date: str | None = None
    dept: str | None = None
    employment_type: str | None = None
    experience_text: str | None = None

    def filter_text(self) -> str:
        """exclude_keywords 판정 대상 텍스트 (제목 + 고용형태 필드만, §2-3)."""
        parts = [self.title]
        if self.employment_type:
            parts.append(self.employment_type)
        return " ".join(parts)

    def match_text(self) -> str:
        """카테고리/하이라이트 키워드 매칭 대상 텍스트 (제목 + 상세 필드)."""
        parts = [self.title]
        for extra in (self.dept, self.employment_type, self.experience_text):
            if extra:
                parts.append(extra)
        return " ".join(parts)


@dataclass
class MatchResult:
    """evaluate_posting 결과 (알림/저장용, 명세 §3·§8-1)."""

    posting: Posting
    category: str
    matched_keywords: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    # 경력조건 충족 여부: True/False, 확인불가면 None → 알림에 ⚠️경력확인필요
    min_experience_ok: bool | None = None
