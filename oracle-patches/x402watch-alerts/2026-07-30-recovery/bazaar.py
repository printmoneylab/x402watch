"""
Coinbase Bazaar Discovery Indexer.

Walks GET /v2/x402/discovery/resources, upserts services into DB,
sends Telegram alerts for newly discovered services.

Run: python -m indexer.bazaar
"""
import asyncio
import json
import logging
import sys
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.db import get_pool, close_pool
from app.telegram import send as tg_send

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bazaar.log"),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger("indexer.bazaar")

API_URL = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
PAGE_SIZE = 1000
HTTP_TIMEOUT = 30

# ─── Network mapping (CAIP-2 → readable) ────────────────────────────────
NETWORK_MAP = {
    # EVM
    "eip155:1": "ethereum",
    "eip155:10": "optimism",
    "eip155:137": "polygon",
    "eip155:480": "world",
    "eip155:8453": "base",
    "eip155:42161": "arbitrum",
    "eip155:84532": "base-sepolia",
    # Solana
    "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc": "solana",
    "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp": "solana",
    "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1": "solana-devnet",
}


def normalize_network(caip: str | None) -> str:
    if not caip:
        return "unknown"
    # Exact match
    if caip in NETWORK_MAP:
        return NETWORK_MAP[caip]
    # Prefix match for Solana variants (mainnet identifier sometimes truncated)
    if caip.startswith("solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"):
        return "solana"
    return caip

# ─── HTTP client ────────────────────────────────────────────────────────
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)
async def fetch_page(client: httpx.AsyncClient, offset: int, limit: int) -> dict[str, Any]:
    r = await client.get(API_URL, params={"offset": offset, "limit": limit})
    r.raise_for_status()
    return r.json()


# ─── Item parsing ──────────────────────────────────────────────────────
def parse_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Map Bazaar item to services-table row. Return None if invalid."""
    accepts = item.get("accepts") or []
    if not accepts:
        return None

    # Prefer the first accept entry (most services have one)
    accept = accepts[0]
    network = normalize_network(accept.get("network"))
    pay_to = accept.get("payTo")
    if not pay_to:
        return None

    # Price: amount is in atomic units, totalUsd in extra is float
    extra = accept.get("extra") or {}
    price_amount = None
    if "totalUsd" in extra:
        price_amount = float(extra["totalUsd"])
    elif accept.get("amount"):
        # Fallback: divide by 10^6 (USDC default)
        try:
            price_amount = float(accept["amount"]) / 1_000_000
        except (TypeError, ValueError):
            price_amount = None

    return {
        "facilitator": "coinbase-cdp",
        "chain": network,
        "seller_address": pay_to.lower(),
        "resource_url": item.get("resource"),
        "name": (item.get("description") or "")[:200],
        "description": item.get("description"),
        "price_amount": price_amount,
        "price_token": extra.get("name", "USDC"),
        "metadata": json.dumps({
            "type": item.get("type"),
            "x402_version": item.get("x402Version"),
            "quality": item.get("quality"),
            "last_updated_remote": item.get("lastUpdated"),
            "extensions": item.get("extensions"),
            "accepts_full": accepts,
        }),
    }


# ─── DB upsert ─────────────────────────────────────────────────────────
UPSERT_SQL = """
INSERT INTO services (
    facilitator, chain, seller_address, resource_url,
    name, description, price_amount, price_token,
    first_seen, last_seen, is_active, metadata
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW(), true, $9::jsonb)
ON CONFLICT (chain, seller_address, resource_url) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price_amount = EXCLUDED.price_amount,
    price_token = EXCLUDED.price_token,
    last_seen = NOW(),
    is_active = true,
    metadata = EXCLUDED.metadata
RETURNING (xmax = 0) AS inserted, id, name, chain, price_amount;
"""


async def upsert_service(conn, row: dict[str, Any]) -> dict[str, Any] | None:
# Strip NUL bytes — PostgreSQL UTF8 rejects 0x00
    row = {k: (v.replace('\x00', '') if isinstance(v, str) else v) for k, v in row.items()}
    res = await conn.fetchrow(
        UPSERT_SQL,
        row["facilitator"], row["chain"], row["seller_address"], row["resource_url"],
        row["name"], row["description"], row["price_amount"], row["price_token"],
        row["metadata"],
    )
    return dict(res) if res else None


# ─── Main crawler ──────────────────────────────────────────────────────
async def run() -> dict[str, int]:
    stats = {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    new_alerts: list[dict[str, Any]] = []

    pool = await get_pool()

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        offset = 0
        while True:
            try:
                page = await fetch_page(client, offset, PAGE_SIZE)
            except Exception as e:
                log.exception("Page fetch failed at offset=%s: %s", offset, e)
                stats["errors"] += 1
                break

            items = page.get("items") or []
            if not items:
                break

            pagination = page.get("pagination") or {}
            total = pagination.get("total")
            log.info(
                "Page offset=%s limit=%s items=%s total=%s",
                offset, PAGE_SIZE, len(items), total,
            )

            async with pool.acquire() as conn:
                for item in items:
                    row = parse_item(item)
                    if row is None:
                        stats["skipped"] += 1
                        continue
                    try:
                        result = await upsert_service(conn, row)
                        stats["fetched"] += 1
                        if result and result["inserted"]:
                            stats["inserted"] += 1
                            new_alerts.append(result)
                        else:
                            stats["updated"] += 1
                    except Exception as e:
                        log.exception("Upsert failed: %s", e)
                        stats["errors"] += 1

            offset += PAGE_SIZE
            if total is not None and offset >= total:
                break


    log.info("Run complete: %s", stats)
    return stats


async def main() -> None:
    try:
        stats = await run()
        if stats["errors"] > 0:
            await tg_send(
                f"⚠️ Bazaar indexer errors: {stats['errors']}\n"
                f"Fetched: {stats['fetched']} · New: {stats['inserted']} · "
                f"Updated: {stats['updated']} · Skipped: {stats['skipped']}"
            )
    finally:
        await close_pool()

if __name__ == "__main__":
    asyncio.run(main())
