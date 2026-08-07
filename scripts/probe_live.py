"""일회용 라이브 프로브 (GitHub Actions 전용).

샌드박스는 채용/ATS 호스트가 프록시 정책으로 차단되므로, 이 스크립트는 오픈
인터넷을 가진 Actions 러너에서만 의미가 있다. 두 가지를 한 번에 처리한다:

  A) Workday 5개(Lululemon/Mattel/Hasbro/Spin Master/Wayfair) — 라이브 조회만.
     디자인+캐나다/토론토/Remote 위치 자리를 출력한다(봇에 추가하지 않음).
  B) Shopify/Figma/Pinterest — 어떤 ATS/토큰이 실제로 응답하는지 탐색한다.

봇 코드(targets.json)는 건드리지 않는다. 결과는 표준출력 로그로만 남긴다.
검증이 끝나면 이 스크립트와 probe 워크플로는 삭제한다.
"""

from __future__ import annotations

import json

import httpx

from opmon.relevance import is_design_or_access

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CA_LOC = ("toronto", "ontario", ", on", "canada", "vancouver", "british columbia",
          ", bc", "remote")

client = httpx.Client(follow_redirects=True, timeout=25.0,
                      headers={"User-Agent": UA, "Accept": "application/json"})


def line(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- A) Workday
# host / tenant / site 후보. site는 회사마다 다를 수 있어 몇 개씩 시도한다.
WORKDAY = {
    "Lululemon": ("lululemon.wd3.myworkdayjobs.com", "lululemon",
                  ["lululemon", "External", "Careers", "lululemon_External"]),
    "Mattel": ("mattel.wd5.myworkdayjobs.com", "mattel",
               ["Mattel", "External", "mattel"]),
    "Hasbro": ("hasbro.wd5.myworkdayjobs.com", "hasbro",
               ["hasbro", "External", "Hasbro_Careers", "Hasbro"]),
    "SpinMaster": ("spinmaster.wd3.myworkdayjobs.com", "spinmaster",
                   ["spinmaster", "External", "Spin_Master_Careers"]),
    "Wayfair": ("wayfair.wd5.myworkdayjobs.com", "wayfair",
                ["wayfair", "External", "WayfairExternal"]),
}


def probe_workday():
    line("\n==================== A) WORKDAY LIVE CHECK ====================")
    for name, (host, tenant, sites) in WORKDAY.items():
        found_site = None
        for site in sites:
            url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
            try:
                r = client.post(url, json={"appliedFacets": {}, "limit": 20,
                                           "offset": 0, "searchText": "designer"},
                                headers={"Content-Type": "application/json"})
            except Exception as e:
                line(f"[{name}] {site}: ERR {type(e).__name__} {str(e)[:80]}")
                continue
            if r.status_code != 200:
                line(f"[{name}] {site}: HTTP {r.status_code}")
                continue
            try:
                data = r.json()
            except Exception:
                line(f"[{name}] {site}: non-JSON")
                continue
            if not isinstance(data, dict) or "jobPostings" not in data:
                line(f"[{name}] {site}: 200 but no jobPostings (keys={list(data)[:6]})")
                continue
            found_site = site
            break
        if not found_site:
            line(f"[{name}] ❌ 사용가능한 Workday board 못 찾음")
            continue

        # board 확정 → designer/graphic/packaging 몇 페이지 훑어 디자인+캐나다/remote 추출
        base = f"https://{host}/wday/cxs/{tenant}/{found_site}/jobs"
        job_base = f"https://{host}/en-US/{found_site}"
        seen, hits = set(), []
        total0 = 0
        for q in ("designer", "graphic", "packaging", "brand"):
            for off in (0, 20, 40):
                try:
                    r = client.post(base, json={"appliedFacets": {}, "limit": 20,
                                                "offset": off, "searchText": q},
                                    headers={"Content-Type": "application/json"})
                    d = r.json()
                except Exception:
                    break
                posts = d.get("jobPostings") or []
                total0 = max(total0, int(d.get("total") or 0))
                for p in posts:
                    path = p.get("externalPath") or ""
                    if path in seen:
                        continue
                    seen.add(path)
                    title = p.get("title") or ""
                    loc = (p.get("locationsText") or "")
                    if not is_design_or_access(title):
                        continue
                    if not any(k in loc.lower() for k in CA_LOC):
                        continue
                    hits.append((title, loc, job_base + path))
                if not posts or off + 20 >= int(d.get("total") or 0):
                    break
        line(f"\n[{name}] ✅ board='{found_site}'  (designer total≈{total0})  "
             f"디자인+캐나다/remote 매칭: {len(hits)}")
        for t, l, u in hits[:15]:
            line(f"    • {t}  —  {l}\n      {u}")


