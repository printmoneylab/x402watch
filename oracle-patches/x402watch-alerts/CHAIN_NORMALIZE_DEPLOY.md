# Revenue 이중 카운트 회귀 fix — merchant_feed chain 정규화 + DB cleanup

`indexer/merchant_feed.py` 가 `chain='eip155:8453'` (CAIP-2) 로 dedupe
SELECT 을 던지는데 EVM 인덱서는 이미 같은 결제를 `chain='base'` 로
INSERT 해둔 상태 → dedupe 실패 → 신규 INSERT → 같은 tx_hash 두 row.
36개 통계 SQL 중 chain 필터를 가진 곳이 없어서 KR Crypto 결제마다 2배
집계. 5월 매출 DB sum **$58.54** vs MetaMask 실잔액 **$37** = $21.5 거품.

이 fix 는 (1) merchant_feed.py 안에 `normalize_chain` 헬퍼 + `norm_chain`
바인딩으로 dedupe 가 항상 readable chain (`base`/`solana`/…) 으로 던지게
하고, (2) 이미 DB 에 쌓인 CAIP-2 / `solana:<addr>` 중복 row 의 attribution
을 base row 로 이전한 뒤 dup row 들을 DELETE. 통계 SQL 36곳은 손대지
않음 — chain 정규화 후 자동으로 정확해짐.

대상:
- `indexer/merchant_feed.py` (패처 1개 파일)
- `transactions` 테이블 (cleanup SQL 1개 트랜잭션)

재시작:
- `x402watch-api` / `x402watch-mcp` 불필요 (인덱서 다음 실행 시 자동 적용)
- `x402watch-indexer` 또는 cron-driven 인덱서 → 다음 사이클부터 정규화 적용

순서 강제: **패처 먼저, DB cleanup 그 다음**. 순서 반대로 하면 cleanup
직후 다음 merchant_feed 실행이 다시 중복을 생성.

---

## Step 0 — 백업 권장

```bash
# DB 백업 (cleanup 직전 권장 — 약 1~2분)
sudo docker exec x402watch-postgres pg_dump -U x402watch -d x402watch \
  --table=transactions --data-only --file=/tmp/transactions.pre-chain-norm.sql
sudo docker cp x402watch-postgres:/tmp/transactions.pre-chain-norm.sql \
  /home/ubuntu/backups/transactions.pre-chain-norm.$(date +%Y%m%d-%H%M).sql
ls -la /home/ubuntu/backups/transactions.pre-chain-norm.*.sql | tail -1
```

(파일 패처는 KST 백업 자동 — `.bak.chain-norm-YYYYMMDD-HHMM`)

## Step 1 — 진단 (읽기 전용)

```bash
cd /home/ubuntu/x402watch

# 1a. merchant_feed.py 의 chain field 첫 등장 (anchor 확인용)
grep -nE "s\.get\([\"']chain" indexer/merchant_feed.py

# 1b. 기존 정규화 함수 (bazaar.py NETWORK_MAP / app/db normalize_network 등)
grep -rnE "def normalize_(network|chain)|NETWORK_MAP" indexer/ app/ 2>/dev/null

# 1c. 중복 row 전체 카운트 (cleanup 영향 범위)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT chain, COUNT(*) AS n
  FROM transactions
 WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%'
 GROUP BY chain
 ORDER BY chain;"

# 1d. orphan 검증 — 모든 dup 이 base 짝 보유하는지 (cleanup 안전 게이트)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT
  (SELECT COUNT(*) FROM transactions
    WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%') AS dup_total,
  (SELECT COUNT(*) FROM transactions dup
    WHERE (dup.chain LIKE 'eip155:%' OR dup.chain LIKE 'solana:%')
      AND NOT EXISTS (
        SELECT 1 FROM transactions base
         WHERE base.tx_hash = dup.tx_hash
           AND base.chain IN ('base', 'arbitrum', 'polygon', 'solana')
      )) AS orphans;"
# expect: orphans = 0  → cleanup 안전
#         orphans > 0 → STOP, Moa 보고. cleanup SQL 의 안전 가드가 자동
#                       으로 RAISE EXCEPTION → ROLLBACK 도 함.

# 1e. 5월 매출 baseline (DB 현재 = 거품 포함값)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT chain, COUNT(*) AS n_rows,
       ROUND(SUM(amount)::numeric, 4) AS sum_usd
  FROM transactions
 WHERE time >= '2026-05-01' AND time < '2026-06-01'
 GROUP BY chain ORDER BY chain;"
# expect (대략): base 5,281 row $58.54, eip155:8453 ~중복분 (KR Crypto)

# 1f. 패처 idempotency probe — 이미 적용됐는지
grep -n "def normalize_chain" indexer/merchant_feed.py
grep -n "norm_chain = " indexer/merchant_feed.py
# expect (미적용): 둘 다 빈 결과
# expect (적용 후): 각각 1줄
```

