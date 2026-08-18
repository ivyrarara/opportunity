"""피플앤잡(peoplenjob) 구조 탐지 — 디자인 검색 결과가 파싱 가능한지."""
import httpx, re
UA=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
H={"User-Agent":UA,"Accept":"text/html,*/*","Accept-Language":"ko-KR,ko;q=0.9,en;q=0.8"}
CANDS=[
 "https://www.peoplenjob.com/",
 "https://www.peoplenjob.com/jobs",
 "https://www.peoplenjob.com/jobs?searchword=%EB%94%94%EC%9E%90%EC%9D%B8",
 "https://www.peoplenjob.com/jobs/search?keyword=%EB%94%94%EC%9E%90%EC%9D%B8",
 "https://www.peoplenjob.com/recruit",
 "https://www.peoplenjob.com/job",
]
print("=== PNJ START ===")
for u in CANDS:
    try:
        r=httpx.get(u,headers=H,timeout=20,follow_redirects=True)
        html=r.text
        # job-ish anchors
        hrefs=re.findall(r'href="([^"]*(?:job|recruit|view|posting)[^"]*)"',html,re.I)
        # design mentions
        dcount=len(re.findall(r'디자인|디자이너|design',html,re.I))
        # sample titles near design
        titles=re.findall(r'>([^<>]{4,40}(?:디자이너|디자인|Designer)[^<>]{0,30})<',html)
        print(f"PNJ| {u} | {r.status_code} | len={len(html)} | final={str(r.url)[:60]}")
        print(f"PNJ|   job_hrefs={len(set(hrefs))} design_hits={dcount}")
        for t in titles[:5]:
            print(f"PNJ|   title: {t.strip()[:60]}")
        for h in list(dict.fromkeys(hrefs))[:5]:
            print(f"PNJ|   href: {h[:80]}")
    except Exception as e:
        print(f"PNJ| {u} | ERR {type(e).__name__}: {str(e)[:80]}")
print("=== PNJ END ===")
