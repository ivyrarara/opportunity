"""외국계 회사들이 봇으로 긁히는지(ATS 종류) + 관심 지역 디자인 롤이 있는지 탐지.

Actions에서만 외부 접근 가능. 회사별로 후보 엔드포인트(Greenhouse/Lever/Workday/커스텀)를
차례로 시도해 첫 성공을 리포트하고, 디자인 롤을 지역(한국/토론토/밴쿠버/캐나다/리모트)별로 센다.
"""
from __future__ import annotations
import json
import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json,text/html,*/*"}
DESIGN = ("design", "brand", "visual", "packaging", "creative", "graphic")
REGIONS = {
    "KR": ("korea", "seoul", "서울", "대한민국"),
    "Toronto": ("toronto",),
    "Vancouver": ("vancouver",),
    "Canada": ("canada", "ontario", "british columbia"),
    "Remote": ("remote",),
    "US": ("united states", ", ca", ", ny", "california", "new york", "san francisco"),
}


def is_design(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in DESIGN)


def region_of(loc: str) -> str:
    l = (loc or "").lower()
    for r, keys in REGIONS.items():
        if any(k in l for k in keys):
            return r
    return ""


def tally(pairs):
    """pairs = list[(title, location)] → design 롤의 지역 카운트 + 샘플."""
    counts, samples = {}, []
    for title, loc in pairs:
        if not is_design(title):
            continue
        r = region_of(loc)
        if r in ("KR", "Toronto", "Vancouver", "Canada", "Remote"):
            counts[r] = counts.get(r, 0) + 1
            if len(samples) < 4:
                samples.append(f"{title} [{loc}]")
    return counts, samples


def greenhouse(token):
    r = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false",
                  headers=H, timeout=20, follow_redirects=True)
    r.raise_for_status()
    js = r.json().get("jobs", [])
    return len(js), [(j.get("title"), (j.get("location") or {}).get("name", "")) for j in js]


def lever(slug):
    r = httpx.get(f"https://api.lever.co/v0/postings/{slug}?mode=json",
                  headers=H, timeout=20, follow_redirects=True)
    r.raise_for_status()
    js = r.json()
    return len(js), [(j.get("text"), (j.get("categories") or {}).get("location", "")) for j in js]


def workday(host, tenant, site):
    out, off = [], 0
    for _ in range(3):
        r = httpx.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                       headers={**H, "Content-Type": "application/json"},
                       json={"appliedFacets": {}, "limit": 20, "offset": off, "searchText": "designer"},
                       timeout=25, follow_redirects=True)
        r.raise_for_status()
        d = r.json()
        posts = d.get("jobPostings", [])
        out += [(p.get("title"), p.get("locationsText", "")) for p in posts]
        off += 20
        if off >= min(d.get("total", 0), 60):
            break
    return len(out), out


def amazon():
    r = httpx.get("https://www.amazon.jobs/en/search.json",
                  params={"base_query": "designer", "result_limit": 100},
                  headers=H, timeout=25, follow_redirects=True)
    r.raise_for_status()
    js = r.json().get("jobs", [])
    return len(js), [(j.get("title"), j.get("normalized_location") or j.get("location", "")) for j in js]


def tesla():
    r = httpx.get("https://www.tesla.com/cua-api/apps/careers/state", headers=H,
                  timeout=25, follow_redirects=True)
    r.raise_for_status()
    d = r.json()
    lst = d.get("listings", []) if isinstance(d, dict) else []
    look = d.get("lookup", {}) if isinstance(d, dict) else {}
    reg = look.get("regions", {}) if isinstance(look, dict) else {}
    out = []
    for it in lst:
        title = it.get("t") or it.get("title") or ""
        loc = it.get("l") or reg.get(str(it.get("region")), "") or it.get("region", "")
        out.append((title, str(loc)))
    return len(out), out


def apple():
    r = httpx.post("https://jobs.apple.com/api/role/search",
                   headers={**H, "Content-Type": "application/json"},
                   json={"query": "designer", "page": 1, "locale": "en-us",
                         "sort": "relevance", "filters": {}}, timeout=25, follow_redirects=True)
    r.raise_for_status()
    d = r.json()
    roles = d.get("searchResults", []) or d.get("res", {}).get("searchResults", [])
    out = []
    for j in roles:
        loc = ", ".join(l.get("name", "") for l in (j.get("locations") or []))
        out.append((j.get("postingTitle") or j.get("title"), loc))
    return len(out), out


# (회사, [시도할 (라벨, 콜러블) 목록])
CANDS = [
    ("sephora", [("greenhouse:sephora", lambda: greenhouse("sephora")),
                 ("lever:sephora", lambda: lever("sephora")),
                 ("workday:sephora.wd5/External", lambda: workday("sephora.wd5.myworkdayjobs.com", "sephora", "External"))]),
    ("apple", [("apple-api", apple)]),
    ("tesla", [("tesla-cua", tesla)]),
    ("amazon", [("amazon.jobs", amazon)]),
    ("nvidia", [("workday:nvidia.wd5/NVIDIAExternalCareerSite",
                 lambda: workday("nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"))]),
    ("adobe", [("workday:adobe.wd5/external_experienced",
                lambda: workday("adobe.wd5.myworkdayjobs.com", "adobe", "external_experienced"))]),
    ("esteelauder", [("greenhouse:esteelauder", lambda: greenhouse("esteelauder")),
                     ("workday:elcompanies.wd5/ELCCareers",
                      lambda: workday("elcompanies.wd5.myworkdayjobs.com", "elcompanies", "ELCCareers"))]),
    ("lululemon", [("workday:lululemon.wd3/lululemon",
                    lambda: workday("lululemon.wd3.myworkdayjobs.com", "lululemon", "lululemon"))]),
]


def main():
    print("=== FPROBE START ===")
    for name, tries in CANDS:
        done = False
        for label, fn in tries:
            try:
                total, pairs = fn()
                counts, samples = tally(pairs)
                print(f"FPROBE| {name} | OK {label} | total={total} | design_by_region={counts}")
                for s in samples:
                    print(f"FPROBE|   ex: {s}")
                done = True
                break
            except Exception as e:  # noqa: BLE001
                print(f"FPROBE| {name} | fail {label} | {type(e).__name__}: {str(e)[:90]}")
        if not done:
            print(f"FPROBE| {name} | --- 모두 실패(자사 보호 ATS 가능) ---")
    print("=== FPROBE END ===")


if __name__ == "__main__":
    main()
