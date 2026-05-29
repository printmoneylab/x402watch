# Revenue 이중 카운트 fix — 변경 전후 (EXPECTED DIFF)

`scripts/normalize_chain_merchant_feed.py --apply` +
`cleanup_duplicate_transactions.sql` 가 만드는 변경.

## A. `indexer/merchant_feed.py` 파일 변경

### A.1 모듈 레벨 헬퍼 + 매핑 추가

마지막 top-level `import ...` 줄 바로 다음 라인.

```diff
 import asyncio
 import json
 ...
 from app.db import get_pool
+
+_CHAIN_NORMALIZE_MAP = {
+    "eip155:8453": "base",
+    "eip155:42161": "arbitrum",
+    "eip155:137": "polygon",
+}
+
+
+def normalize_chain(chain):
+    """Normalize CAIP-2 chain identifiers to readable names.
+
+    Known mappings: ``eip155:8453`` → ``base``, ``eip155:42161`` →
+    ``arbitrum``, ``eip155:137`` → ``polygon``. Any ``solana:<address>``
+    → ``solana``. Unknown / unmapped chains (including ``None``) pass
+    through unchanged so this fix can't regress unrelated callers."""
+    if chain is None:
+        return None
+    mapped = _CHAIN_NORMALIZE_MAP.get(chain)
+    if mapped is not None:
+        return mapped
+    if isinstance(chain, str) and chain.startswith("solana:"):
+        return "solana"
+    return chain
+
```

자기완결 — bazaar.py / app.db 등 다른 모듈 의존성 0. 매핑 외 chain
(`base`, `polygon`, 미래의 새 chain, 잘못된 문자열, `None`) 모두 그대로
통과시키므로 EVM / Solana 인덱서 / 다른 호출자 회귀 위험 0.

### A.2 ingest 함수 안 chain 정규화 + 4 곳 교체

target 은 `s.get("chain")` Call 을 가진 유일한 모듈-레벨 FunctionDef.
첫 chain-쓰는 stmt 직전에 두 줄 삽입 + 4 곳 callsite 교체.

```diff
 async def ingest_settlement(c, s):
+    raw_chain = s.get("chain")
+    norm_chain = normalize_chain(raw_chain)
     existing = await c.fetchrow(
         "SELECT 1 FROM transactions WHERE tx_hash = $1 AND chain = $2",
-        s.get("tx_hash"), s.get("chain"),
+        s.get("tx_hash"), norm_chain,
     )
     if existing:
         await c.execute(
             """
             UPDATE transactions
                SET service_id = $3, attribution_source = $4, feed_merchant_id = $5
              WHERE tx_hash = $1 AND chain = $2
             """,
-            s.get("tx_hash"), s.get("chain"),
+            s.get("tx_hash"), norm_chain,
             ...
         )
     else:
         await c.execute(
             """
             INSERT INTO transactions (tx_hash, chain, ...)
             VALUES ($1, $2, ...)
             """,
-            s.get("tx_hash"), s.get("chain"),
+            s.get("tx_hash"), norm_chain,
             ...
         )
```

- spec 의 4 callsite (`:232` dedupe / `:237` UPDATE WHERE / `:249` INSERT
  VALUES / `:250` INSERT row) 가 모두 `norm_chain` 으로 바뀜.
- `s.get("chain")` 의 다른 형태 (`s.get("chain", "base")` 같이 default 인자
  있는 경우) 도 AST 매치는 동일하게 동작.
- 다른 변수 / 함수 / 다른 `s.get(...)` 호출 (예: `s.get("tx_hash")`) 는
  손대지 않음.

### A.3 변경 없음 (보존)

- 모듈 import 블록.
- ingest 함수 시그너처 / docstring / 모든 SQL 문자열 (예: `WHERE tx_hash = $1
  AND chain = $2`) — 그대로.
- 다른 함수 (`_other_helper`, signing, indexer entry 등) — `s.get("chain")`
  안 가지면 무영향.
- `service_id` / `attribution_source` / `feed_merchant_id` / `amount_usd`
  / `is_x402_payment` 등 다른 컬럼 처리 로직.

## B. `transactions` 테이블 상태 변화

### B.1 cleanup 전 (현재)

