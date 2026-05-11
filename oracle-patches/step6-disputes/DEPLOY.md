# Step 6 — Oracle deploy (dispute submission)

Copy-paste sequence. Every block has a verification at the bottom.
All file paths are absolute. Adjust the systemd unit name in §5 if
your FastAPI service is not called `x402watch-api`.

CF Pages frontend is already on `main` (commit `e9e89e9`); the Edge
routes return `503 internal_unavailable` until `X402_INTERNAL_TOKEN`
is set in the Pages dashboard — that is the safety interlock.

---

## 0. Inputs you need before starting

| Variable | Where used | Notes |
|---|---|---|
| `X402_INTERNAL_TOKEN` | Oracle `.env` + CF Pages env | strong random hex, ≥ 48 chars. Same value both sides. |
| DB host/port/user | psql commands | TimescaleDB on docker, default port 5433 |
| FastAPI service name | `systemctl restart …` | placeholder: `x402watch-api` |
| Path to FastAPI entrypoint | §4 router include | `main.py` or `app/api.py` |

Generate the secret if you haven't:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 1. Pull the patches onto Oracle

The patch files live in the x402watch git repo at
`oracle-patches/step6-disputes/`. From the Oracle box:

```bash
cd /home/ubuntu/x402watch
git fetch origin
git checkout main
git pull --ff-only origin main
ls oracle-patches/step6-disputes/
# expect: DEPLOY.md  disputes_api.py  disputes_schema.sql  labeller_queue_patch.py
```

Stage the files in their permanent locations:

```bash
mkdir -p /home/ubuntu/x402watch/migrations
cp oracle-patches/step6-disputes/disputes_schema.sql       migrations/disputes_schema.sql
cp oracle-patches/step6-disputes/labeller_queue_patch.py   migrations/labeller_queue_patch.py
cp oracle-patches/step6-disputes/disputes_api.py           app/disputes_api.py
```

Verify:
```bash
ls -la migrations/disputes_schema.sql migrations/labeller_queue_patch.py app/disputes_api.py
# all three present, ~7-10 KB each
```

---

## 2. Apply the DB migration

```bash
PGPASSWORD="$DB_PASSWORD" psql \
  -h 127.0.0.1 -p 5433 -U x402watch -d x402watch \
  -f /home/ubuntu/x402watch/migrations/disputes_schema.sql
```

Verify:
```bash
PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
  \d label_disputes
"
PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
  SELECT COUNT(*) FROM label_disputes;     -- expect 0
  SELECT COUNT(*) FROM recompute_queue;    -- expect 0
"
```

Rollback (only if needed before §3 lands):
```bash
PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
  DROP TABLE IF EXISTS recompute_queue;
  DROP TABLE IF EXISTS label_disputes;
"
```

---

## 3. Confirm X402_INTERNAL_TOKEN is in the Oracle env

Moa says this is already added. Confirm:
```bash
grep -c "^X402_INTERNAL_TOKEN=" /home/ubuntu/x402watch/.env
# expect: 1
```

If 0, add it:
```bash
echo "X402_INTERNAL_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  >> /home/ubuntu/x402watch/.env
```

(And put the *same* hex into the CF Pages dashboard — see §6.)

---

## 4. Register the FastAPI router

Find the file that constructs the FastAPI app:
```bash
grep -l "FastAPI(" /home/ubuntu/x402watch/main.py \
                   /home/ubuntu/x402watch/app/*.py 2>/dev/null
```

In that file, add this near the other `include_router(...)` calls (or
right after the `app = FastAPI(...)` line if there are none yet):

```python
from app.disputes_api import router as disputes_router
app.include_router(disputes_router)
```

If you prefer an explicit alternate path:
```bash
mkdir -p /home/ubuntu/x402watch/app/routers
mv /home/ubuntu/x402watch/app/disputes_api.py \
   /home/ubuntu/x402watch/app/routers/disputes.py
# then:  from app.routers.disputes import router as disputes_router
```

Verify the import works without starting the server:
```bash
cd /home/ubuntu/x402watch
venv/bin/python -c "from app.disputes_api import router; print('ROUTER_OK routes=', len(router.routes))"
# expect: ROUTER_OK routes= 3
```

---

## 5. Restart the FastAPI service

```bash
sudo systemctl restart x402watch-api
sudo systemctl status x402watch-api --no-pager | head -20
sudo journalctl -u x402watch-api -n 50 --no-pager
```

Watch the journalctl for an `Application startup complete` line and no
`ImportError` from disputes_api.

Smoke-test from the Oracle box (skips CF Pages so any failure points
straight at the local server):

