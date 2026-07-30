#!/bin/bash
set -euo pipefail
cd /home/ubuntu/x402watch
set -a; source .env; set +a
export X402WATCH_DSN="postgresql://x402watch:$(python3 -c "from urllib.parse import quote_plus; import os; print(quote_plus(os.environ['POSTGRES_PASSWORD']))")@127.0.0.1:5433/x402watch"
exec venv/bin/python scripts/reconcile_x402watch_attribution.py \
    --apply --dsn "$X402WATCH_DSN" --since 2026-05-29T19:56:00+09:00