```
chain          | n_rows   | sum_usd (5월)
---------------|----------|---------------
base           | 5,281    | 58.5410
eip155:8453    | ~2,084   | (KR Crypto 중복)
solana         | 1        | 0.0010
solana:5eyk... | ~14      | (Solana merchant_feed 중복)
arbitrum       | 0        | 0
polygon        | 0        | 0
```

(정확한 수치는 1c / 1e 로 확인. 5월 base sum_usd 가 부풀려진 핵심
시그널 — MetaMask 실잔액 $37 보다 $21 가량 거품.)

### B.2 cleanup 후 (목표 상태)

```
chain     | n_rows   | sum_usd (5월)
----------|----------|---------------
base      | ~3,200   | ~37.0000   ← MetaMask 일치
solana    | 1        | 0.0010
arbitrum  | 0        | 0
polygon   | 0        | 0
```

- `eip155:%` / `solana:<addr>` 0건.
- base row 의 `attribution_source` 가 `'merchant_feed_signed'` (또는
  spec 상의 dup 출처값) 으로 갱신됨.
- `feed_merchant_id` 가 base row 로 이전됨.
- `is_x402_payment = TRUE` 가 base row 에 표시됨.
- `service_id` 가 dup row 의 정확한 값(예: 14391, 14727, 14741) 으로
  갱신.

### B.3 변경 없음 (DB 보존)

- `transactions` 테이블 스키마 (컬럼 / 인덱스 / 제약 / 트리거).
- `services`, `categories`, `merchant_feed_keys`, `recompute_queue`,
  `label_disputes` 등 다른 테이블 — 무관.
- `created_at`, `amount_usd`, `block_number`, `from_addr`, `to_addr`
  등 dup row 가 가져다 줄 게 없는 컬럼 — base row 의 기존값 유지.
- attribution 이 NULL 인 dup row 가 있으면 base 의 attribution 도 NULL 로
  덮어쓰지 않음 (`IS DISTINCT FROM` 조건이 no-op 시 UPDATE 자체를 스킵).

## C. 통계 SQL 36 곳 변화 (재집계 후)

| 모듈 | sites | 동작 |
|---|---|---|
| `indexer/category_stats.py` | 2 | 같은 SQL, 입력 row 수 줄어 정확 |
| `indexer/derive_global.py` | 2 | 같은 SQL, sum 정확 |
| `indexer/labeller.py` | 9 | 같은 SQL |
| `indexer/pair_labels.py` | 5 | 같은 SQL |
| `indexer/seller_flags.py` | 2 | 같은 SQL |
| `app/api.py` | 16 | 같은 SQL — 실시간 매출/통계 API 자동 정정 |

코드 변경 0. 데이터 정정만으로 자동 정확. (재집계 강제 실행이 필요한
모듈만 Step 4 에서 명시적으로 돌림.)

## D. 결과 동작 (시나리오별)

| 상황 | fix 전 | fix 후 |
|---|---|---|
| EVM 인덱서 — Base USDC Transfer → chain='base' INSERT | row 1개 | row 1개 (그대로) |
| KR Crypto merchant_feed — 같은 tx 를 chain='eip155:8453' 으로 post | dedupe miss → INSERT 추가 → row 2개 | dedupe hit → UPDATE → row 1개 |
| Solana 인덱서 — chain='solana' INSERT | row 1개 | row 1개 (그대로) |
| KR Crypto merchant_feed — 같은 tx 를 chain='solana:5eyk...' 으로 post | dedupe miss → INSERT 추가 → row 2개 | dedupe hit → UPDATE → row 1개 |
| 신규 미상 chain (예: chain='aptos') | dedupe miss → INSERT 추가 | dedupe miss → INSERT 추가 (그대로) |
| 5월 매출 SUM | $58.54 (거품) | ~$37 (MetaMask 일치) |
| 통계 SQL 36 곳 | 2 배 부풀림 | 정확 |
| KR Crypto endpoint attribution (service_id 14391/…) | base + dup 둘로 분산 | base 단일 row 로 통합 |
| `is_x402_payment = TRUE` 카운트 | 중복 포함 N | 정확 N/2 |

핵심: chain 정규화가 dedupe 키 일치를 보장 → INSERT-vs-UPDATE 분기
가 항상 정확. 통계 SQL 은 한 줄도 안 고쳐도 됨.
