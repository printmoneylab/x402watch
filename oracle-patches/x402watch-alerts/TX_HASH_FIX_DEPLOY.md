# P3 fix — stats.jsonl payment 이벤트에 tx_hash 추가 — 배포

`app/api.py`의 두 `_stats_write` 호출(`kind="payment"` + `kind="post_settle_fail"`)
과 `_notify_post_settle` 호출에 x402 `X-Payment-Response` 헤더(base64 JSON)
디코드 결과를 주입. payment 6건 vs DB 1건 같은 누락 사례를 tx_hash로
교차 검증 가능하게 만드는 게 목적.

대상: `app/api.py` 단 한 파일. `x402watch-api.service`만 재시작.
PR #36 v2.4 / merchant feed / MCP 알림 / 결제 settle 자체 무관.

---

## Step 1 — 진단 (apply 전, 읽기 전용)

```bash
cd /home/ubuntu/x402watch

# 1a. payment_notify_middleware 전체 흐름 (post_settle_fail 분기 포함)
sed -n '1955,2045p' app/api.py | head -100

# 1b. base64/json 모듈 레벨 import 상태 (헬퍼는 lazy import 라 무관 — 참고용)
grep -nE "^import base64|^import json|^from base64|^from json" app/api.py

# 1c. 현재 stats.jsonl payment 이벤트 스키마 baseline
grep '"kind": "payment"' /home/ubuntu/x402watch/var/stats.jsonl 2>/dev/null \
  | tail -2 | python3 -m json.tool 2>/dev/null
# expect: tx_hash / network / buyer_wallet 필드 부재

# 1d. log 모듈 레벨 바인딩 (헬퍼 분기 결정)
grep -nE "^log\s*=" app/api.py | head -3
# expect: log = logging.getLogger(...) 한 줄
#   ─ 있으면: 패처가 `log.warning(...)` 버전 헬퍼 삽입
#   ─ 없으면: 패처가 `logging.getLogger(__name__).warning(...)` 폴백 자동 사용

# 1e. _stats_write({"kind":"payment"|"post_settle_fail"}) 호출 카운트 — 정확히 1 + 1 이어야 함
grep -cE '_stats_write\(\{"kind": ?"payment"' app/api.py
grep -cE '_stats_write\(\{"kind": ?"post_settle_fail"' app/api.py
# expect: 1 / 1 (멀티라인이라 ast 매칭 기준 결과는 다를 수 있음 — 지표용)

# 1f. post-settle 알림 호출 — 정확히 1개 + tx_hash=None/payer_wallet=None
# (alias `_notify_post_settle` 또는 canonical `notify_post_settle_failure` 어느 쪽이든 매칭)
grep -nB1 -A8 -E "_notify_post_settle\(|notify_post_settle_failure\(" app/api.py | head -30
# expect: tx_hash=None, payer_wallet=None 라인 보임

# 1g. 헬퍼 / 패처 흔적 — 재실행 시 idempotent 동작 확인용
grep -n "_decode_x_payment_response" app/api.py
# expect: 미적용 상태에서 빈 결과; 적용 후에는 def + 호출 두 군데
```

**기대 (정상, 미적용 상태)**:
- 1a에서 `response = await call_next(request)` 직후 5xx + x-payment 체크 →
  `_stats_write({"kind": "post_settle_fail", …})` + `_notify_post_settle(…)`
- 1a 더 아래에 `_enrich_and_notify` 안에서 `_stats_write({"kind":"payment",…})`
- 1c에 tx_hash 필드 없음, ts/kind/endpoint/amount_usd/ip/ipinfo 등 7개
- 1d에 `log = logging.getLogger(…)` 한 줄 (있는 경우 with-log 헬퍼)
- 1e 둘 다 1 (멀티라인은 grep 카운트가 0/1 갈릴 수 있음 — 패처가 AST로 재검증)
- 1f에 `tx_hash=None`, `payer_wallet=None` 두 줄 정확히 1쌍
- 1g 빈 결과

**분기**:
- 1d에 `log = ` 가 모듈 레벨에 없음 → 패처가 자동으로 `logging.getLogger(__name__)`
  폴백 버전 삽입. 진행 OK.
- 1e 결과가 0/1 = grep 카운트일 수도 있음(멀티라인). 그래도 패처의 AST
  매치는 `_stats_write` Call + 첫 인자 Dict 의 `"kind"` 키 상수값으로
  하므로 결과가 비신뢰. **진짜 정답은 dry-run 노트**.
