"""알림 포맷 렌더링 (명세 §9).

포맷:
  🆕 [브랜딩] 위버스컴퍼니 🌐영어가능
  {제목}
  매칭 키워드: BX, 브랜드 아이덴티티
  {링크}

- 영어가능 등 하이라이트 태그는 매칭 시만.
- 경력조건 못 찾으면 제목 줄에 ⚠️경력확인필요.
- 여러 건은 사이트별로 묶어 한 메시지로.
"""

from __future__ import annotations

from collections import OrderedDict

from ..config import TargetsConfig
from ..models import PostingRecord

# 하이라이트 태그 → 이모지 접두 (표시용)
_HIGHLIGHT_EMOJI = {"영어가능": "🌐"}


def _highlight_str(highlights: list[str]) -> str:
    parts = [f"{_HIGHLIGHT_EMOJI.get(h, '')}{h}" for h in highlights]
    return (" " + " ".join(parts)) if parts else ""


def render_posting(record: PostingRecord, company_name: str) -> str:
    """공고 1건 블록 (§9)."""
    header = f"🆕 [{record.category}] {company_name}{_highlight_str(record.highlights)}"
    exp_flag = "  ⚠️경력확인필요" if record.min_experience_ok is None else ""
    title_line = f"{record.title}{exp_flag}"
    kw_line = f"매칭 키워드: {', '.join(record.matched_keywords)}" if record.matched_keywords else "매칭 키워드: -"
    return "\n".join([header, title_line, kw_line, record.url])


def render_site_message(company_name: str, records: list[PostingRecord]) -> str:
    """한 사이트의 여러 공고를 하나의 메시지로 (블록 사이 빈 줄)."""
    return "\n\n".join(render_posting(r, company_name) for r in records)


def build_new_posting_messages(
    new_records: list[PostingRecord], cfg: TargetsConfig
) -> list[str]:
    """신규 공고를 사이트별로 묶어 메시지 목록으로. 입력 순서 보존."""
    by_site: "OrderedDict[str, list[PostingRecord]]" = OrderedDict()
    for r in new_records:
        by_site.setdefault(r.site, []).append(r)

    messages: list[str] = []
    for site, recs in by_site.items():
        try:
            name = cfg.get_company(site).name
        except KeyError:
            name = site
        messages.append(render_site_message(name, recs))
    return messages
