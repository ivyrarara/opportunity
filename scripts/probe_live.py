"""일회용 검증 (GitHub Actions 전용) — nudestix/bmo/td 어댑터 직접 실행.

BambooHR(nudestix) 스키마 실측 확인 + BMO/TD Workday 재확인. 검증 후 삭제.
"""

from __future__ import annotations

import os
import traceback

import httpx

os.environ.setdefault("OPMON_BAMBOOHR_DEBUG", "1")

from opmon.adapters.base import RunContext
from opmon.adapters.registry import get_runner
from opmon.config import load_targets

CFG = load_targets()
TARGETS = ["nudestix", "bmo", "td"]


def main():
    for cid in TARGETS:
        print(f"\n==================== {cid} ====================", flush=True)
        company = CFG.get_company(cid)
        runner = get_runner(company.adapter.value)
        client = httpx.Client(follow_redirects=True, timeout=25.0)
        try:
            res = runner(company, CFG, RunContext(client=client))
        except Exception:
            print("  EXCEPTION:\n" + traceback.format_exc(), flush=True)
            client.close()
            continue
        client.close()
        print(f"  outcome = {res.outcome}", flush=True)
        print(f"  meta    = {res.meta}", flush=True)
        for m in res.matches[:15]:
            print(f"    • {m.posting.title}\n      {m.posting.url}", flush=True)


if __name__ == "__main__":
    main()
    print("\n==================== VERIFY DONE ====================", flush=True)
