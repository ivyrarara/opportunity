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
- [x] 3. Outcome/classifier/aggregator (§5) — 순수 로직 완료. crawl_state는 인메모리 구현(Firestore는 4단계)
- [x] 4. Firestore 중복 제거(postings) — 저장소 추상화 + 인메모리/Firestore 구현 + `site+job_id` 중복제거.
      실제 자격증명 연결은 배포 시점(§12): `GOOGLE_APPLICATION_CREDENTIALS`, `OPMON_FIRESTORE_PROJECT`
- [x] 5. 텔레그램 봇 알림 연동 — §9 포맷 렌더 + Notifier 추상화(인메모리/텔레그램) + dispatch(시드 억제 훅).
      실제 봇 토큰은 배포 시점: `OPMON_TELEGRAM_TOKEN`, `OPMON_TELEGRAM_CHAT_ID` (`.env.example` 참조)
- [x] 6. 스케줄 등록 + 오케스트레이터 — `run_once`(config→취득→classify→저장→aggregate→알림),
      어댑터 레지스트리(미구현 어댑터 자동 스킵), GitHub Actions 크론(11:00 UTC≈07:00 Toronto).
      - 드라이런: `python -m opmon.pipeline --dry-run --only nhn`
      - 실행: `python -m opmon.pipeline [--seed] [--only ...]` (env 필요)
- [x] 7. 시드 모드 — `--seed` 플래그·dispatch 억제 구현·테스트 완료. 실제 시드 실행 절차는 `DEPLOY.md` runbook
- [ ] 8. SPA 그룹 (토스 검증 → 확장)
- [ ] 9. 현대차 NetFunnel (맨 마지막·실패 허용)
