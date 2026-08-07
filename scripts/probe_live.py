"""일회용 Microsoft 채용 API 탐색 (GitHub Actions 전용).

MS는 자체 채용사이트(careers.microsoft.com)를 쓴다. 공개 검색 API 후보를 쳐서
200+JSON(jobs 배열)을 주는 엔드포인트와 스키마(제목/위치/id 필드)를 찾는다.
확정되면 microsoft 어댑터를 만든다. 검증 후 삭제.
"""

from __future__ import annotations

import json

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0,
                      headers={"User-Agent": UA, "Accept": "application/json"})

BASE = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
CANDS = [
    f"{BASE}?q=designer&lc=Vancouver%2C%20British%20Columbia%2C%20Canada&l=en_us&pg=1&pgSz=20&o=Relevance&flt=true",
    f"{BASE}?q=designer&lc=Canada&pg=1&pgSz=20&l=en_us",
    f"{BASE}?q=designer&pg=1&pgSz=20",
]


def peek(data):
    def find_jobs(d):
        if isinstance(d, dict):
            if isinstance(d.get("jobs"), list):
                return d["jobs"]
            for v in d.values():
                r = find_jobs(v)
                if r is not None:
                    return r
        return None
    jobs = find_jobs(data)
    if jobs is None:
        return f"jobs 배열 못 찾음. top keys={list(data)[:8] if isinstance(data, dict) else type(data)}"
    s = json.dumps(jobs[0], ensure_ascii=False)[:600] if jobs else "empty"
    return f"jobs={len(jobs)} sample={s}"


for url in CANDS:
    print(f"\n--- {url}", flush=True)
    try:
        r = client.get(url)
    except Exception as e:
        print(f"    ERR {type(e).__name__}: {str(e)[:120]}", flush=True)
        continue
    print(f"    HTTP {r.status_code} ct={r.headers.get('content-type','')[:30]} len={len(r.text)}", flush=True)
    if r.status_code != 200:
        continue
    try:
        print("    " + peek(r.json()), flush=True)
    except Exception:
        print(f"    non-JSON head={r.text[:120]!r}", flush=True)

print("\n==================== MS PROBE DONE ====================", flush=True)
