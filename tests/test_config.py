"""config 로더 · 스키마 검증 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opmon.config import (
    Adapter,
    Company,
    ConfigError,
    Mode,
    TargetsConfig,
    load_targets,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = REPO_ROOT / "src" / "opmon" / "data" / "targets.json"


def _minimal_config() -> dict:
    """검증을 통과하는 최소 설정 딕셔너리."""
    return {
        "companies": [
            {"id": "nhn", "name": "NHN", "adapter": "jobkorea", "brand_filter": "엔에이치엔"},
        ],
        "keyword_sets": [
            {"category": "AI", "keywords": ["AI", "LLM"]},
        ],
        "highlight_tags": [
            {"tag": "영어가능", "keywords": ["English"]},
        ],
        "exclude_keywords": ["계약직"],
        "min_experience_years": 5,
    }


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "targets.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


# --- 실제 targets.json ---------------------------------------------------


def test_default_targets_loads():
    cfg = load_targets()
    assert isinstance(cfg, TargetsConfig)
    assert len(cfg.companies) >= 1


def test_default_targets_ids_unique():
    cfg = load_targets()
    ids = [c.id for c in cfg.companies]
    assert len(ids) == len(set(ids))


def test_default_targets_five_categories():
    cfg = load_targets()
    cats = {ks.category for ks in cfg.keyword_sets}
    assert {"UX/HMI", "접근성", "브랜딩", "패키지/인쇄", "Design(EN)"} <= cats
    assert "AI" not in cats  # AI 카테고리는 개발직 노이즈 유발로 제거됨


def test_default_targets_min_experience_is_five():
    cfg = load_targets()
    assert cfg.min_experience_years == 5


def test_jobkorea_companies_share_fingerprint():
    cfg = load_targets()
    jk = cfg.companies_by_adapter(Adapter.JOBKOREA)
    assert jk, "jobkorea 회사가 하나 이상 있어야 함"
    assert all(c.fingerprint == "JOBKOREA_M_FINGERPRINT" for c in jk)


# --- 헬퍼 메서드 ---------------------------------------------------------


def test_get_company_and_missing():
    cfg = load_targets()
    assert cfg.get_company("nhn").name == "NHN"
    with pytest.raises(KeyError):
        cfg.get_company("does_not_exist")


def test_all_keywords_maps_to_category():
    cfg = load_targets()
    mapping = cfg.all_keywords()
    assert mapping.get("브랜딩") == "브랜딩"
    assert mapping.get("UX") == "UX/HMI"


# --- 검증 실패 케이스 ----------------------------------------------------


def test_missing_file_raises_config_error(tmp_path: Path):
    with pytest.raises(ConfigError, match="찾을 수 없습니다"):
        load_targets(tmp_path / "nope.json")


def test_bad_json_raises_config_error(tmp_path: Path):
    p = tmp_path / "targets.json"
    p.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON 파싱 실패"):
        load_targets(p)


def test_duplicate_ids_rejected(tmp_path: Path):
    data = _minimal_config()
    data["companies"].append(
        {"id": "nhn", "name": "중복", "adapter": "jobkorea"}
    )
    with pytest.raises(ConfigError, match="중복된 company id"):
        load_targets(_write(tmp_path, data))


def test_unknown_adapter_rejected(tmp_path: Path):
    data = _minimal_config()
    data["companies"][0]["adapter"] = "unknown_adapter"
    with pytest.raises(ConfigError, match="스키마 검증 실패"):
        load_targets(_write(tmp_path, data))


def test_unknown_field_rejected(tmp_path: Path):
    data = _minimal_config()
    data["companies"][0]["typo_field"] = "oops"
    with pytest.raises(ConfigError, match="스키마 검증 실패"):
        load_targets(_write(tmp_path, data))


def test_mode_on_static_adapter_rejected(tmp_path: Path):
    data = _minimal_config()
    data["companies"][0]["mode"] = "api"  # jobkorea는 정적 → mode 불가
    with pytest.raises(ConfigError, match="mode를 지정할 수 없"):
        load_targets(_write(tmp_path, data))


def test_negative_min_experience_rejected(tmp_path: Path):
    data = _minimal_config()
    data["min_experience_years"] = -1
    with pytest.raises(ConfigError, match="스키마 검증 실패"):
        load_targets(_write(tmp_path, data))


def test_empty_keywords_rejected(tmp_path: Path):
    data = _minimal_config()
    data["keyword_sets"][0]["keywords"] = []
    with pytest.raises(ConfigError, match="스키마 검증 실패"):
        load_targets(_write(tmp_path, data))


def test_spa_mode_allowed(tmp_path: Path):
    data = _minimal_config()
    data["companies"].append(
        {"id": "toss", "name": "토스", "adapter": "spa", "mode": "api"}
    )
    cfg = load_targets(_write(tmp_path, data))
    assert cfg.get_company("toss").mode == Mode.API


def test_company_model_defaults():
    c = Company(id="x", name="X", adapter=Adapter.SPA)
    assert c.urls == []
    assert c.brand_filter is None
    assert c.mode is None
