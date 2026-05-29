# P1 fix — x402watch attribution reconciliation — 변경 전후 (EXPECTED DIFF)

`scripts/reconcile_x402watch_attribution.py --apply` 가 transactions
테이블에 만드는 변화. 신규 파일 1개라 file diff 는 없음 — 변화는 DB
상태에만 있음.

## 1. 매핑 (스크립트 hard-code)

```python
ENDPOINT_TO_SERVICE_ID = {
    "/api/v1/services/{service_id}/wash-detail":   3268993,
    "/api/v1/wash/check":                          7604654,
    "/api/v1/categories/{slug}/full-history":      7604655,
    "/api/v1/services/{service_id}/transactions":  7604656,
    "/api/v1/buyers/{address}/profile":            7604657,
}
SERVICE_PRICE_USD = {
    3268993: 0.005, 7604654: 0.05, 7604655: 0.020,
    7604656: 0.010, 7604657: 0.005,
}
```

- 5개만. 다른 endpoint (예: `/api/v1/categories/{slug}` 무료, KR Crypto
  endpoint 등) 는 `skipped_unmapped_endpoint` 로 자동 통과.
- `{name}` (FastAPI 스타일) + `:name` (DB colon-prefix) 모두 인식 →
  `[^/]+` 정규식으로 변환되어 concrete URL 매칭.
- 가격 검증은 5% 오차 허용 — settle 시 fee/slippage 흡수.

## 2. 회귀 상태 → reconcile 후 분포 예측

P3 fix 이후 발생한 신규 결제 1건이 wash/check ($0.05) 였다고 가정.

### 변경 전 (회귀 상태)

| service_id | 서비스 | db_payments | 비고 |
|---|---|---|---|
| 3268993 | wash-detail | (자기 결제 + 흡수된 buyers/profile) | EVM `(seller, amount=$0.005)` MIN(id) → 3268993 |
| 7604654 | wash/check | 0 | 자기 결제도 다른 sid 로 흡수 (예: 또 3268993 또는 인접 sid) |
| 7604655 | full-history | 0 | 자기 결제도 흡수 |
| 7604656 | transactions | 0 | 자기 결제도 흡수 |
| 7604657 | buyers/profile | 0 | 자기 결제 5건 모두 3268993 으로 흡수 |
| 14741 | kr-sentiment | (KR Crypto 결제 + 흡수된 wash/check 2건) | EVM `(seller, amount=$0.05)` MIN(id) → 14741 |

### 변경 후 (reconcile 적용)

스크립트가 stats.jsonl 의 tx_hash → endpoint 페어를 따라 transactions
row 를 권한 있는 service_id 로 갱신:

| service_id | 서비스 | db_payments | 비고 |
|---|---|---|---|
| 3268993 | wash-detail | 자기 결제만 (흡수분 빠짐) | buyers/profile 흡수분이 7604657 로 이전 |
| 7604654 | wash/check | 자기 결제 (흡수 풀림) | 14741 로 흡수됐던 wash/check tx 가 옮겨옴 |
| 7604655 | full-history | 자기 결제 (있다면) | |
| 7604656 | transactions | 자기 결제 (있다면) | |
| 7604657 | buyers/profile | 자기 결제 5건 (P3 이전 6건 중) | 3268993 에서 옮겨옴 |
| 14741 | kr-sentiment | KR Crypto 결제만 (흡수 풀림) | wash/check 2건이 7604654 로 이전 |

⚠ 단, **P3 fix 이전 발생한 5월 6건은 reconcile 불가**. tx_hash 가
stats.jsonl 에 없어서 매칭 키 부재. → `skipped (no tx_hash, pre-P3)`
6 으로 집계되고 DB 미변경. 백필이 필요하면 별도 P0 (인덱서가
재indexing 하면서 stats.jsonl 결제 시각과 매칭).

### 5월 매출 (PrintMoneyLab x402watch portion) 영향

매출 sum 자체는 변하지 않음. amount * row 합은 동일. 변하는 것은:
- 매출이 **올바른 service_id 로 카운트**됨
- 5개 endpoint 별 dashboard 그래프가 0 에서 실값으로 바뀜
- kr-sentiment / wash-detail 그래프가 흡수분만큼 감소

