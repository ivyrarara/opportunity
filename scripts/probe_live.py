"""일회용 프로브 (GitHub Actions 전용) — JD 요건 스캔 + Workday board 탐색.

PART 1: Pinterest(Greenhouse)/Netflix(Eightfold) 실제 열린 자리의 JD 본문을 끌어와
        필수 연차·툴(Figma/모션/비디오)·포트폴리오 성격 신호를 스캔해 출력.
PART 2: Lululemon/Mattel/Hasbro/SpinMaster/Wayfair 의 Workday board를 후보 대폭
        늘려 재탐색(+대체 ATS). 찾으면 디자인+캐나다/remote 자리도 출력.

검증 후 이 파일/probe.yml 삭제. 봇 targets 는 건드리지 않는다.
"""

from __future__ import annotations

import re

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0,
                      headers={"User-Agent": UA, "Accept": "application/json"})

SIGNALS = [
    "year", "yrs", "figma", "motion", "video", "after effects", "animation",
    "prototyp", "brand", "packaging", "print", "portfolio", "typograph",
    "visual", "illustrat", "3d", "accessib",
]


def line(*a):
    print(*a, flush=True)


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", s).strip()


def scan(text: str, cap: int = 14):
    """신호 키워드가 든 문장만 뽑아 출력."""
    sents = re.split(r"(?<=[.!?])\s+|(?:•|•|\n)", text)
    hits, seen = [], set()
    for s in sents:
        low = s.lower()
        if any(k in low for k in SIGNALS) and len(s) > 12:
            key = s[:60]
            if key not in seen:
                seen.add(key)
                hits.append(s.strip())
    for h in hits[:cap]:
        line(f"      · {h[:240]}")
    if not hits:
        line("      (신호 키워드 없음 — 본문 앞부분) " + text[:200])


# ---------------------------------------------------------- PART 1: JD 스캔
PINTEREST = [
    ("Principal Product Designer, AI Native, Core", "7638599"),
    ("Sr. Product Designer, Advertiser Experience", "7770902"),
    ("Staff Product Designer, Design Innovation", "7839695"),
]
NETFLIX = [
    ("Senior Creative Designer, Creative Publishing", "790316788411"),
    ("Senior Product Designer, Emerging Creative", "790316471296"),
    ("Principal UX Designer, Creative Publishing", "790316788821"),
]


def jd_pinterest():
    line("\n########## PART 1a — Pinterest JD 스캔 (Greenhouse) ##########")
    for title, jid in PINTEREST:
        line(f"\n[Pinterest] {title}  (jid={jid})")
        try:
            r = client.get(f"https://boards-api.greenhouse.io/v1/boards/pinterest/jobs/{jid}")
            if r.status_code != 200:
                line(f"    HTTP {r.status_code}")
                continue
            d = r.json()
            loc = (d.get("location") or {}).get("name")
            line(f"    location={loc}")
            scan(strip_html(d.get("content", "")))
        except Exception as e:
            line(f"    ERR {type(e).__name__}: {str(e)[:100]}")


def jd_netflix():
    line("\n########## PART 1b — Netflix JD 스캔 (Eightfold) ##########")
    for title, pid in NETFLIX:
        line(f"\n[Netflix] {title}  (pid={pid})")
        got = False
        for url in (
            f"https://explore.jobs.netflix.net/api/apply/v2/jobs/{pid}?domain=netflix.com",
            f"https://explore.jobs.netflix.net/api/apply/v2/positions/{pid}?domain=netflix.com",
        ):
            try:
                r = client.get(url)
            except Exception as e:
                line(f"    ERR {type(e).__name__}: {str(e)[:80]}")
                continue
            if r.status_code != 200:
                continue
            try:
                d = r.json()
            except Exception:
                continue
            desc = ""
            if isinstance(d, dict):
                desc = d.get("job_description") or d.get("description") or ""
                if not desc:
                    pos = d.get("positions") or d.get("position")
                    if isinstance(pos, list) and pos:
                        desc = pos[0].get("job_description", "")
                    elif isinstance(pos, dict):
                        desc = pos.get("job_description", "")
                loc = d.get("location") or (d.get("position") or {}).get("location") if isinstance(d.get("position"), dict) else d.get("location")
                line(f"    location={loc}")
            if desc:
                scan(strip_html(desc))
                got = True
                break
            else:
                line(f"    200 but no description (keys={list(d)[:8] if isinstance(d, dict) else type(d)})")
                got = True
                break
        if not got:
            line("    본문 못 가져옴 (상세 엔드포인트 미확인)")