- 1f에 둘 다 0개 → api.py 가 post-settle 알림을 다른 이름으로 호출.
  패처는 `_notify_post_settle` + `notify_post_settle_failure` 두 이름
  모두 매칭 + `tx_hash`/`payer_wallet` kwarg 동반 조건으로 필터하므로
  drift 가 아닌 진짜 없음. 1a 의 post_settle_fail 블록 paste 요청.
- 1f에 2개 이상 → 같은 시그너처의 호출이 둘 이상. 패처가 `expected
  exactly 1` 로 abort. 1a 블록 paste 요청.

## Step 2 — 패처 적용

```bash
cd /home/ubuntu/x402watch
# (Oracle은 git repo 아님 — 맥북 git repo에서 SCP)
cp oracle-patches-x402watch-alerts/add_tx_hash_to_payment.py \
   scripts/add_tx_hash_to_payment.py

# (선택) 합성 fixture self-test — 실제 api.py 안 건드림
venv/bin/python scripts/add_tx_hash_to_payment.py --self-test

# dry-run — plan 출력 (실제 api.py 대상)
venv/bin/python scripts/add_tx_hash_to_payment.py

# 적용 (백업 자동: api.py.bak.tx-hash-fix-YYYYMMDD-HHMM)
venv/bin/python scripts/add_tx_hash_to_payment.py --apply

# 재시작 (api.py만 수정 — MCP 서비스 무관)
sudo systemctl restart x402watch-api
sudo systemctl is-active x402watch-api        # expect: active
sudo journalctl -u x402watch-api -n 30 --no-pager | grep -E "ERROR|Traceback|startup"
```

dry-run 기대 출력 (미적용 상태):
```
✓ insert helper _decode_x_payment_response (with log.warning)
✓ payment _stats_write at line <N>: insert settle_info + tx_hash/network/buyer_wallet keys
✓ post_settle_fail _stats_write at line <N>: insert settle_info + tx_hash/network/buyer_wallet keys
✓ _notify_post_settle at line <N>: tx_hash + payer_wallet rewritten to settle_info[…]
✓ ast.parse OK
(dry-run — re-run with --apply to write)
```

재실행 (이미 적용된 상태):
```
◌ helper _decode_x_payment_response already present — keep
◌ payment _stats_write at line <N> already has tx_hash — keep
◌ post_settle_fail _stats_write at line <N> already has tx_hash — keep
◌ _notify_post_settle at line <N> kwargs already non-None — keep
(nothing to do — already fully patched)
```

## Step 3 — 회귀 검증

```bash
cd /home/ubuntu/x402watch

# 3a. import + 헬퍼 노출
venv/bin/python -c "
from app.api import _decode_x_payment_response as d
print('helper import OK')
# 빈 헤더 → None 폴백
print('empty:', d(''))
# 가짜/깨진 헤더 → None 폴백 (예외 흡수)
print('broken:', d('not-base64-at-all'))
# success=true 인 정상 payload
import base64, json
ok = base64.b64encode(json.dumps({
  'success': True,
  'transaction': '0xabc123',
  'network': 'base',
  'payer': '0x1234'
}).encode()).decode()
print('ok:', d(ok))
# success=false → None
fail = base64.b64encode(json.dumps({'success': False}).encode()).decode()
print('fail:', d(fail))
"
# expect:
#   empty:  {'tx_hash': None, 'network': None, 'buyer_wallet': None}
#   broken: {'tx_hash': None, 'network': None, 'buyer_wallet': None}
#   ok:     {'tx_hash': '0xabc123', 'network': 'base', 'buyer_wallet': '0x1234'}
#   fail:   {'tx_hash': None, 'network': None, 'buyer_wallet': None}

# 3b. PR #36 v2.4 헤더 유지 (이 fix와 무관해야 함)
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.4

# 3c. paid 402 응답 cache-control 유지 (P3 PR #138 v2.4 회귀 가드)
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(cache-control|x-x402-rewriter):"
# expect: cache-control: no-store / x-x402-rewriter: v2.4

# 3d. MCP probe (api 서비스와 별개 서비스지만 무회귀 가드용)
curl -sS -m 15 https://api.x402.printmoneylab.com/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "User-Agent: ClaudeCodeProbe/1.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  | head -c 200
echo

# 3e. (가능하면) Moa owner-test 결제 1회 → stats.jsonl 새 payment 라인 확인
tail -F /home/ubuntu/x402watch/var/stats.jsonl &
TAIL_PID=$!
# (별 터미널에서 결제 1회 실행)
# 10초 후
sleep 10; kill $TAIL_PID 2>/dev/null

# stats.jsonl 최신 payment 이벤트의 새 3 필드
grep '"kind": "payment"' /home/ubuntu/x402watch/var/stats.jsonl \
  | tail -1 | python3 -c "
import sys, json
r = json.loads(sys.stdin.read())
print('tx_hash:     ', r.get('tx_hash'))
print('network:     ', r.get('network'))
print('buyer_wallet:', r.get('buyer_wallet'))
"
# expect (정상 결제 시): 3 필드 모두 실값
#        (가짜 헤더/디코드 실패 시): 3 필드 모두 None — 기존 동작 유지

# 3f. DB 교차 검증 (이게 이 fix 의 최종 목적)
psql -c "
SELECT s.ts, s.tx_hash, s.network, s.buyer_wallet,
       t.tx_hash IS NOT NULL AS in_db
FROM (
  SELECT (l->>'ts')::timestamptz AS ts,
         l->>'tx_hash' AS tx_hash,
         l->>'network' AS network,
         l->>'buyer_wallet' AS buyer_wallet
  FROM regexp_split_to_table(pg_read_file('/home/ubuntu/x402watch/var/stats.jsonl'), E'\n') AS line,
       LATERAL (SELECT line::json AS l) j
  WHERE line LIKE '%\"kind\": \"payment\"%'
    AND line ~ '\"ts\": \"2026-05-2'
) s
LEFT JOIN transactions t ON t.tx_hash = s.tx_hash
ORDER BY s.ts DESC LIMIT 20;
"
# expect (24h 누적 후): in_db = true 가 정상. false 행이 있으면
# stats.jsonl 에는 있지만 DB 에 없는 결제 = 누락 추적 가능.
```