매출 ($37.57) 또는 unique tx_hash 합은 chain normalize fix (이미 적용
완료, `8307229`) 가 끝낸 일이라 이번 reconcile 과 무관.

## 3. row 별 변화 (예시)

reconcile 대상 row 1 행의 변화:

```diff
 -- transactions row (tx_hash = '0x8f3d...')
 id                  : 12345
 tx_hash             : 0x8f3d...
 chain               : base
-service_id          : 3268993            -- EVM 인덱서 MIN(id) 충돌 결과
+service_id          : 7604657            -- stats.jsonl endpoint 기반 정답
-attribution_source  : (NULL)
+attribution_source  : x402watch_reconcile
-is_x402_payment     : false              -- (또는 true; 인덱서 설정 따라)
+is_x402_payment     : true
 amount              : 0.005
 buyer_wallet        : 0xABC...
 seller_wallet       : 0xDEF...
 time                : 2026-05-29 20:00:00+09
 -- (다른 모든 필드 변경 없음)
```

- 보존: `id`, `tx_hash`, `chain`, `amount`, `buyer_wallet`,
  `seller_wallet`, `time`, `block_number`, `tx_index`, `feed_merchant_id`
  등 사실 데이터.
- 갱신: `service_id`, `attribution_source`, `is_x402_payment` 3 필드.

## 4. 회귀 가드 (스크립트 동작 매트릭스)

| stats.jsonl 이벤트 상태 | 스크립트 동작 |
|---|---|
| `kind != "payment"` | 무시 (loop 가 yield 안 함) |
| `tx_hash` 없음 (P3 이전) | `skipped_no_tx_hash` |
| `ts < --since` | `skipped_before_since` |
| `endpoint` 가 매핑 5개 외 | `skipped_unmapped_endpoint` + DEBUG 로그 |
| `amount_usd` 가 canonical 가격 ±5% 밖 | `skipped_amount_mismatch` + WARNING |
| `tx_hash` 가 transactions 에 없음 | `not_found_in_db` + DEBUG |
| DB 의 `service_id` 가 이미 정답 | `already_correct` (no-op) |
| DB 의 `service_id` ≠ 정답 (dry-run) | `would_update` (롤백) |
| DB 의 `service_id` ≠ 정답 (--apply) | `updated` + UPDATE 1건 + INFO 로그 |

모든 분기에서 **DELETE / INSERT 없음**. 잘못 매핑된 reconcile 도
`attribution_source = 'x402watch_reconcile'` 태그로 식별 + 롤백 가능.

## 5. 보존되는 것 (무변경)

| 영역 | 이유 |
|---|---|
| EVM 인덱서 (`indexer/evm_indexer.py` 또는 그에 상응) | 본 fix 는 사후 reconcile — 인덱서 자체는 손대지 않음. 다음 인덱서 사이클이 같은 회귀를 만들면 cron 의 다음 실행이 다시 정정함 |
| `services` 테이블 | reconcile 은 `transactions` 만 UPDATE. 가격 / URL 정의는 services 에 불변 |
| `stats.jsonl` | 읽기 전용. 어떤 파일도 수정 안 함 |
| PR #36 v2.4 / merchant_feed chain normalize / 알림 dedupe / payment settle | 모두 다른 경로 |
| 다른 service_id 의 attribution | 매핑 5개 외 endpoint 결제는 자동 skip — 회귀 위험 0 |
| `is_x402_payment` 기존 TRUE row | 한 번 더 TRUE 로 UPDATE 해도 변화 없음 (idempotent) |
| `feed_merchant_id` | reconcile 이 손대지 않음. chain normalize fix 가 채운 값 보존 |

## 6. cron / systemd timer 운영 시 예상 동작

매 1시간 (RandomizedDelaySec=300 으로 5분 분산) 실행:
1. stats.jsonl 의 P3 이후 payment 전체 스캔 (수만 줄도 sub-second)
2. 이미 정답 sid 는 `already_correct` 로 통과 (대부분)
3. 새로 들어온 결제 중 인덱서가 잘못 attribution 한 행만 UPDATE
4. 로그 1줄/UPDATE: `reconciled tx=0x... service_id <old> → <new>`

장기적으로 시간당 평균 UPDATE 수는 신규 x402watch 결제 빈도에 비례.
0 이 일반적 (즉시 정답 attribution 되는 결제가 대부분), 가끔 1~수건.