**분기**:
- 1b 에 `normalize_network` / `NETWORK_MAP` 존재 → 패처는 그래도 자기
  완결 `normalize_chain` 을 inline 삽입 (의존성 0). 이미 있는 다른 정규화
  와 충돌 안 함 (이름 다름).
- 1d 의 `orphans > 0` → cleanup SQL 의 `DO $$` 가드가 자동 RAISE
  EXCEPTION → 트랜잭션 ROLLBACK. **STOP**, Moa 보고. orphan 의 tx_hash
  를 조사 후 수동 처리.
- 1f 둘 다 결과 있음 → 이미 적용 상태. dry-run 시 패처가
  "(nothing to do)" 로 끝남. cleanup SQL 도 idempotent — 다시 돌려도 0건.

## Step 2 — merchant_feed.py 패처 적용

```bash
cd /home/ubuntu/x402watch

# SCP (Moa 맥북에서)
cp oracle-patches-x402watch-alerts/normalize_chain_merchant_feed.py \
   scripts/normalize_chain_merchant_feed.py

# self-test (합성 fixture — 실제 indexer 안 건드림)
venv/bin/python scripts/normalize_chain_merchant_feed.py --self-test

# dry-run
venv/bin/python scripts/normalize_chain_merchant_feed.py

# 적용 (백업 자동: merchant_feed.py.bak.chain-norm-YYYYMMDD-HHMM)
venv/bin/python scripts/normalize_chain_merchant_feed.py --apply

# import 검증
venv/bin/python -c "
from indexer.merchant_feed import normalize_chain
assert normalize_chain('eip155:8453') == 'base'
assert normalize_chain('eip155:42161') == 'arbitrum'
assert normalize_chain('eip155:137') == 'polygon'
assert normalize_chain('solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp') == 'solana'
assert normalize_chain('base') == 'base'
assert normalize_chain('unknown') == 'unknown'
assert normalize_chain(None) is None
print('normalize_chain mapping OK')
"
```

dry-run 기대 (미적용 상태):
```
✓ insert helper normalize_chain (+ _CHAIN_NORMALIZE_MAP)
  target function: <ingest 함수명> (line <N>)
✓ <fn>: insert raw_chain + norm_chain assigns (before stmt at line <N>)
✓ <fn>: replace 4 `s.get("chain")` Calls with `norm_chain`
✓ ast.parse OK
(dry-run — re-run with --apply to write)
```

재실행 (이미 적용된 상태):
```
◌ helper normalize_chain already present — keep
  target function: <fn> (line <N>)
◌ <fn> already binds `norm_chain` — function body considered already patched
(nothing to do — already fully patched)
```

**다중 ingest 함수 분기**: 패처가 `multiple FunctionDefs contain s.get("chain")`
로 abort 하면 merchant_feed.py 가 ingest 함수를 둘 이상 갖고 있다는 뜻.
`--target-fn <name>` 같은 옵션은 안 만들었으니 — 이 경우 paste 요청.

## Step 3 — DB cleanup SQL 실행

```bash
cd /home/ubuntu/x402watch
cp oracle-patches-x402watch-alerts/cleanup_duplicate_transactions.sql \
   /tmp/cleanup_duplicate_transactions.sql

# Step 3a — dry-run (COMMIT → ROLLBACK 치환, 변화 0 확인)
sed 's/^COMMIT;$/ROLLBACK;/' /tmp/cleanup_duplicate_transactions.sql \
  | sudo docker exec -i x402watch-postgres \
        psql -U x402watch -d x402watch
# 출력 확인:
#   === BEFORE === : 중복 row 카운트
#   === safety guard === : orphan_duplicate_rows = 0  ← 필수
#   === Step A === : UPDATE 진행 (영향 row 수)
#   === Step B === : DELETE 진행 (영향 row 수)
#   === AFTER === : 남은 CAIP-2/solana:<addr> = 0
#   ROLLBACK (변화 없음)
#
# 만약 "STOP: N orphan ..." 메시지가 보이면 → 1d 결과와 일치해야 함.
# orphan > 0 이면 자동 ROLLBACK + Moa 보고.

# Step 3b — 진짜 적용
sudo docker exec -i x402watch-postgres \
  psql -U x402watch -d x402watch \
  -f /tmp/cleanup_duplicate_transactions.sql
# 마지막 줄: COMMIT
```

(dry-run 출력의 `Step A` UPDATE row 수와 `Step B` DELETE row 수는
1c 의 `n` 합과 거의 일치해야 함. UPDATE 가 더 작을 수 있음 — base 가
이미 같은 attribution 을 갖고 있어 UPDATE 가 no-op 된 경우.)

## Step 4 — 통계 재집계

