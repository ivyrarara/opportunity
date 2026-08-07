"""일회용 NUDESTIX BambooHR 구조 확인 (GitHub Actions 전용).

/careers/list 가 JSON이 아니라 HTML을 준다. 실제 JSON 엔드포인트나, HTML 안에
임베드된 잡 데이터를 찾는다. 검증 후 삭제.
"""

from __future__ import annotations

import re

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0, headers={"User-Agent": UA})


def line(*a):
    print(*a, flush=True)


CANDS = [
    ("careers/list JSON", "https://nudestix.bamboohr.com/careers/list", {"Accept": "application/json"}),
    ("embed2", "https://nudestix.bamboohr.com/jobs/embed2.php?version=1.0.0", {}),
    ("careers page", "https://nudestix.bamboohr.com/careers", {}),
]

for name, url, h in CANDS:
    line(f"\n--- [{name}] {url}")
    try:
        r = client.get(url, headers=h)
    except Exception as e:
        line(f"    ERR {type(e).__name__}: {str(e)[:100]}")
        continue
    ct = r.headers.get("content-type", "")
    line(f"    HTTP {r.status_code} ct={ct} len={len(r.text)}")
    t = r.text
    # JSON 시그널
    for key in ('"jobOpeningName"', '"result"', '"jobs"', '"jobTitle"', '"atsStatusGroup"'):
        if key in t:
            i = t.find(key)
            line(f"    JSON신호 {key} @ {i}: …{t[max(0,i-40):i+160]}…")
    # /careers/{id} 링크
    ids = re.findall(r'/careers/(\d+)', t)
    line(f"    /careers/{{id}} 링크 수: {len(ids)} 유니크: {sorted(set(ids))[:20]}")
    # 임베드 JSON island (window.__ 또는 <script type=application/json>)
    for m in re.finditer(r'window\.\w+\s*=\s*(\{.{0,80})', t):
        line(f"    window 할당: {m.group(1)[:100]}")
        break
    # 제목처럼 보이는 것
    titles = re.findall(r'jobOpeningName"\s*:\s*"([^"]{3,80})"', t)
    if titles:
        line(f"    제목 표본: {titles[:15]}")

line("\n==================== NUDESTIX PROBE DONE ====================")