## Step 4 — 24h 후 누락 진단

```bash
# 이번 달 stats.jsonl payment vs DB transactions 교차 (fix 의 최초 목표)
psql -c "
WITH stats AS (
  SELECT l->>'tx_hash' AS tx_hash, l->>'network' AS network
  FROM regexp_split_to_table(pg_read_file('/home/ubuntu/x402watch/var/stats.jsonl'), E'\n') AS line,
       LATERAL (SELECT line::json AS l) j
  WHERE line LIKE '%\"kind\": \"payment\"%'
    AND line ~ '\"ts\": \"2026-05-'
    AND l->>'tx_hash' IS NOT NULL
)
SELECT stats.network, COUNT(*) AS stats_count,
       COUNT(t.tx_hash) AS in_db_count,
       COUNT(*) - COUNT(t.tx_hash) AS missing_from_db
FROM stats LEFT JOIN transactions t ON t.tx_hash = stats.tx_hash
GROUP BY stats.network ORDER BY stats.network;
"
# 5월 6건 vs DB 1건 = 5건 누락 시나리오를 tx_hash 단위로 정확히 짚을 수
# 있게 됨. missing_from_db = 0 이면 fix 이후 새 결제는 모두 DB와 일치.
```

## Step 5 — 롤백

```bash
cd /home/ubuntu/x402watch/app
ls -t api.py.bak.tx-hash-fix-* | head -1
cp "$(ls -t api.py.bak.tx-hash-fix-* | head -1)" api.py
sudo systemctl restart x402watch-api
```

롤백은 stats.jsonl payment 이벤트가 다시 tx_hash 없는 스키마로 돌아간다
(DB 교차 불가 상태 복귀). fix 자체에 문제가 있을 때만. 디코드 실패는
None 폴백으로 흡수되므로 헤더 부재/형식 변경이 롤백 사유가 되는 경우는
거의 없다.

## 안전장치 (요약)

- `app/api.py` 단일 파일 수정. 다른 파일/서비스 무변경.
- 헬퍼는 lazy import (base64, json) — 모듈 import 블록 무변경.
- `_decode_x_payment_response` 는 어떤 입력에도 raise 안 함 → request 경로
  에러 없음. 결제 settle 자체 무영향.
- payment 알림 텔레그램 포맷(`_format_alert`) 무변경. dedupe / owner_test /
  redis_client 로직 무변경.
- daily_summary / merchant_feed / PR #36 v2.4 / Tier 2/3 daily / CF IP fix
  무관.
- 디코드 실패 시 새 3 필드만 None. 기존 7 필드는 정상 기록.