```bash
cd /home/ubuntu/x402watch

# (모듈 경로는 환경에 따라 다를 수 있음 — 1b 와 같이 로컬 grep 결과 기준
# 으로 조정. 보통 indexer 패키지 안에 있음.)
venv/bin/python -m indexer.category_stats
venv/bin/python -m indexer.derive_global
venv/bin/python -m indexer.labeller
venv/bin/python -m indexer.pair_labels    2>/dev/null || true
venv/bin/python -m indexer.seller_flags   2>/dev/null || true

# 인덱서가 systemd timer / cron 으로 돌면 즉시 1회 강제 실행:
sudo systemctl start x402watch-indexer  2>/dev/null || true
```

만약 모듈 경로가 다르면 (예: `app.indexer.category_stats`) 1b 의 결과
로 조정. 모든 stat SQL 36곳은 chain 필터 없음 — 단순히 재집계만
하면 자동 정확해짐.

## Step 5 — 회귀 검증

```bash
# 5a. 중복 row 0건
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT COUNT(*) AS remaining_caip2_or_solana_addr
  FROM transactions
 WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%';"
# expect: 0

# 5b. 5월 매출 — MetaMask $37 과 일치
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT chain, COUNT(*) AS n_rows,
       ROUND(SUM(amount)::numeric, 4) AS sum_usd
  FROM transactions
 WHERE time >= '2026-05-01' AND time < '2026-06-01'
 GROUP BY chain ORDER BY chain;"
# expect: 총합 ≈ $37 ± $1, base / solana / … 만 (eip155:%, solana:% 없음)

# 5c. KR Crypto endpoint attribution 보존 (service_id 14391/14727/14741 등)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT service_id, COUNT(*) AS n_tx,
       ROUND(SUM(amount)::numeric, 4) AS sum_usd,
       MAX(attribution_source) AS attr
  FROM transactions
 WHERE service_id IN (14391, 14727, 14741)
   AND time >= '2026-05-01'
 GROUP BY service_id ORDER BY service_id;"
# expect: 각 service_id 의 attribution_source 가 merchant_feed_signed 또는
#         spec 상의 정상 값. is_x402_payment = TRUE.

# 5d. 다음 merchant_feed 호출 시 신규 중복 미발생 — 인덱서 1 사이클 후
sudo systemctl start x402watch-indexer  2>/dev/null || \
  venv/bin/python -m indexer.merchant_feed
sleep 30
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT COUNT(*) AS new_caip2
  FROM transactions
 WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%';"
# expect: 0  (정규화된 chain 으로 dedupe SELECT → UPDATE 분기로 진입)

# 5e. PR #36 v2.4 헤더 / MCP 알림 / 결제 settle 무회귀
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.4

curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(cache-control|x-x402-rewriter):"
# expect: cache-control: no-store / x-x402-rewriter: v2.4
```

## Step 6 — 롤백

```bash
# 6a. merchant_feed.py 백업 복구
cd /home/ubuntu/x402watch/indexer
ls -t merchant_feed.py.bak.chain-norm-* | head -1
cp "$(ls -t merchant_feed.py.bak.chain-norm-* | head -1)" merchant_feed.py

# 6b. DB 백업에서 transactions 복구 (Step 0 백업 사용)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
  TRUNCATE TABLE transactions;
"
sudo docker cp /home/ubuntu/backups/transactions.pre-chain-norm.<TS>.sql \
  x402watch-postgres:/tmp/restore.sql
sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch \
  -f /tmp/restore.sql

# 6c. 통계 재집계
cd /home/ubuntu/x402watch
venv/bin/python -m indexer.category_stats
venv/bin/python -m indexer.derive_global
venv/bin/python -m indexer.labeller
```

롤백은 중복 row 다시 만들어 매출이 다시 $58 로 돌아간다. fix 자체에
실제 회귀가 있을 때만. `normalize_chain` 은 매핑 외 chain 그대로 통과
시키므로 회귀 위험 0 — 롤백 사유가 되는 경우는 거의 없다.

## 안전장치 (요약)

- `indexer/merchant_feed.py` 단일 파일 수정. EVM/Solana 인덱서 / 통계
  코드 36곳 / 알림 / 결제 settle / merchant feed signing / PR #36 v2.4
  무관.
- `normalize_chain` 은 매핑 외 chain 그대로 통과 — 미래에 등장할 새
  chain 자동 호환.
- cleanup SQL 은 BEGIN/COMMIT 트랜잭션 — `RAISE EXCEPTION` 시 자동
  ROLLBACK.
- 안전 가드: orphan dup (matching base row 없음) > 0 이면 무조건
  EXCEPTION → 데이터 손실 0 보장.
- UPDATE 가 idempotent 조건 (`IS DISTINCT FROM`) 으로 감싸있어 재실행
  안전.
- DB pg_dump 백업 권장 (Step 0).
