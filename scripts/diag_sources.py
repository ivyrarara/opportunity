"""진단: 회사별 어댑터를 1회씩 실행해 outcome + 실제 에러를 한 줄로 출력.

Actions에서만 외부 호스트 접근 가능하므로 여기로 돌린다.
출력: company | adapter | outcome | detail(에러/상태코드/메타)
"""
from __future__ import annotations

from opmon.config import load_targets
from opmon.adapters.registry import REGISTRY
from opmon.adapters.base import RunContext


def main() -> None:
    cfg = load_targets()
    ctx = RunContext()
    rows = []
    for company in cfg.companies:
        runner = REGISTRY.get(company.adapter.value)
        if runner is None:
            rows.append((company.id, company.adapter.value, "SKIP_unregistered", ""))
            continue
        try:
            res = runner(company, cfg, ctx)
        except Exception as exc:  # noqa: BLE001
            rows.append((company.id, company.adapter.value, "EXC", repr(exc)[:180]))
            continue
        if getattr(res, "skipped", False):
            rows.append((company.id, company.adapter.value, "SKIP", str(res.meta)[:140]))
            continue
        meta = res.meta or {}
        detail = meta.get("error") or meta.get("status") or {k: v for k, v in meta.items() if k != "count"}
        cnt = meta.get("count", len(getattr(res, "matches", []) or []))
        rows.append((company.id, company.adapter.value, res.outcome.value, f"n={cnt} {str(detail)[:150]}"))

    print("=== DIAG START ===")
    for r in rows:
        print("DIAG| " + " | ".join(str(x) for x in r))
    print("=== DIAG END ===")


if __name__ == "__main__":
    main()
