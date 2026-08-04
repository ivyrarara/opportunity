# 배포 · 시드 runbook (명세 §12, §10-7, §1 격리)

이 문서는 코드가 아니라 **운영 절차**다. 코드(1~6단계)는 오프라인으로 완성돼 있고,
아래는 실제 네트워크·자격증명이 있는 배포 환경에서 한 번 밟는 순서다.

## 0. 격리 원칙 재확인 (§1 — 최우선)

- **신규 GitHub 레포**(이 레포). 마늘 레포와 커밋/대화 공유 없음. ✅
- **신규 텔레그램 봇**: BotFather로 새로 생성, 중립적 이름. @garlic_kor_bot 재사용 금지.
- **별도 Firebase 프로젝트** 권장. 같은 계정이어도 프로젝트 분리.
- 커밋 메시지·변수명·컬렉션명에 "이직/채용/job search" 흔적 없음. ✅ (컬렉션명 postings/crawl_state/crawl_errors)

## 1. 자격증명 발급

1. **Firebase**: 새 프로젝트 → Firestore 사용 설정 → 서비스계정 키(JSON) 발급.
2. **Telegram**: BotFather `/newbot` → 토큰 확보. 봇과 대화 시작 후 chat_id 확인
   (`https://api.telegram.org/bot<TOKEN>/getUpdates`의 `chat.id`).

## 2. env 설정 (`.env.example` 참조 — 실제 값은 절대 커밋 금지)

```
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
OPMON_FIRESTORE_PROJECT=<firebase-project-id>
OPMON_TELEGRAM_TOKEN=<botfather-token>
OPMON_TELEGRAM_CHAT_ID=<chat-id>
```

GitHub Actions로 스케줄한다면 위를 리포지토리 Secrets로 등록
(`OPMON_TELEGRAM_TOKEN`, `OPMON_TELEGRAM_CHAT_ID`, `OPMON_FIRESTORE_PROJECT`,
`GCP_SA_KEY`=서비스계정 JSON 원문). 워크플로우: `.github/workflows/monitor.yml`.

## 3. 잡코리아 fingerprint 실측 확정 (§6-4) — **네트워크 뚫린 곳에서 1회**

개발 세션은 egress 정책상 `m.jobkorea.co.kr` 접근이 차단돼 있어 미완료 상태다.
접근 가능한 환경에서:

```bash
python -m opmon.adapters.jobkorea --company nhn --probe
```

출력의 status/title/JSON-LD/count후보/read-link/empty마커를 보고
`src/opmon/fingerprints.py`의 `[검증필요]` 값을 실제 문구로 교체한다.
없는 회사명으로도 1회 돌려 empty_markers 실제 문구를 캡처한다.
접근 사다리(requests 200? → 헤더보강 → 채용관 직행 → Playwright) 중 **어디서 통과되는지**가
나머지 잡코리아 15곳 설계를 결정한다. 통과 HTML은 fixture로 박제해 회귀 테스트에 반영.

## 4. 시드 실행 (§2-2, §10-7) — 최초 1회, 알림 없이 DB만

```bash
python -m opmon.pipeline --seed
```

- 공고 알림은 억제되고 `postings`에 현재 공고를 채운다(전부 "기존"으로 등록).
- **운영 이상 alert(차단/의심)는 시드에서도 전송**된다 — 초기 접근 문제를 놓치지 않기 위함.
  시드 실행에서 다수가 transport_error/blocked면 3단계(fingerprint/접근)로 돌아가라.

## 5. 정상 모드 전환

시드가 정상 종료(대부분 OK_*)했으면 이후부터는 `--seed` 없이 실행한다.

```bash
python -m opmon.pipeline
```

스케줄(GitHub Actions cron 11:00 UTC ≈ 07:00 Toronto)이 기본 브랜치에서 자동 발화한다.
부담되면 SPA 그룹만 격일로 조정(§9).

## 6. 운영 점검

- `crawl_errors` 컬렉션을 주간 감사(§8-3). 특정 회사가 반복 SUSPICIOUS/PARSE면 셀렉터 갱신.
- `⚠️ 전체 차단 의심` 요약이 오면 사이트 차단/개편 → fingerprint 점검.
- 공기업 3곳(인천공항·관광공사·주택금융) 공고가 거의 안 잡히면 `narailter_adapter`(job.alio.go.kr) 추가 검토(§11).

## 상태 요약

| 항목 | 상태 |
|---|---|
| 코드 파이프라인 (1~6단계) | ✅ 완료, 테스트 통과 |
| 잡코리아 fingerprint 실측 | ⏳ 네트워크 필요 (3번) |
| SPA/ATS 어댑터 (8단계) | 골격 구축 예정 |
| 현대차 NetFunnel (9단계) | 맨 마지막·실패 허용 |
| 자격증명·시드 실행 | ⏳ 배포 시점 (1·4·5번) |
