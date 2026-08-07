"""일회용 Netflix 엔드포인트 탐색 (GitHub Actions 전용).

jobs.netflix.com/api/search 가 404 → 실제 채용 API를 찾는다. 후보 URL들을 쳐서
status/keys/sample을 출력한다. 확정되면 netflix 어댑터를 그 엔드포인트로 고친다.
검증 후 이 파일/probe.yml 삭제.
"""

from __future__ import annotations

import json

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0,
                      headers={"User-Agent": UA, "Accept": "application/json"})

CANDIDATES = [
    # Eightfold (explore.jobs.netflix.net) — 가장 유력
    "https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&start=0&num=10&query=designer",
    "https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&start=0&num=10",
    # jobs.netflix.com 변형
    "https://jobs.netflix.com/api/search?q=designer&page=1",
    "https://jobs.netflix.com/api/v1/search?q=designer",
    "https://jobs.netflix.com/search/api/jobs?q=designer",
    # Eightfold positions 변형
    "https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&query=designer&location=remote&start=0&num=10",
]


def peek(data):
    if isinstance(data, dict):
        keys = list(data)[:8]
        # 흔한 리스트 키에서 첫 샘플
        for k in ("positions", "jobs", "records", "results", "data"):
            v = data.get(k)
            if isinstance(v, list) and v:
                return f"keys={keys} '{k}'[0]={json.dumps(v[0], ensure_ascii=False)[:500]}"
            if isinstance(v, dict):
                for kk in ("postings", "jobs", "positions"):
                    vv = v.get(kk)
                    if isinstance(vv, list) and vv:
                        return f"keys={keys} '{k}.{kk}'[0]={json.dumps(vv[0], ensure_ascii=False)[:500]}"
        return f"keys={keys} (리스트 없음) body={json.dumps(data, ensure_ascii=False)[:300]}"
    if isinstance(data, list):
        return f"list len={len(data)} [0]={json.dumps(data[0], ensure_ascii=False)[:500] if data else 'empty'}"
    return f"type={type(data)}"


def main():
    for url in CANDIDATES:
        print(f"\n--- {url}", flush=True)
        try:
            r = client.get(url)
        except Exception as e:
            print(f"    ERR {type(e).__name__}: {str(e)[:120]}", flush=True)
            continue
        ct = r.headers.get("content-type", "")
        print(f"    HTTP {r.status_code}  content-type={ct}", flush=True)
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except Exception:
            print(f"    non-JSON (len={len(r.text)}) head={r.text[:120]!r}", flush=True)
            continue
        print("    " + peek(data), flush=True)


if __name__ == "__main__":
    main()
    print("\n==================== NETFLIX PROBE DONE ====================", flush=True)
