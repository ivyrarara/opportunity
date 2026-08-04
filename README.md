# opportunity

관심 카테고리(UX/HMI · AI · 접근성 · 브랜딩 · 패키지/인쇄)의 신규 공고를 매일 확인해
텔레그램으로 알려주는 개인용 모니터링. 개인 용도 한정(재배포/상업화 금지).

## 구조

```
config/targets.json   # 대상 회사 · 키워드 · 필터 설정 (코드와 분리)
src/opmon/config.py   # 설정 로더 + 스키마 검증
tests/                # 테스트
```

## 개발

```bash
pip install -e ".[dev]"

# 설정 로드 확인 (요약 출력)
python -m opmon.config

# 테스트
pytest
```

## 구현 진행

명세 §10 순서대로 한 단계씩 진행한다.

- [x] 1. `config/targets.json` 로더 + 스키마 검증
- [~] 2. 잡코리아 NHN end-to-end 세로 검증 — **파싱·매칭·콘솔출력까지 오프라인 완료**.
      단, 이 세션은 egress 정책상 `m.jobkorea.co.kr` 접근이 차단되어 §6-4 라이브 probe 미완.
      fingerprint의 `[검증필요]` 셀렉터/마커는 network 되는 환경에서 probe 1회로 확정 필요.
      - 오프라인 검증: `python -m opmon.adapters.jobkorea --company nhn --fixture tests/fixtures/jobkorea_nhn_synthetic.html`
      - 라이브 probe(접근 뚫린 환경): `python -m opmon.adapters.jobkorea --company nhn --probe`
- [ ] 3. Outcome/classifier/aggregator + crawl_errors·crawl_state
- [ ] 4. Firestore 중복 제거(postings)
- [ ] 5. 텔레그램 봇 알림 연동
- [ ] 6. 스케줄 등록
- [ ] 7. 시드 모드 1회 전체 실행 → 정상 알림 모드
- [ ] 8. SPA 그룹 (토스 검증 → 확장)
- [ ] 9. 현대차 NetFunnel (맨 마지막·실패 허용)