# ------------------------------------------------- PART 2: Workday 재탐색
WORKDAY = {
    "Lululemon": ([f"lululemon.wd{n}.myworkdayjobs.com" for n in (3, 1, 5)],
                  "lululemon",
                  ["lululemon", "External", "Careers", "lululemoncareers",
                   "lululemon_External", "lululemonExternal"]),
    "Mattel": ([f"mattel.wd{n}.myworkdayjobs.com" for n in (5, 1, 3)],
               "mattel",
               ["Mattel", "External", "MattelCareers", "Mattel_External",
                "mattel", "External_Careers"]),
    "Hasbro": ([f"hasbro.wd{n}.myworkdayjobs.com" for n in (5, 1, 3)],
               "hasbro",
               ["Hasbro", "External", "HasbroCareers", "Hasbro_External",
                "hasbro", "Hasbro_Careers"]),
    "SpinMaster": ([f"spinmaster.wd{n}.myworkdayjobs.com" for n in (3, 1, 5)]
                   + [f"spinmasterltd.wd{n}.myworkdayjobs.com" for n in (3, 1)],
                   "spinmaster",
                   ["SpinMaster", "External", "spinmaster", "Spin_Master",
                    "SpinMasterCareers"]),
    "Wayfair": ([f"wayfair.wd{n}.myworkdayjobs.com" for n in (5, 1, 12, 3)],
                "wayfair",
                ["Wayfair", "External", "WayfairExternal", "wayfair",
                 "WayfairCareers"]),
}
CA_LOC = ("toronto", "ontario", ", on", "canada", "vancouver", "british columbia",
          ", bc", "remote")
try:
    from opmon.relevance import is_design_or_access
except Exception:
    def is_design_or_access(t):
        return "design" in (t or "").lower()


def workday():
    line("\n########## PART 2 — Workday board 재탐색 ##########")
    for name, (hosts, tenant, sites) in WORKDAY.items():
        found = None
        for host in hosts:
            for site in sites:
                url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
                try:
                    r = client.post(url, json={"appliedFacets": {}, "limit": 20,
                                               "offset": 0, "searchText": "designer"},
                                    headers={"Content-Type": "application/json"})
                except Exception:
                    continue
                if r.status_code == 200:
                    try:
                        d = r.json()
                    except Exception:
                        continue
                    if isinstance(d, dict) and "jobPostings" in d:
                        found = (host, site, d)
                        break
            if found:
                break
        if not found:
            line(f"\n[{name}] ❌ Workday board 못 찾음 (hosts={hosts[0]} 등)")
            continue
        host, site, d = found
        base = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        job_base = f"https://{host}/en-US/{site}"
        hits, seen, total = [], set(), int(d.get("total") or 0)
        for q in ("designer", "graphic", "packaging", "brand"):
            for off in (0, 20):
                try:
                    rr = client.post(base, json={"appliedFacets": {}, "limit": 20,
                                                 "offset": off, "searchText": q},
                                     headers={"Content-Type": "application/json"})
                    dd = rr.json()
                except Exception:
                    break
                posts = dd.get("jobPostings") or []
                for p in posts:
                    path = p.get("externalPath") or ""
                    if path in seen:
                        continue
                    seen.add(path)
                    t, loc = p.get("title") or "", (p.get("locationsText") or "")
                    if is_design_or_access(t) and any(k in loc.lower() for k in CA_LOC):
                        hits.append((t, loc, job_base + path))
                if not posts or off + 20 >= int(dd.get("total") or 0):
                    break
        line(f"\n[{name}] ✅ board host={host} site='{site}' (designer total≈{total}) "
             f"디자인+캐나다/remote: {len(hits)}")
        for t, l, u in hits[:12]:
            line(f"    • {t}  —  {l}")


if __name__ == "__main__":
    jd_pinterest()
    jd_netflix()
    workday()
    line("\n==================== PROBE DONE ====================")
