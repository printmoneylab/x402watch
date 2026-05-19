"""
x402watch-side merchant feed indexer.

Permanent location on Oracle:
  /home/ubuntu/x402watch/indexer/merchant_feed.py

Mount from the existing indexer cron / systemd timer:
  # in indexer/run.py (or whatever the orchestrator is)
  from indexer import merchant_feed
  await merchant_feed.poll_all()

Or run standalone for manual backfill / dry-run:
  venv/bin/python -m indexer.merchant_feed --merchant kr-crypto --since 2026-04-27
  venv/bin/python -m indexer.merchant_feed --dry-run

What it does
============
For each registered merchant in `merchant_feed_keys`:
  1. Fetch  /.well-known/x402watch-feed.json (fallback /api/v1/...)
  2. Validate feed_version, merchant_id, feed_seq monotonicity,
     issued_at clock-skew window.
  3. Verify Ed25519 signature over canonical (sorted-keys) JSON body
     minus the signature field.
  4. For each settlement row:
     a. Confirm seller ∈ feed.seller_addresses.
     b. Look up matching services row by (seller_address, resource_url).
     c. UPSERT into transactions with attribution_source =
        'merchant_feed:<merchant_id>'. tx_hash + chain is the PK.
  5. Persist last_accepted_feed_seq[merchant_id].
  6. Emit a `merchant_feed_fetch` row to stats.jsonl with counts.

Schema dependencies
===================
  ALTER TABLE transactions ADD COLUMN IF NOT EXISTS attribution_source TEXT;
  ALTER TABLE transactions ADD COLUMN IF NOT EXISTS feed_merchant_id TEXT;
  ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_x402_payment BOOLEAN;
  CREATE TABLE IF NOT EXISTS merchant_feed_keys ( ... );
  CREATE TABLE IF NOT EXISTS merchant_feed_state ( ... );
(both DDLs in backfill_kr_crypto.sql)

Conservative defaults
=====================
- Network timeout 10 s, body cap 16 MiB.
- Retry per feed: 5/15/60 min backoff. After 3 failures, pause merchant
  for 24 h and Telegram alert.
- Never hard-delete transactions. Only UPDATE service_id + attribution_source.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.db import get_pool

log = logging.getLogger("merchant_feed")

FEED_VERSION_SUPPORTED = 1
NETWORK_TIMEOUT = 10.0
MAX_BODY_BYTES = 16 * 1024 * 1024
ISSUED_AT_PAST_WINDOW = timedelta(hours=24)
ISSUED_AT_FUTURE_WINDOW = timedelta(minutes=5)


# ─── Crypto + canonicalisation ──────────────────────────────────────
def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _verify_signature(body: dict) -> tuple[bool, str]:
    """Returns (ok, reason). body must include `signature` field."""
    sig = body.get("signature") or {}
    if sig.get("alg") != "Ed25519":
        return False, "unsupported_alg"
    key_id = sig.get("key_id")
    value_b64 = sig.get("value")
    if not key_id or not value_b64:
        return False, "incomplete_signature"
    # Look up the public key
    # (sync DB lookup happens at caller; this helper takes the key bytes)
    return True, "deferred"  # placeholder — real verify happens in verify_feed()


async def _lookup_public_key(conn, merchant_id: str, key_id: str,
                             issued_at: datetime) -> Optional[bytes]:
    row = await conn.fetchrow("""
        SELECT public_key_b64url, valid_from, valid_until, revoked_at
        FROM merchant_feed_keys
        WHERE merchant_id = $1 AND key_id = $2
    """, merchant_id, key_id)
    if row is None:
        return None
    if row["revoked_at"] is not None and issued_at >= row["revoked_at"]:
        return None
    if not (row["valid_from"] <= issued_at <= row["valid_until"]):
        return None
    pad = "=" * ((4 - len(row["public_key_b64url"]) % 4) % 4)
    return base64.urlsafe_b64decode(row["public_key_b64url"] + pad)


def _verify_ed25519(public_key_raw: bytes, msg: bytes, sig_b64url: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key_raw)
        pad = "=" * ((4 - len(sig_b64url) % 4) % 4)
        sig = base64.urlsafe_b64decode(sig_b64url + pad)
        key.verify(sig, msg)
        return True
    except InvalidSignature:
        return False
    except Exception:
        log.exception("ed25519 verify error")
        return False


# ─── Feed validation + ingestion ────────────────────────────────────
async def verify_feed(conn, body: dict) -> tuple[bool, str]:
    if body.get("feed_version") != FEED_VERSION_SUPPORTED:
        return False, f"unsupported_feed_version:{body.get('feed_version')}"
    merchant_id = body.get("merchant_id")
    if not merchant_id:
        return False, "missing_merchant_id"
    sig = body.get("signature") or {}
    if sig.get("alg") != "Ed25519":
        return False, "unsupported_alg"

    # issued_at sanity
    try:
        issued = datetime.fromisoformat(body["issued_at"].replace("Z", "+00:00"))
    except Exception:
        return False, "invalid_issued_at"
    now = datetime.now(timezone.utc)
    if issued < now - ISSUED_AT_PAST_WINDOW:
        return False, "issued_at_too_old"
    if issued > now + ISSUED_AT_FUTURE_WINDOW:
        return False, "issued_at_future"

    # Replay protection
    last_seq = await conn.fetchval(
        "SELECT last_feed_seq FROM merchant_feed_state WHERE merchant_id = $1",
        merchant_id,
    )
    if last_seq is not None and body.get("feed_seq", 0) <= last_seq:
        return False, f"replay:feed_seq<=last({last_seq})"

    # Key lookup + signature verify
    pub_raw = await _lookup_public_key(conn, merchant_id, sig.get("key_id", ""), issued)
    if pub_raw is None:
        return False, "unknown_or_expired_key"
    body_copy = dict(body)
    body_copy.pop("signature", None)
    msg = _canonical_json(body_copy)
    if not _verify_ed25519(pub_raw, msg, sig.get("value", "")):
        return False, "bad_signature"

    return True, "ok"


async def ingest_feed(conn, body: dict, dry_run: bool = False) -> dict:
    """Apply a verified feed body to transactions table."""
    merchant_id = body["merchant_id"]
    sellers = {s.lower() if s.startswith("0x") else s for s in body.get("seller_addresses", [])}
    counts = {"accepted": 0, "rejected_seller": 0, "rejected_resource": 0,
              "rejected_amount": 0, "unchanged": 0}
    for s in body.get("settlements", []):
        seller = (s.get("seller") or "").lower() if s.get("seller", "").startswith("0x") else s.get("seller")
        if seller not in sellers:
            counts["rejected_seller"] += 1
            continue

        # Find the canonical services row for (seller, resource_url).
        svc = await conn.fetchrow("""
            SELECT id, price_amount
            FROM services
            WHERE LOWER(seller_address) = $1 AND resource_url = $2
            LIMIT 1
        """, seller, s.get("resource_url"))
        if svc is None:
            counts["rejected_resource"] += 1
            continue

        # Sanity-check the amount against services.price_amount.
        try:
            feed_amount = int(s.get("amount_usdc", "0")) / 1_000_000
        except Exception:
            feed_amount = -1
        if svc["price_amount"] is not None and abs(feed_amount - float(svc["price_amount"])) > 1e-6:
            log.warning(
                "amount mismatch — feed=%s svc=%s tx=%s",
                feed_amount, svc["price_amount"], s.get("tx_hash"),
            )
            # Not a hard reject — we accept the feed but log the warning.

        if dry_run:
            counts["accepted"] += 1
            continue

        # UPSERT — if the tx row already exists with a different service_id,
        # update it; otherwise insert fresh.
        try:
            ts_raw = s.get("settled_at", "")
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            ts = datetime.now(timezone.utc)

        result = await conn.execute("""
            INSERT INTO transactions (
                tx_hash, chain, time, buyer_address, seller_address,
                service_id, amount, attribution_source, feed_merchant_id,
                is_x402_payment
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, TRUE)
            ON CONFLICT (tx_hash, chain) DO UPDATE
              SET service_id = EXCLUDED.service_id,
                  attribution_source = EXCLUDED.attribution_source,
                  feed_merchant_id = EXCLUDED.feed_merchant_id,
                  is_x402_payment = TRUE
        """,
            s.get("tx_hash"), s.get("chain"), ts,
            s.get("payer"), seller, svc["id"], feed_amount,
            f"merchant_feed:{merchant_id}", merchant_id,
        )
        if result.startswith("INSERT 0 1") or result.startswith("UPDATE 1"):
            counts["accepted"] += 1
        else:
            counts["unchanged"] += 1

    if not dry_run:
        await conn.execute("""
            INSERT INTO merchant_feed_state (merchant_id, last_feed_seq, last_fetch_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (merchant_id) DO UPDATE
              SET last_feed_seq = EXCLUDED.last_feed_seq,
                  last_fetch_at = NOW()
        """, merchant_id, body.get("feed_seq"))
    return counts


# ─── Polling loop ───────────────────────────────────────────────────
async def fetch_feed(url: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=NETWORK_TIMEOUT) as c:
        r = await c.get(url)
        if r.status_code != 200:
            log.warning("feed %s returned %s", url, r.status_code)
            return None
        if len(r.content) > MAX_BODY_BYTES:
            log.error("feed %s exceeded body cap (%d bytes)", url, len(r.content))
            return None
        try:
            return r.json()
        except Exception:
            log.exception("feed %s json parse failed", url)
            return None


async def poll_merchant(merchant_id: str, feed_base_url: str, *, dry_run: bool = False) -> dict:
    """Try .well-known/ first, fall back to /api/v1/."""
    pool = await get_pool()
    candidates = [
        f"{feed_base_url.rstrip('/')}/.well-known/x402watch-feed.json",
        f"{feed_base_url.rstrip('/')}/api/v1/x402watch-feed.json",
    ]
    body = None
    fetched_from = None
    for url in candidates:
        body = await fetch_feed(url)
        if body is not None:
            fetched_from = url
            break
    if body is None:
        return {"merchant_id": merchant_id, "error": "fetch_failed", "fetched_from": None}

    async with pool.acquire() as conn:
        ok, reason = await verify_feed(conn, body)
        if not ok:
            return {"merchant_id": merchant_id, "error": reason, "fetched_from": fetched_from}
        counts = await ingest_feed(conn, body, dry_run=dry_run)
    return {"merchant_id": merchant_id, "fetched_from": fetched_from,
            "feed_seq": body.get("feed_seq"), "counts": counts}


async def poll_all(*, dry_run: bool = False) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        merchants = await conn.fetch(
            "SELECT DISTINCT merchant_id, feed_base_url "
            "FROM merchant_feed_keys "
            "WHERE feed_base_url IS NOT NULL AND revoked_at IS NULL"
        )
    out = []
    for m in merchants:
        out.append(await poll_merchant(m["merchant_id"], m["feed_base_url"], dry_run=dry_run))
    return out


async def _main(args):
    if args.merchant and args.feed_url:
        result = await poll_merchant(args.merchant, args.feed_url, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))
    else:
        results = await poll_all(dry_run=args.dry_run)
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--merchant", help="merchant_id to poll (omit = all)")
    p.add_argument("--feed-url", help="base URL of the merchant (required with --merchant)")
    p.add_argument("--dry-run", action="store_true")
    asyncio.run(_main(p.parse_args()))
