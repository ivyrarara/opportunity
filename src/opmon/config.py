"""targets.json 로더 + 스키마 검증.

기회 모니터링의 대상 회사/키워드/필터 설정을 코드에서 분리해 로드한다.
스키마는 pydantic으로 엄격 검증한다 (알 수 없는 필드 거부, id 중복 검사 등).

명세 §3(설정 구조) · §11(대상 회사)에 대응한다.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# 패키지에 동봉된 기본 설정 (설치본에서도 동작). 커스텀은 OPMON_TARGETS env 또는 인자로.
_PACKAGED_TARGETS = Path(__file__).resolve().parent / "data" / "targets.json"


def _default_targets_path() -> Path:
    """기본 targets.json 경로 해석: env(OPMON_TARGETS) → 패키지 동봉본."""
    env = os.getenv("OPMON_TARGETS")
    if env:
        return Path(env)
    return _PACKAGED_TARGETS


DEFAULT_TARGETS_PATH = _PACKAGED_TARGETS  # 하위호환 (직접 참조하는 코드용)


class ConfigError(Exception):
    """설정 파일이 없거나, JSON이 깨졌거나, 스키마 검증에 실패했을 때."""


class Adapter(str, Enum):
    """어댑터 유형 (명세 §4)."""

    JOBKOREA = "jobkorea"
    GENERIC_LIST = "generic_list"
    GREENHOUSE = "greenhouse"
    SPA = "spa"
    HYUNDAI = "hyundai"
    WORKDAY = "workday"
    NJOYN = "njoyn"
    LEVER = "lever"
    HRSMART = "hrsmart"
    NETFLIX = "netflix"
    BAMBOOHR = "bamboohr"


class Mode(str, Enum):
    """어댑터 접근 경로. SPA/ATS 계열에서 API 직행인지 렌더인지 힌트 (명세 §7)."""

    API = "api"
    RENDER = "render"


class Company(BaseModel):
    """감시 대상 회사 1곳 (명세 §11)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    adapter: Adapter
    mode: Mode | None = None
    urls: list[str] = Field(default_factory=list)
    brand_filter: str | None = None
    fingerprint: str | None = None
    notes: str | None = None
    # 실패 허용 회사(예: 현대차 NetFunnel §4). 실패가 전체차단 비율을 오염시키지 않고 알림도 억제.
    failure_tolerant: bool = False


class KeywordSet(BaseModel):
    """카테고리별 매칭 키워드 묶음 (명세 §3)."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1)
    keywords: list[str] = Field(min_length=1)


class HighlightTag(BaseModel):
    """표시용 하이라이트 태그. 필터가 아니라 알림에 붙이는 라벨 (예: 영어가능)."""

    model_config = ConfigDict(extra="forbid")

    tag: str = Field(min_length=1)
    keywords: list[str] = Field(min_length=1)


class TargetsConfig(BaseModel):
    """targets.json 전체 스키마."""

    model_config = ConfigDict(extra="forbid")

    companies: list[Company] = Field(min_length=1)
    keyword_sets: list[KeywordSet] = Field(min_length=1)
    highlight_tags: list[HighlightTag] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    min_experience_years: int = Field(ge=0)

    @field_validator("companies")
    @classmethod
    def _unique_company_ids(cls, companies: list[Company]) -> list[Company]:
        seen: set[str] = set()
        dups: list[str] = []
        for c in companies:
            if c.id in seen:
                dups.append(c.id)
            seen.add(c.id)
        if dups:
            raise ValueError(f"중복된 company id: {sorted(set(dups))}")
        return companies

    @field_validator("keyword_sets")
    @classmethod
    def _unique_categories(cls, sets: list[KeywordSet]) -> list[KeywordSet]:
        seen: set[str] = set()
        dups: list[str] = []
        for ks in sets:
            if ks.category in seen:
                dups.append(ks.category)
            seen.add(ks.category)
        if dups:
            raise ValueError(f"중복된 keyword_set category: {sorted(set(dups))}")
        return sets

    @model_validator(mode="after")
    def _mode_matches_adapter(self) -> TargetsConfig:
        # jobkorea/generic_list는 정적이라 mode를 두지 않는다. spa/greenhouse만 api|render 힌트를 가진다.
        static_adapters = {
            Adapter.JOBKOREA, Adapter.GENERIC_LIST, Adapter.HYUNDAI,
            Adapter.WORKDAY, Adapter.NJOYN, Adapter.LEVER, Adapter.HRSMART,
            Adapter.NETFLIX, Adapter.GREENHOUSE, Adapter.BAMBOOHR,
        }
        for c in self.companies:
            if c.mode is not None and c.adapter in static_adapters:
                raise ValueError(
                    f"company '{c.id}': adapter '{c.adapter.value}'에는 mode를 지정할 수 없습니다 "
                    f"(mode는 spa/greenhouse 전용)"
                )
        return self

    # --- 조회 헬퍼 -------------------------------------------------------

    def get_company(self, company_id: str) -> Company:
        for c in self.companies:
            if c.id == company_id:
                return c
        raise KeyError(company_id)

    def companies_by_adapter(self, adapter: Adapter) -> list[Company]:
        return [c for c in self.companies if c.adapter == adapter]

    def all_keywords(self) -> dict[str, str]:
        """키워드 → 카테고리 매핑 (매칭 시 카테고리 역참조용)."""
        mapping: dict[str, str] = {}
        for ks in self.keyword_sets:
            for kw in ks.keywords:
                mapping[kw] = ks.category
        return mapping


def load_targets(path: str | Path | None = None) -> TargetsConfig:
    """targets.json을 읽어 검증된 TargetsConfig로 반환한다.

    파일 부재 · JSON 파싱 오류 · 스키마 위반은 모두 ConfigError로 감싸 던진다.
    """
    p = Path(path) if path is not None else _default_targets_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {p}") from exc
    except OSError as exc:  # 권한/IO 오류 등
        raise ConfigError(f"설정 파일을 읽을 수 없습니다: {p} ({exc})") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"설정 JSON 파싱 실패: {p} ({exc})") from exc

    try:
        return TargetsConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"설정 스키마 검증 실패: {p}\n{exc}") from exc


@lru_cache(maxsize=1)
def get_targets() -> TargetsConfig:
    """기본 경로 설정을 1회 로드해 캐시한다."""
    return load_targets()


def _summary(cfg: TargetsConfig) -> str:
    from collections import Counter

    by_adapter = Counter(c.adapter.value for c in cfg.companies)
    lines = [
        f"companies: {len(cfg.companies)}",
        "  by adapter: " + ", ".join(f"{k}={v}" for k, v in sorted(by_adapter.items())),
        f"keyword_sets: {len(cfg.keyword_sets)} "
        f"({', '.join(ks.category for ks in cfg.keyword_sets)})",
        f"keywords total: {len(cfg.all_keywords())}",
        f"highlight_tags: {[t.tag for t in cfg.highlight_tags]}",
        f"exclude_keywords: {cfg.exclude_keywords}",
        f"min_experience_years: {cfg.min_experience_years}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    try:
        config = load_targets(sys.argv[1] if len(sys.argv) > 1 else None)
    except ConfigError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        raise SystemExit(1)
    print("[OK] targets.json 로드 및 검증 성공\n")
    print(_summary(config))
