"""일회용 접근성/인클루시브 디자인 라이브 스윕 (GitHub Actions 전용).

봇에 붙은 신뢰 JSON-API 회사들에 접근성 키워드로 실제 열린 자리를 조회한다.
title/직무에 accessibility·inclusive·a11y·universal·barrier-free 가 있는 디자인
자리를 뽑는다. 검증 후 삭제.
"""

from __future__ import annotations

import re

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0,
                      headers={"User-Agent": UA, "Accept": "application/json"})

ACC = re.compile(r"accessib|inclusive|a11y|universal design|barrier|assistive|wcag|aoda", re.I)
DES = re.compile(r"design|ux|ui|brand|visual|graphic|creative|research", re.I)


def line(*a):
    print(*a, flush=True)


def hit(title):
    return bool(ACC.search(title))


# ---- Greenhouse (Figma, Pinterest): content=true 로 본문까지 접근성 스캔
def greenhouse(token):
    line(f"\n== Greenhouse/{token} ==")
    try:
        r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        jobs = r.json().get("jobs", [])
    except Exception as e:
        line(f"   ERR {type(e).__name__}"); return
    total = len(jobs)
    title_hits = [j for j in jobs if hit(j.get("title", ""))]
    # 본문에 접근성 + 디자인직 제목
    body_hits = []
    for j in jobs:
        t = j.get("title", "")
        c = j.get("content", "") or ""
        if DES.search(t) and ACC.search(c) and j not in title_hits:
            body_hits.append(j)
    line(f"   전체 {total} · 제목에 접근성 {len(title_hits)} · (디자인직+본문 접근성 언급) {len(body_hits)}")
    for j in title_hits[:10]:
        line(f"   ★ {j.get('title')} — {(j.get('location') or {}).get('name')}")
    for j in body_hits[:8]:
        line(f"   · {j.get('title')} — {(j.get('location') or {}).get('name')}  [본문 접근성 언급]")


# ---- Lever (Arc'teryx, Wealthsimple)
def lever(slug):
    line(f"\n== Lever/{slug} ==")
    try:
        data = client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json").json()
    except Exception as e:
        line(f"   ERR {type(e).__name__}"); return
    th = [d for d in data if hit(d.get("text", ""))]
    bh = [d for d in data if DES.search(d.get("text", "")) and ACC.search(
        (d.get("descriptionPlain") or "") + (d.get("description") or "")) and d not in th]
    line(f"   전체 {len(data)} · 제목 접근성 {len(th)} · 디자인직+본문 접근성 {len(bh)}")
    for d in th[:10]:
        line(f"   ★ {d.get('text')} — {(d.get('categories') or {}).get('location')}")
    for d in bh[:8]:
        line(f"   · {d.get('text')} — {(d.get('categories') or {}).get('location')}  [본문]")


# ---- Netflix Eightfold: 접근성 쿼리
def netflix():
    line("\n== Netflix (Eightfold) ==")
    seen = {}
    for q in ("accessibility", "inclusive design", "accessible"):
        try:
            d = client.get("https://explore.jobs.netflix.net/api/apply/v2/jobs"
                           f"?domain=netflix.com&start=0&num=20&query={q}").json()
            for p in d.get("positions", []):
                seen[p.get("id")] = p
        except Exception as e:
            line(f"   ERR {type(e).__name__} ({q})")
    des = [p for p in seen.values() if DES.search(p.get("name", ""))]
    line(f"   접근성쿼리 유니크 {len(seen)} · 그중 디자인직 {len(des)}")
    for p in des[:12]:
        line(f"   · {p.get('name')} — {p.get('location')}")


# ---- Workday (캐나다 브랜드/은행): searchText 접근성
def workday(name, host, tenant, site):
    line(f"\n== Workday/{name} ==")
    found = {}
    for q in ("accessibility", "inclusive", "accessible design"):
        try:
            d = client.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q},
                            headers={"Content-Type": "application/json"}).json()
            for p in d.get("jobPostings", []):
                found[p.get("externalPath")] = p
        except Exception as e:
            line(f"   ERR {type(e).__name__} ({q})"); return
    des = [p for p in found.values() if DES.search(p.get("title", ""))]
    line(f"   접근성쿼리 유니크 {len(found)} · 디자인직 {len(des)}")
    for p in des[:10]:
        line(f"   · {p.get('title')} — {p.get('locationsText')}")


greenhouse("figma")
greenhouse("pinterest")
lever("arcteryx.com")
lever("wealthsimple")
netflix()
workday("Aritzia", "aritzia.wd3.myworkdayjobs.com", "aritzia", "External")
workday("BMO", "bmo.wd3.myworkdayjobs.com", "bmo", "External")
workday("TD", "td.wd3.myworkdayjobs.com", "td", "TD_Bank_Careers")
line("\n==================== ACCESS SWEEP DONE ====================")