```bash
TOKEN=$(grep ^X402_INTERNAL_TOKEN= /home/ubuntu/x402watch/.env | cut -d= -f2-)

curl -sS -X POST http://127.0.0.1:8000/api/v1/internal/disputes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_address": "0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0",
    "current_label": "ai_agent",
    "current_confidence": 0.75,
    "reason": "Smoke test from Step 6 deploy — please ignore or reject."
  }' | python3 -m json.tool
```

Expected: `{"ok": true, "dispute_id": 1, "status": "pending", "pending_for_buyer": 1, "message": "..."}`.

Confirm the row landed:
```bash
PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
  SELECT id, buyer_address, current_label, status, created_at FROM label_disputes;
"
```

Confirm the admin list endpoint:
```bash
curl -sS "http://127.0.0.1:8000/api/v1/internal/disputes/list?status=pending" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Confirm the public count endpoint:
```bash
curl -sS "http://127.0.0.1:8000/api/v1/disputes/buyer/0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0" \
  | python3 -m json.tool
# expect: { ..., "total_disputes": 1, "pending": 1, ... }
```

Tear down the smoke test row (optional but tidy):
```bash
PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
  DELETE FROM label_disputes WHERE reason LIKE 'Smoke test from Step 6 deploy%';
"
```

---

## 6. Cloudflare Pages env vars

In the Cloudflare dashboard → Workers & Pages → x402watch → Settings →
Environment variables:

| Scope | Name | Value |
|---|---|---|
| Production | `X402_INTERNAL_TOKEN` | same hex as Oracle `.env` |
| Production | `X402_INTERNAL_API` *(optional)* | `https://api.x402.printmoneylab.com/api/v1` — only set if you proxy through a different host |

Re-deploy the Pages project (no code change — env-only redeploy).

End-to-end smoke test, through the public proxy:

```bash
curl -sS -X POST https://x402.printmoneylab.com/api/disputes \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_address": "0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0",
    "current_label": "ai_agent",
    "current_confidence": 0.75,
    "reason": "End-to-end smoke test through CF Pages proxy — please ignore."
  }' | python3 -m json.tool
```

Expected: `{"ok": true, "dispute_id": N, ...}`. A Telegram alert
should land in the configured chat within ~5 s.

---

## 7. Apply the labeller queue-drain patch

```bash
cd /home/ubuntu/x402watch
cp indexer/labeller.py indexer/labeller.py.bak.pre_step6
venv/bin/python migrations/labeller_queue_patch.py
```

Expected: `PATCH_OK lines=NNN`. Re-running prints `PATCH_ALREADY_APPLIED`.

Verify the import + syntax:
```bash
venv/bin/python -c "from indexer import labeller; print('labeller importable, has queue helper:', hasattr(labeller, 'process_recompute_queue'))"
# expect: labeller importable, has queue helper: True
```

The labeller runs on its existing systemd timer (daily 09:00 KST).
Nothing to restart — the patched module will load on the next firing.

Dry-run option (to exercise the new code path immediately):
```bash
venv/bin/python -m indexer.labeller 2>&1 | tail -30
# look for "recompute queue: ..." in the output
```

---

## 8. UI smoke test on the public site

1. Open `https://x402.printmoneylab.com/services/14239` (Aubrai — the
   confirmed wash farm with 10× `suspected_wash` buyers).
2. Click the flag icon next to a row.
3. Fill the reason (≥ 32 chars) and submit.
4. Confirm the dialog flips to the success state showing a `#N`
   dispute id.
5. Confirm the Telegram alert lands and a row appears via:
   ```bash
   PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
     SELECT id, buyer_address, status, created_at FROM label_disputes
     ORDER BY id DESC LIMIT 5;
   "
   ```

---

## 9. Rollback (full)

```bash
# (a) labeller
cd /home/ubuntu/x402watch
cp indexer/labeller.py.bak.pre_step6 indexer/labeller.py

# (b) FastAPI router — remove the include_router lines added in §4,
#     then restart:
sudo systemctl restart x402watch-api

# (c) tables (destructive — only if you really want disputes gone)
PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch -c "
  DROP TABLE IF EXISTS recompute_queue;
  DROP TABLE IF EXISTS label_disputes;
"

# (d) frontend interlock — unset X402_INTERNAL_TOKEN in CF Pages env;
#     the Edge route will return 503 internal_unavailable and the UI
#     dialog surfaces a clean error message.
```

Rollback completes in <2 minutes. The original v2.0 pipeline keeps
running normally with disputes turned off.
