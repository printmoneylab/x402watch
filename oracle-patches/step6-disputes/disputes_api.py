"""
Step 6 — dispute submission router for the Oracle FastAPI app.

Permanent location: /home/ubuntu/x402watch/app/disputes_api.py

Mount from whichever file owns the FastAPI() instance (main.py or
app/api.py):

    from app.disputes_api import router as disputes_router
    app.include_router(disputes_router)

Endpoints:

    POST /api/v1/internal/disputes
        Authorization: Bearer $X402_INTERNAL_TOKEN
        Header:        X-Forwarded-IP  (set by the CF Pages Edge proxy)
        Body:          { buyer_address, seller_address?, reporter_address?,
                         reason, current_label, current_confidence? }
        Behaviour:     insert dispute → count pending for this buyer →
                       bump recompute_queue at ≥ RECOMPUTE_THRESHOLD →
                       fire-and-forget Telegram alert.

    GET  /api/v1/internal/disputes/list
        Authorization: Bearer $X402_INTERNAL_TOKEN
        Query:         status=pending&limit=20&offset=0

    GET  /api/v1/disputes/buyer/{address}
        Public, count-only. No bodies leak.

Environment:
    X402_INTERNAL_TOKEN  — shared secret with the CF Pages /api/disputes proxy.
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

# Reuse the shared asyncpg pool. The path matches the rest of the
# Oracle codebase (`from app.db import get_pool`).
from app.db import get_pool

log = logging.getLogger("disputes")

RECOMPUTE_THRESHOLD = 5
REASON_MIN, REASON_MAX = 32, 1000

ALLOWED_LABELS = {
    "organic_user", "self_test", "developer", "suspected_wash",
    "ai_agent", "analytics_bot", "exchange_user", "verifier",
    "owner_test", "unlabeled",
}

BASE58_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

router = APIRouter()


# ─── auth ────────────────────────────────────────────────────────────
def require_internal_token(authorization: str = Header(...)) -> None:
    expected = os.environ.get("X402_INTERNAL_TOKEN", "")
    if not expected:
        raise HTTPException(503, "internal token not configured")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "unauthorized")
    token = authorization[len("Bearer "):]
    if not hmac.compare_digest(token, expected):
        raise HTTPException(401, "unauthorized")


# ─── input schema ────────────────────────────────────────────────────
def _validate_wallet(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    v = v.strip()
    if v.startswith("0x") and len(v) == 42:
        int(v[2:], 16)  # raises if not hex
        return v.lower()
    if 32 <= len(v) <= 44 and all(c in BASE58_ALPHABET for c in v):
        return v
    raise ValueError("invalid_address")


class DisputeIn(BaseModel):
    buyer_address: str = Field(min_length=32, max_length=64)
    seller_address: Optional[str] = Field(default=None, max_length=64)
    reporter_address: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)
    current_label: str
    current_confidence: Optional[float] = None

    @field_validator("current_label")
    @classmethod
    def label_in_taxonomy(cls, v: str) -> str:
        if v not in ALLOWED_LABELS:
            raise ValueError("invalid_label")
        return v

    @field_validator("buyer_address", "seller_address", "reporter_address")
    @classmethod
    def wallet_format(cls, v: Optional[str]) -> Optional[str]:
        return _validate_wallet(v)


# ─── telegram ────────────────────────────────────────────────────────
async def _notify_telegram(dispute_id: int, payload: DisputeIn, pending_for_buyer: int) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    conf_str = (
        f" ({payload.current_confidence:.2f})"
        if payload.current_confidence is not None
        else ""
    )
    reason_excerpt = payload.reason[:200] + ("…" if len(payload.reason) > 200 else "")
    text = (
        f"🚩 New label dispute\n"
        f"Buyer: {payload.buyer_address}\n"
        f"Seller: {payload.seller_address or '(global)'}\n"
        f"Current label: {payload.current_label}{conf_str}\n"
        f"Pending for this buyer: {pending_for_buyer}\n"
        f"Auto-recompute threshold: {RECOMPUTE_THRESHOLD}\n"
        f"Reason: {reason_excerpt}\n"
        f"Dispute ID: #{dispute_id}"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text},
            )
    except Exception:
        log.exception("telegram notify failed")


# ─── POST /internal/disputes ─────────────────────────────────────────
@router.post(
    "/api/v1/internal/disputes",
    dependencies=[Depends(require_internal_token)],
)
async def create_dispute(
    payload: DisputeIn,
    request: Request,
    x_forwarded_ip: Optional[str] = Header(default=None),
) -> dict:
    ip_source = x_forwarded_ip or (request.client.host if request.client else "")
    ip = (ip_source or "")[:64]
    pool = await get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            try:
                row = await c.fetchrow(
                    """
                    INSERT INTO label_disputes (
                        buyer_address, seller_address, reporter_address,
                        reporter_ip, reason, current_label, current_confidence
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7)
                    RETURNING id
                    """,
                    payload.buyer_address, payload.seller_address,
                    payload.reporter_address, ip,
                    payload.reason, payload.current_label,
                    payload.current_confidence,
                )
            except Exception as e:
                if "label_disputes_dedupe_idx" in str(e):
                    raise HTTPException(429, "duplicate")
                raise
            dispute_id = row["id"]

            pending = await c.fetchval(
                """
                SELECT COUNT(*) FROM label_disputes
                WHERE buyer_address = $1 AND status = 'pending'
                """,
                payload.buyer_address,
            )

            if pending >= RECOMPUTE_THRESHOLD:
                await c.execute(
                    """
                    INSERT INTO recompute_queue (buyer_address, triggered_by, pending_count)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (buyer_address) DO UPDATE
                      SET pending_count = EXCLUDED.pending_count,
                          processed_at = NULL,
                          triggered_by = COALESCE(recompute_queue.triggered_by, EXCLUDED.triggered_by)
                    """,
                    payload.buyer_address, dispute_id, pending,
                )

    # Fire-and-forget telegram alert. Never block the response.
    try:
        asyncio.create_task(_notify_telegram(dispute_id, payload, pending))
    except RuntimeError:
        pass  # outside an event loop — skip silently

    if pending >= RECOMPUTE_THRESHOLD:
        msg = "Dispute received. Auto-recompute triggered."
    else:
        remaining = RECOMPUTE_THRESHOLD - pending
        msg = f"Dispute received. Auto-recompute at {remaining} more independent reports."

    return {
        "ok": True,
        "dispute_id": dispute_id,
        "status": "pending",
        "pending_for_buyer": pending,
        "message": msg,
    }


# ─── GET /internal/disputes/list ─────────────────────────────────────
@router.get(
    "/api/v1/internal/disputes/list",
    dependencies=[Depends(require_internal_token)],
)
async def list_disputes(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as c:
        total = await c.fetchval("SELECT COUNT(*) FROM label_disputes")
        pending = await c.fetchval(
            "SELECT COUNT(*) FROM label_disputes WHERE status='pending'"
        )
        rows = await c.fetch(
            """
            SELECT id, buyer_address, seller_address, reporter_address,
                   current_label, current_confidence, status, reason,
                   created_at, resolved_at, resolution_note
            FROM label_disputes
            WHERE ($1::text IS NULL OR status = $1)
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            status, limit, offset,
        )
        by_buyer_rows = await c.fetch(
            """
            SELECT buyer_address, COUNT(*) AS n
            FROM label_disputes
            WHERE status = 'pending'
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 50
            """
        )
    return {
        "total": int(total or 0),
        "pending": int(pending or 0),
        "by_buyer": {r["buyer_address"]: int(r["n"]) for r in by_buyer_rows},
        "recent": [dict(r) for r in rows],
    }


# ─── GET /disputes/buyer/{address} (public) ──────────────────────────
@router.get("/api/v1/disputes/buyer/{address}")
async def public_buyer_counts(address: str) -> dict:
    try:
        cleaned = _validate_wallet(address)
    except ValueError:
        raise HTTPException(400, "invalid_address")
    if cleaned is None:
        raise HTTPException(400, "invalid_address")

    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT status, COUNT(*) AS n
            FROM label_disputes
            WHERE buyer_address = $1
            GROUP BY status
            """,
            cleaned,
        )
    counts = {r["status"]: int(r["n"]) for r in rows}
    return {
        "buyer_address": cleaned,
        "total_disputes": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "reviewed": counts.get("reviewed", 0),
        "resolved": counts.get("resolved", 0),
        "rejected": counts.get("rejected", 0),
    }
