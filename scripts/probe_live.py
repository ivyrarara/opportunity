"""일회용 검증 (GitHub Actions 전용) — 신규 어댑터 3종만 직접 실행.

전체 파이프라인(느린 hyundai 대기열 + flaky jobkorea)과 분리해, netflix/figma/
pinterest 어댑터만 라이브 API로 돌려 outcome/meta/샘플을 출력한다. Netflix는
OPMON_NETFLIX_DEBUG로 스키마도 함께 로깅한다. 검증 후 이 파일/probe.yml 삭제.
"""

from __future__ import annotations

import os
import traceback

import httpx

os.environ.setdefault("OPMON_NETFLIX_DEBUG", "1")

from opmon.adapters.base import RunContext
from opmon.adapters.registry import get_runner
from opmon.config import load_targets

CFG = load_targets()
TARGETS = ["netflix", "figma", "pinterest"]


def main():
    for cid in TARGETS:
        print(f"\n==================== {cid} ====================", flush=True)
        try:
            company = CFG.get_company(cid)
        except Exception as e:
            print(f"  targets에 없음: {e}", flush=True)
            continue
        runner = get_runner(company.adapter.value)
        if runner is None:
            print(f"  runner 없음: {company.adapter.value}", flush=True)
            continue
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
        print(f"  matched = {len(res.matches)}", flush=True)
        for m in res.matches[:15]:
            print(f"    • {m.posting.title}\n      {m.posting.url}", flush=True)


if __name__ == "__main__":
    main()
    print("\n==================== VERIFY DONE ====================", flush=True)
