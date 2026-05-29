# P1 fix — x402watch attribution reconciliation — 배포

`scripts/reconcile_x402watch_attribution.py` 는 P3 fix 가 stats.jsonl
에 박은 `tx_hash` + `endpoint` 페어를 권한 있는 진실로 사용해 5개
x402watch endpoint 결제가 잘못된 service_id 로 흡수된 row 를 한 행씩
교정. EVM 인덱서의 `(seller, amount_micro)` MIN(id) 충돌 회귀에서
복구하는 게 목적.

| service_id | 정답 endpoint | 가격 (USD) |
|---|---|---|
| 3268993 | `/api/v1/services/{service_id}/wash-detail` | $0.005 |
| 7604654 | `/api/v1/wash/check` | $0.05 |
| 7604655 | `/api/v1/categories/{slug}/full-history` | $0.020 |
| 7604656 | `/api/v1/services/{service_id}/transactions` | $0.010 |
| 7604657 | `/api/v1/buyers/{address}/profile` | $0.005 |

대상: 신규 파일 `scripts/reconcile_x402watch_attribution.py` 1 개.
다른 코드 무수정. 서비스 재시작 불필요 (오프라인 reconcile).

전제: P3 fix ([`d0c8611`](https://github.com/printmoneylab/x402watch/commit/d0c8611)
+ [`baef86a`](https://github.com/printmoneylab/x402watch/commit/baef86a))
가 이미 적용되어 stats.jsonl 에 tx_hash 가 채워지고 있어야 함.
2026-05-29 19:56 KST 이후 발생분만 reconcile 대상.

---

## Step 1 — 진단 (apply 전, 읽기 전용 — Moa 실행)

```bash
cd /home/ubuntu/x402watch

# 1a. stats.jsonl payment 중 tx_hash 채워진 비율 (P3 fix 이후 발생분 카운트)
python3 -c "
import json
n_with_tx = n_total = 0
for line in open('var/stats.jsonl'):
    try: d = json.loads(line)
    except: continue
    if d.get('kind') != 'payment': continue
    n_total += 1
    if d.get('tx_hash'): n_with_tx += 1
print(f'total payment: {n_total}, with tx_hash: {n_with_tx}')
"
# expect (예시): total payment: 6, with tx_hash: N
#   N == 0 → P3 fix 이후 결제 없음. reconcile 대상 없음 → cron 만 걸어
#            두고 대기. self-test 만 통과해도 배포 OK.
#   N >= 1 → reconcile 대상 있음. Step 2~5 진행.

# 1b. services 매핑 검증 — 5개 service_id 의 resource_url + price_amount
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT id, resource_url, price_amount
  FROM services
 WHERE id IN (3268993, 7604654, 7604655, 7604656, 7604657)
 ORDER BY id;
"
# expect: 5 행 모두 출력, resource_url 이 스크립트의 ENDPOINT_TO_SERVICE_ID
# 키와 일치하는지 확인. 불일치 시 STOP — 매핑 dict 수정 필요.

# 1c. cron / systemd timer 사용 가능 여부 (Step 6 등록 위해)
ls /etc/systemd/system/ | grep -i x402watch
crontab -l 2>/dev/null | grep -i x402watch || echo "(no crontab for ubuntu)"

# 1d. 현재 5개 service_id 의 db_payments 카운트 (baseline)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT service_id, COUNT(*) AS db_payments,
       ROUND(SUM(amount)::numeric, 4) AS sum_amount
  FROM transactions
 WHERE service_id IN (3268993, 7604654, 7604655, 7604656, 7604657)
   AND time >= '2026-05-01'
 GROUP BY service_id
 ORDER BY service_id;
"
# expect (회귀 상태): 3268993 만 카운트 있고 나머지 4개는 0 또는 매우 작음
# (kr-sentiment 14741 / wash-detail 3268993 등으로 흡수되어 있음).
```

**분기**:
- 1a 의 `with tx_hash` 가 0 → reconcile 대상 없음. 스크립트 + cron 만
  깔고 대기. 신규 결제가 들어오면 자동 정정.
- 1b 의 resource_url 이 매핑 dict 와 다름 → STOP. `ENDPOINT_TO_SERVICE_ID`
  를 실제 DB 값 기준으로 수정 후 재배포.
- 1d 의 baseline 을 메모 — Step 5 검증에서 대비.

## Step 2 — 스크립트 SCP + 권한

```bash
cd /home/ubuntu/x402watch
mkdir -p scripts logs

# 맥북 git repo → Oracle scripts/
cp oracle-patches-x402watch-alerts/reconcile_x402watch_attribution.py \
   scripts/reconcile_x402watch_attribution.py
chmod +x scripts/reconcile_x402watch_attribution.py

# DSN — venv 환경변수가 이미 있으면 그대로 사용. 없으면 .env / .env.local
# 에서 DATABASE_URL 추출:
grep -E "^DATABASE_URL=|^X402WATCH_DSN=" .env .env.local 2>/dev/null
# expect: postgresql://x402watch:...@localhost:5432/x402watch
# 없으면 직접 export:
#   export X402WATCH_DSN="postgresql://x402watch:<pw>@localhost:5432/x402watch"
```

## Step 3 — self-test

실제 DB / stats.jsonl 미접촉. 7개 합성 이벤트로 endpoint matching + amount
verification + reconcile loop + idempotency 전수 검증.

```bash
venv/bin/python scripts/reconcile_x402watch_attribution.py --self-test
```

기대:
```
✓ all self-test cases passed
```

실패하면 STOP — 스크립트 결함이지 환경 문제 아님.

## Step 4 — dry-run (실제 stats.jsonl + DB)

```bash
# P3 fix 시각 이후만 — pre-P3 6건은 tx_hash 없어서 자동으로 skip 되지만
# --since 로 명시하면 출력 카운트가 깔끔.
venv/bin/python scripts/reconcile_x402watch_attribution.py \
    --dsn "${X402WATCH_DSN:-postgresql://x402watch:...@localhost:5432/x402watch}" \
    --since 2026-05-29T19:56:00+09:00
```

기대 출력:
```
== reconcile x402watch attribution — DRY RUN ==
   stats.jsonl: /home/ubuntu/x402watch/var/stats.jsonl
   since: 2026-05-29T19:56:00+09:00

scanned payment events:       <N>
skipped (before --since):     <pre-P3 6건>
skipped (no tx_hash, pre-P3): 0
skipped (unmapped endpoint):  <K>
skipped (amount mismatch):    0
already correct service_id:   <M>
would update                  <L>
not found in transactions:    <P>

   would update breakdown:
     /api/v1/buyers/{address}/profile → service_id 7604657 (J건)
     /api/v1/wash/check → service_id 7604654 (I건)

DRY RUN OK — re-run with --apply to commit.
```

would update 행이 보이면 reconcile 대상 존재. 0 이면 신규 결제 없음
(또는 이미 정답 sid) — cron 만 걸어두고 대기.

## Step 5 — apply

dry-run 결과를 검토해서 `would update breakdown` 이 의도된 endpoint
에만 있는지 확인 후:

```bash
venv/bin/python scripts/reconcile_x402watch_attribution.py \
    --apply \
    --dsn "${X402WATCH_DSN}" \
    --since 2026-05-29T19:56:00+09:00
```

기대 출력 (`updated` 행이 dry-run 의 `would update` 와 같은 수):
```
== reconcile x402watch attribution — APPLY ==
...
updated                       <L>
   updated breakdown:
     /api/v1/buyers/{address}/profile → service_id 7604657 (J건)
     /api/v1/wash/check → service_id 7604654 (I건)
```

각 UPDATE 마다 INFO 로그 1줄 — `reconciled tx=0x... service_id <old> →
<new>`. 로그 파일에 남기려면 `>> logs/reconcile.log 2>&1` 추가.

## Step 6 — 검증

```bash
# 6a. 5개 service_id 의 db_payments 카운트 변화 (Step 1d 대비)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT service_id, COUNT(*) AS db_payments,
       ROUND(SUM(amount)::numeric, 4) AS sum_amount
  FROM transactions
 WHERE service_id IN (3268993, 7604654, 7604655, 7604656, 7604657)
   AND time >= '2026-05-01'
 GROUP BY service_id
 ORDER BY service_id;
"
# expect: 1d 의 baseline 대비 7604654 / 7604655 / 7604656 / 7604657 카운트
# 증가, 3268993 또는 14741 카운트 감소 (흡수가 풀린 만큼).

# 6b. 이번 reconcile 로 마크된 row 확인
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT service_id, COUNT(*)
  FROM transactions
 WHERE attribution_source = 'x402watch_reconcile'
 GROUP BY service_id
 ORDER BY service_id;
"
# expect: dry-run 의 update_by_template 합계와 일치.

# 6c. idempotency — 재실행 시 updated=0
venv/bin/python scripts/reconcile_x402watch_attribution.py --apply \
    --dsn "${X402WATCH_DSN}" \
    --since 2026-05-29T19:56:00+09:00
# expect: updated 0 / already correct service_id <L+M> / not found in transactions <P>
```

## Step 7 — cron 또는 systemd timer 등록 (권장, 선택)

신규 결제가 들어올 때마다 자동 reconcile. 매 1시간이 적절 (인덱서
주기와 비슷).

### Option A — cron

```bash
sudo tee /etc/cron.d/x402watch-reconcile > /dev/null <<'EOF'
# Hourly reconciliation of x402watch attribution from stats.jsonl
0 * * * * ubuntu cd /home/ubuntu/x402watch && \
  X402WATCH_DSN="postgresql://x402watch:<password>@localhost:5432/x402watch" \
  /home/ubuntu/x402watch/venv/bin/python \
    /home/ubuntu/x402watch/scripts/reconcile_x402watch_attribution.py \
    --apply --since 2026-05-29T19:56:00+09:00 \
    >> /home/ubuntu/x402watch/logs/reconcile.log 2>&1
EOF
sudo systemctl restart cron
# 1시간 후 logs/reconcile.log 확인
tail -50 /home/ubuntu/x402watch/logs/reconcile.log
```

### Option B — systemd timer (권장 — DSN을 systemd EnvironmentFile 로 안전 관리)

```bash
sudo tee /etc/systemd/system/x402watch-reconcile.service > /dev/null <<'EOF'
[Unit]
Description=x402watch attribution reconciliation
After=postgresql.service docker.service

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/x402watch
EnvironmentFile=/home/ubuntu/x402watch/.env
ExecStart=/home/ubuntu/x402watch/venv/bin/python \
  /home/ubuntu/x402watch/scripts/reconcile_x402watch_attribution.py \
  --apply --since 2026-05-29T19:56:00+09:00
StandardOutput=append:/home/ubuntu/x402watch/logs/reconcile.log
StandardError=append:/home/ubuntu/x402watch/logs/reconcile.log
EOF

sudo tee /etc/systemd/system/x402watch-reconcile.timer > /dev/null <<'EOF'
[Unit]
Description=Run x402watch reconciliation every hour

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now x402watch-reconcile.timer
systemctl list-timers | grep reconcile
```

## Step 8 — 롤백

이번 fix 가 회귀를 일으킨다면 (시나리오: 매핑 dict 가 틀려서 잘못된
endpoint 가 reconcile 됨):

```bash
# 1. timer / cron 끄기
sudo systemctl disable --now x402watch-reconcile.timer 2>/dev/null
sudo rm -f /etc/cron.d/x402watch-reconcile

# 2. 이번 reconcile 로 마크된 row 복구. 가장 안전한 방법은
#    Step 1d 직전의 pg_dump 백업 복원. 백업 안 했으면 부분 롤백:
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
-- 이번 reconcile 로 변경된 row 의 attribution_source 만 NULL 로
-- 되돌리되 service_id 는 그대로 둠 (EVM 인덱서의 다음 사이클이
-- 다시 잘못 attribution 할 수 있음 — 그래도 데이터 손실은 없음).
UPDATE transactions
   SET attribution_source = NULL
 WHERE attribution_source = 'x402watch_reconcile';
"
# 또는 백업 dump 가 있으면:
#   sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch \
#     < backups/transactions.bak.reconcile-<ts>.sql
```

## 안전장치 요약

- 신규 파일 1 개. 다른 코드 무수정. 서비스 재시작 불필요.
- `UPDATE` 만 — `DELETE` / `INSERT` 없음.
- `BEGIN/COMMIT` 단일 트랜잭션. dry-run 은 ROLLBACK 으로 끝.
- 5개 endpoint allowlist 외 endpoint 는 skip (`skipped_unmapped_endpoint`).
- 가격 5% 이상 오차 시 skip (`skipped_amount_mismatch`) — 잘못된 매핑
  방지.
- `tx_hash` 없는 P3 이전 결제 6건은 reconcile 불가 — `skipped_no_tx_hash`
  로 명시. 백필은 인덱서 분리 작업 필요 (별도 P0).
- 재실행 idempotent — 이미 정답 sid 면 `already_correct` 로 no-op.
- `attribution_source='x402watch_reconcile'` 태그가 reconcile 출처
  표시 + 롤백/감사용.
- PR #36 v2.4 / 알림 fix / merchant_feed chain normalize / payment
  settle 무관.