# ------------------------------------------------------- B) ATS DISCOVERY
def _sample_titles(items, tkey, lkey=None):
    out = []
    for it in items[:3]:
        t = it.get(tkey) if isinstance(it, dict) else None
        out.append(str(t)[:60])
    return out


def probe_greenhouse(token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false"
    try:
        r = client.get(url)
    except Exception as e:
        return f"greenhouse/{token}: ERR {type(e).__name__}"
    if r.status_code != 200:
        return f"greenhouse/{token}: HTTP {r.status_code}"
    try:
        d = r.json()
    except Exception:
        return f"greenhouse/{token}: non-JSON"
    jobs = d.get("jobs") if isinstance(d, dict) else None
    if jobs is None:
        return f"greenhouse/{token}: 200 keys={list(d)[:6]}"
    return f"greenhouse/{token}: ✅ 200 jobs={len(jobs)} sample={_sample_titles(jobs,'title')}"


def probe_ashby(name):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{name}"
    try:
        r = client.get(url)
    except Exception as e:
        return f"ashby/{name}: ERR {type(e).__name__}"
    if r.status_code != 200:
        return f"ashby/{name}: HTTP {r.status_code}"
    try:
        d = r.json()
    except Exception:
        return f"ashby/{name}: non-JSON"
    jobs = d.get("jobs") if isinstance(d, dict) else None
    if jobs is None:
        return f"ashby/{name}: 200 keys={list(d)[:6]}"
    return f"ashby/{name}: ✅ 200 jobs={len(jobs)} sample={_sample_titles(jobs,'title')}"


def probe_smartrecruiters(company):
    url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=10"
    try:
        r = client.get(url)
    except Exception as e:
        return f"smartrecruiters/{company}: ERR {type(e).__name__}"
    if r.status_code != 200:
        return f"smartrecruiters/{company}: HTTP {r.status_code}"
    try:
        d = r.json()
    except Exception:
        return f"smartrecruiters/{company}: non-JSON"
    content = d.get("content") if isinstance(d, dict) else None
    if content is None:
        return f"smartrecruiters/{company}: 200 keys={list(d)[:6]}"
    return (f"smartrecruiters/{company}: ✅ 200 total={d.get('totalFound')} "
            f"n={len(content)} sample={_sample_titles(content,'name')}")


def probe_ats():
    line("\n==================== B) ATS DISCOVERY (Shopify/Figma/Pinterest) ====================")
    line("\n-- Shopify --")
    for f in (lambda: probe_greenhouse("shopify"),
              lambda: probe_smartrecruiters("shopify"),
              lambda: probe_smartrecruiters("Shopify"),
              lambda: probe_ashby("shopify")):
        line("  " + f())
    line("\n-- Figma --")
    for f in (lambda: probe_ashby("Figma"),
              lambda: probe_ashby("figma"),
              lambda: probe_greenhouse("figma"),
              lambda: probe_smartrecruiters("figma")):
        line("  " + f())
    line("\n-- Pinterest --")
    for f in (lambda: probe_greenhouse("pinterest"),
              lambda: probe_ashby("pinterest"),
              lambda: probe_smartrecruiters("pinterest"),
              lambda: probe_smartrecruiters("Pinterest")):
        line("  " + f())


if __name__ == "__main__":
    probe_workday()
    probe_ats()
    line("\n==================== PROBE DONE ====================")
