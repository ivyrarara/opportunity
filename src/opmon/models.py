"""공통 데이터 모델."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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


@dataclass
class PostingRecord:
    """Firestore `postings` 문서 (명세 §8-1). 중복 판단 키는 site + job_id."""

    site: str                       # 회사 id (§11)
    job_id: str                     # 사이트 고유 ID 우선, 없으면 정규화 URL 해시
    title: str
    url: str
    category: str                   # UX/HMI|AI|접근성|브랜딩|패키지/인쇄
    posted_date: str | None = None
    matched_keywords: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)  # 표시용, 필터 아님
    min_experience_ok: bool | None = None                # 확인 불가면 None
    first_seen: float | None = None                      # 저장 시각(epoch)

    @property
    def doc_id(self) -> str:
        """`site + job_id` 조합 문서 ID (사이트 개편에도 안정)."""
        return f"{self.site}__{self.job_id}"

    def to_document(self) -> dict:
        return asdict(self)

    @classmethod
    def from_document(cls, data: dict) -> "PostingRecord":
        fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in fields})

    @classmethod
    def from_match(cls, mr: "MatchResult", site: str) -> "PostingRecord":
        return cls(
            site=site,
            job_id=mr.posting.job_id,
            title=mr.posting.title,
            url=mr.posting.url,
            category=mr.category,
            posted_date=mr.posting.posted_date,
            matched_keywords=list(mr.matched_keywords),
            highlights=list(mr.highlights),
            min_experience_ok=mr.min_experience_ok,
        )
