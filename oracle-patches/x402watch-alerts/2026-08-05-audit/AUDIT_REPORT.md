# x402watch 데이터 감사 — 2026-08-05

## 판정: READY (B2 fix 후)
Trust Score API 착수 가능. buyer_labels(37K) + seller_flags(4.8K) + buyer_seller_labels(52K) + services.suspected_wash_pct(3.7K) 4개 원료로 산출 가능.

## 해결
- B2: reconcile SELECT id 제거 (transactions에 id 컬럼 없음, PK=time/chain/tx_hash). 5/29 스크립트 작성 시 잘못 가정. reconcile 5/29~8/5 매시간 실패했던 근본 원인.
- B1: 오판. wash_scores 0 rows는 v1.1 예약 스키마. 워시 판정은 seller_flags/buyer_labels/services.suspected_wash_pct에 정상 저장.

## 미해결 (Trust API 설계 시 반영)
- Y1: duplicate tx_hash 107 groups (인덱서 재시도). ON CONFLICT (tx_hash,chain) 필요.
- Y2: 6월 x402 0건 (merchant-feed 중단기). 백필 불가. "as of" 날짜 명시로 대응.
- Y4/Y5/Y6: 봇/owner_test/amount<=0 필터 (산출 시 exclude).
- Y11: 대소문자 정규화 (조회 LOWER, 응답 checksum).
- Y9: backup 테이블 310MB DROP 가능.

## 커버리지
unique buyers 23,311, buyer_labels 37,434 (가시성 90%+), seller_flags 4,797.
