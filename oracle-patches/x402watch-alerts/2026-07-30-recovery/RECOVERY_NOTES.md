# 2026-07-30 2달 방치 후유증 복구

5/29~7/30 방치 기간 발견된 4개 이슈 fix. 파일은 Oracle 실제 적용본 스냅샷.

## 1. merchant_feed.py — UnboundLocalError fix
5/29 chain normalize patcher가 `raw_chain = s.get("chain")` / `norm_chain`을
for 루프 밖에 잘못 삽입 → 매시간 UnboundLocalError → merchant-feed 2달 중단.
fix: 두 줄을 `for s in body.get("settlements", []):` 루프 안으로 이동.

## 2. bazaar.py — NUL byte strip
carbon-cashmere.de description에 NUL(0x00) → PostgreSQL UTF8 거부 → 매시간 errors=1.
fix: upsert_service에서 모든 string 필드 `.replace('\x00','')`.

## 3. app/api.py — P3 tx_hash 헤더명 fix
P3(5/29)가 legacy 헤더 `x-payment-response`를 읽는데 x402 SDK 2.8.0은
`PAYMENT-RESPONSE` 사용 → tx_hash 2달간 None → reconcile 무용지물.
fix: `payment-response` 우선 + `x-payment-response` fallback (api.py 1964, 2023).
SDK: SettleResponse 필드 transaction/network/payer, base64 인코딩 (헬퍼 로직은 정상).

## 4. run_reconcile.sh (신규) + x402watch-reconcile.service
systemd inline DSN 조립이 POSTGRES_PASSWORD 특수문자 이스케이프 깨짐
→ InvalidPasswordError 매시간. fix: wrapper 스크립트로 source .env 후 DSN 조립.
service ExecStart을 wrapper로 교체, EnvironmentFile 제거.

## 상태: 4개 전부 Oracle 적용 완료 + 검증 완료 (2026-07-30)
