"""
x402watch landing-stats API.

Single endpoint:
  GET /api/v1/landing-stats
returning the rich payload consumed by the Next.js Server Component
(stats + label_distribution + category_volume_series + daily_new_services).

Redis caches the full payload under the key `x402watch:landing_stats:v1`
with a 60-second TTL. First request populates the cache; subsequent
requests within the TTL serve from Redis.

Run: uvicorn app.api:app --host 127.0.0.1 --port 8090
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis_lib

from app.db import close_pool, get_pool

load_dotenv()
log = logging.getLogger("x402watch.api")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


CACHE_KEY = "x402watch:landing_stats:v1"
CACHE_TTL_SECONDS = 60
TOP_CATEGORIES_FOR_SERIES = 5
SERIES_LOOKBACK_DAYS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Redis container is on 127.0.0.1:6380 with REDIS_PASSWORD auth.
    # Using kwargs (not from_url) to avoid URL-encoding issues with special chars in the password.
    app.state.redis = redis_lib.Redis(
        host="127.0.0.1",
        port=6380,
        password=os.environ["REDIS_PASSWORD"],
        decode_responses=True,
    )
    log.info("redis client ready")
    try:
        yield
    finally:
        await app.state.redis.close()
        await close_pool()


app = FastAPI(
    title="x402watch API",
    version="1.0",
    description="Public read-only landing-page stats. CC0 data.",
    lifespan=lifespan,
)

# CORS — open by default for the public landing page; tighten to printmoneylab
# domains if abused.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://x402.printmoneylab.com",
        "https://printmoneylab.com",
        "http://localhost:3000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# Step 6: dispute system
from app.disputes_api import router as disputes_router
app.include_router(disputes_router)

# PR #36 reviewer feedback — paid-endpoint OpenAPI + accepts.resource
# parity + POST preflight. See oracle-patches/pr36-openapi/.


# ─── Query helpers ────────────────────────────────────────────────────
async def query_basic_stats(conn) -> dict[str, Any]:
    n_services = await conn.fetchval(
        "SELECT COUNT(*) FROM services WHERE is_active = TRUE"
    )
    n_tx = await conn.fetchval("SELECT COUNT(*) FROM transactions")
    n_buyers = await conn.fetchval(
        "SELECT COUNT(DISTINCT buyer_address) FROM transactions "
        "WHERE time >= NOW() - INTERVAL '30 days'"
    )
    real_pct = await conn.fetchval("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT COALESCE(SUM(CASE WHEN l.label IN ('organic_user','ai_agent','exchange_user')
                                 THEN t.amount ELSE 0 END), 0)
               / NULLIF(SUM(t.amount), 0) * 100
        FROM transactions t
        LEFT JOIN latest l ON l.buyer_address = t.buyer_address
        WHERE t.time >= NOW() - INTERVAL '30 days'
    """)
    return {
        "services_indexed": int(n_services or 0),
        "transactions_analyzed": int(n_tx or 0),
        "active_buyers": int(n_buyers or 0),
        "real_volume_pct": round(float(real_pct or 0), 1),
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
    }


async def query_label_distribution(conn) -> list[dict]:
    rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT label, COUNT(*) AS n FROM latest GROUP BY 1 ORDER BY 2 DESC
    """)
    total = sum(r["n"] for r in rows) or 1
    return [
        {"label": r["label"], "n_buyers": r["n"], "share_pct": round(100 * r["n"] / total, 2)}
        for r in rows
    ]


async def query_category_volume_series(conn) -> list[dict]:
    """Top N categories by 24h volume, with daily series over the lookback window."""
    top_rows = await conn.fetch("""
        SELECT category, SUM(total_volume_24h)::float AS vol
        FROM category_stats
        WHERE chain = 'all'
          AND time >= NOW() - INTERVAL '1 day' * $1
          AND category NOT IN ('other','premium_placeholder','test_dummy')
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT $2
    """, SERIES_LOOKBACK_DAYS, TOP_CATEGORIES_FOR_SERIES)
    top = [r["category"] for r in top_rows]
    if not top:
        return []
    rows = await conn.fetch("""
        SELECT category,
               date_trunc('day', time) AS day,
               MAX(total_volume_24h)::float AS vol_24h,
               MAX(total_tx_24h)::int AS tx_24h
        FROM category_stats
        WHERE chain = 'all'
          AND category = ANY($1::text[])
          AND time >= NOW() - INTERVAL '1 day' * $2
        GROUP BY 1, 2
        ORDER BY 1, 2
    """, top, SERIES_LOOKBACK_DAYS)
    by_cat: dict[str, list[dict]] = {c: [] for c in top}
    for r in rows:
        by_cat.setdefault(r["category"], []).append({
            "date": r["day"].date().isoformat(),
            "total_volume_24h": float(r["vol_24h"] or 0),
            "total_tx_24h": int(r["tx_24h"] or 0),
        })
    return [{"category": c, "points": by_cat[c]} for c in top]


async def query_daily_new_services(conn) -> list[dict]:
    rows = await conn.fetch("""
        SELECT date_trunc('day', first_seen) AS day, COUNT(*)::int AS n
        FROM services
        WHERE first_seen >= NOW() - INTERVAL '30 days'
        GROUP BY 1 ORDER BY 1
    """)
    return [{"date": r["day"].date().isoformat(), "count": int(r["n"] or 0)} for r in rows]


async def build_payload() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await query_basic_stats(conn)
        labels = await query_label_distribution(conn)
        series = await query_category_volume_series(conn)
        daily = await query_daily_new_services(conn)
    return {
        "stats": stats,
        "label_distribution": labels,
        "category_volume_series": series,
        "daily_new_services": daily,
    }


@app.get("/api/v1/landing-stats")
async def landing_stats():
    r = app.state.redis
    cached = await r.get(CACHE_KEY)
    if cached:
        import json
        return json.loads(cached)
    payload = await build_payload()
    import json as _json
    await r.set(CACHE_KEY, _json.dumps(payload), ex=CACHE_TTL_SECONDS)
    return payload


CATEGORIES_LIST_KEY = "x402watch:categories:list:v1"
CATEGORY_DETAIL_KEY_FMT = "x402watch:categories:detail:{slug}:v1"
CATEGORIES_TTL_SECONDS = 300

# Real-volume label set (kept in sync with methodology §2)
REAL_LABELS = ("organic_user", "ai_agent", "exchange_user")
WASH_LABELS = ("self_test", "suspected_wash")


# ─── Categories list ───────────────────────────────────────────────────
async def query_categories_list(conn) -> list[dict]:
    """Service counts + price stats per category."""
    rows = await conn.fetch("""
        SELECT
            category,
            COUNT(*)::int AS services_count,
            AVG(price_amount)::float AS avg_price,
            PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY price_amount)::float AS median_price
        FROM services
        WHERE category IS NOT NULL AND is_active = TRUE
        GROUP BY 1
    """)
    base = {r["category"]: dict(r) for r in rows}

    # Latest 24h volume / tx per category from category_stats
    rows = await conn.fetch("""
        SELECT DISTINCT ON (category)
            category, total_volume_24h::float AS volume_24h, total_tx_24h::int AS tx_24h, time
        FROM category_stats WHERE chain = 'all'
        ORDER BY category, time DESC
    """)
    for r in rows:
        if r["category"] in base:
            base[r["category"]]["volume_24h"] = r["volume_24h"] or 0.0
            base[r["category"]]["tx_24h"] = r["tx_24h"] or 0
            base[r["category"]]["last_hour"] = r["time"].isoformat() if r["time"] else None

    # Per-category buyer-label tx mix (last 30 days)
    rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT s.category, COALESCE(l.label, 'unlabeled') AS label, SUM(t_count.n)::int AS n
        FROM (
            SELECT t.service_id, t.buyer_address, COUNT(*) AS n
            FROM transactions t
            WHERE t.time >= NOW() - INTERVAL '30 days'
            GROUP BY 1, 2
        ) t_count
        JOIN services s ON s.id = t_count.service_id
        LEFT JOIN latest l ON l.buyer_address = t_count.buyer_address
        WHERE s.category IS NOT NULL
        GROUP BY 1, 2
    """)
    label_by_cat: dict[str, dict[str, int]] = {}
    for r in rows:
        label_by_cat.setdefault(r["category"], {})[r["label"]] = r["n"]

    out: list[dict] = []
    for cat, b in base.items():
        labels = label_by_cat.get(cat, {})
        total_tx = sum(labels.values()) or 1
        real = sum(labels.get(l, 0) for l in REAL_LABELS)
        wash = sum(labels.get(l, 0) for l in WASH_LABELS)
        b.update({
            "category": cat,
            "volume_24h": b.get("volume_24h", 0.0),
            "tx_24h": b.get("tx_24h", 0),
            "real_volume_pct": round(100 * real / total_tx, 1),
            "wash_pct": round(100 * wash / total_tx, 1),
            "label_distribution": {l: round(n / total_tx, 4) for l, n in labels.items()},
        })
        out.append(b)
    out.sort(key=lambda d: d.get("volume_24h", 0), reverse=True)
    return out


@app.get("/api/v1/categories")
async def categories_list():
    r = app.state.redis
    cached = await r.get(CATEGORIES_LIST_KEY)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        cats = await query_categories_list(conn)
    payload = {
        "categories": cats,
        "total_categories": len(cats),
        "total_services": sum(c["services_count"] for c in cats),
        "total_volume_24h": sum(c.get("volume_24h", 0) or 0 for c in cats),
        "total_tx_24h": sum(c.get("tx_24h", 0) or 0 for c in cats),
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
    }
    import json as _j
    await r.set(CATEGORIES_LIST_KEY, _j.dumps(payload), ex=CATEGORIES_TTL_SECONDS)
    return payload


# ─── Category detail ──────────────────────────────────────────────────
async def query_category_detail(conn, slug: str) -> dict | None:
    # Existence check + headline stats
    base = await conn.fetchrow("""
        SELECT
            category,
            COUNT(*)::int AS services_count,
            AVG(price_amount)::float AS avg_price,
            PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY price_amount)::float AS median_price
        FROM services
        WHERE category = $1 AND is_active = TRUE
        GROUP BY 1
    """, slug)
    if base is None:
        return None

    latest = await conn.fetchrow("""
        SELECT total_volume_24h::float AS volume_24h, total_tx_24h::int AS tx_24h, time
        FROM category_stats
        WHERE chain = 'all' AND category = $1
        ORDER BY time DESC LIMIT 1
    """, slug)

    # Time series — daily aggregate from category_stats over 30 days
    series_rows = await conn.fetch("""
        SELECT date_trunc('day', time) AS day,
               MAX(total_volume_24h)::float AS volume_24h,
               MAX(total_tx_24h)::int AS tx_24h
        FROM category_stats
        WHERE chain = 'all' AND category = $1
          AND time >= NOW() - INTERVAL '30 days'
        GROUP BY 1 ORDER BY 1
    """, slug)
    time_series = [
        {
            "date": r["day"].date().isoformat(),
            "volume": float(r["volume_24h"] or 0),
            "tx_count": int(r["tx_24h"] or 0),
        }
        for r in series_rows
    ]

    # Label distribution for this category (30d tx-weighted)
    label_rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT COALESCE(l.label, 'unlabeled') AS label, COUNT(*)::int AS n
        FROM transactions t
        JOIN services s ON s.id = t.service_id
        LEFT JOIN latest l ON l.buyer_address = t.buyer_address
        WHERE s.category = $1 AND t.time >= NOW() - INTERVAL '30 days'
        GROUP BY 1
    """, slug)
    total_tx_30d = sum(r["n"] for r in label_rows) or 1
    label_distribution = [
        {"label": r["label"], "n_tx": r["n"], "share_pct": round(100 * r["n"] / total_tx_30d, 2)}
        for r in label_rows
    ]
    real_n = sum(r["n"] for r in label_rows if r["label"] in REAL_LABELS)
    wash_n = sum(r["n"] for r in label_rows if r["label"] in WASH_LABELS)

    # Price histogram
    price_rows = await conn.fetch("""
        SELECT
            CASE
                WHEN price_amount IS NULL THEN 'unknown'
                WHEN price_amount = 0 THEN 'free'
                WHEN price_amount < 0.005 THEN '<$0.005'
                WHEN price_amount < 0.01 THEN '$0.005-0.01'
                WHEN price_amount < 0.05 THEN '$0.01-0.05'
                WHEN price_amount < 0.1 THEN '$0.05-0.1'
                ELSE '$0.1+'
            END AS bucket,
            COUNT(*)::int AS n
        FROM services
        WHERE category = $1 AND is_active = TRUE
        GROUP BY 1
    """, slug)
    BUCKET_ORDER = {"free": 0, "<$0.005": 1, "$0.005-0.01": 2, "$0.01-0.05": 3,
                    "$0.05-0.1": 4, "$0.1+": 5, "unknown": 6}
    price_distribution = sorted(
        ({"bucket": r["bucket"], "count": r["n"]} for r in price_rows),
        key=lambda d: BUCKET_ORDER.get(d["bucket"], 99),
    )

    # Top 20 services by 30d tx count
    top_rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        ),
        svc_tx AS (
            SELECT t.service_id,
                   COUNT(*)::int AS tx_30d,
                   SUM(t.amount)::float AS volume_30d,
                   COUNT(*) FILTER (WHERE l.label IN ('organic_user','ai_agent','exchange_user'))::int AS real_tx,
                   COUNT(*) FILTER (WHERE l.label IN ('self_test','suspected_wash'))::int AS wash_tx
            FROM transactions t
            LEFT JOIN latest l ON l.buyer_address = t.buyer_address
            WHERE t.time >= NOW() - INTERVAL '30 days'
            GROUP BY 1
        )
        SELECT s.id, s.name, s.resource_url, s.price_amount::float AS price,
               COALESCE(st.tx_30d, 0) AS tx_30d,
               COALESCE(st.volume_30d, 0) AS volume_30d,
               COALESCE(st.real_tx, 0) AS real_tx,
               COALESCE(st.wash_tx, 0) AS wash_tx,
               s.organic_traffic_pct::float AS organic_pct,
               s.suspected_wash_pct::float AS wash_pct
        FROM services s LEFT JOIN svc_tx st ON st.service_id = s.id
        WHERE s.category = $1 AND s.is_active = TRUE
        ORDER BY COALESCE(st.tx_30d, 0) DESC
        LIMIT 20
    """, slug)
    top_services = []
    for r in top_rows:
        tx = r["tx_30d"] or 0
        real_pct = (100 * r["real_tx"] / tx) if tx > 0 else (r["organic_pct"] or 0)
        wash_pct_calc = (100 * r["wash_tx"] / tx) if tx > 0 else (r["wash_pct"] or 0)
        top_services.append({
            "id": r["id"],
            "name": (r["name"] or "")[:120],
            "resource_url": r["resource_url"],
            "price": r["price"],
            "tx_30d": tx,
            "volume_30d": float(r["volume_30d"] or 0),
            "real_pct": round(real_pct or 0, 1),
            "wash_pct": round(wash_pct_calc or 0, 1),
        })

    return {
        "category": base["category"],
        "stats": {
            "services_count": base["services_count"],
            "avg_price": base["avg_price"],
            "median_price": base["median_price"],
            "volume_24h": float(latest["volume_24h"]) if latest and latest["volume_24h"] else 0,
            "tx_24h": int(latest["tx_24h"]) if latest and latest["tx_24h"] else 0,
            "real_volume_pct": round(100 * real_n / total_tx_30d, 1),
            "wash_pct": round(100 * wash_n / total_tx_30d, 1),
            "last_hour": latest["time"].isoformat() if latest and latest["time"] else None,
        },
        "time_series": time_series,
        "label_distribution": label_distribution,
        "price_distribution": price_distribution,
        "top_services": top_services,
    }


@app.get("/api/v1/categories/{slug}")
async def category_detail(slug: str):
    r = app.state.redis
    key = CATEGORY_DETAIL_KEY_FMT.format(slug=slug)
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        detail = await query_category_detail(conn, slug)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"category not found: {slug}")
    import json as _j
    await r.set(key, _j.dumps(detail), ex=CATEGORIES_TTL_SECONDS)
    return detail


SERVICES_LIST_KEY_FMT = "x402watch:services:list:v1:{h}"
SERVICE_DETAIL_KEY_FMT = "x402watch:services:detail:{id}:v1"
SERVICES_TTL_SECONDS = 300

VALID_CHAINS = {"base", "solana", "arbitrum", "base-sepolia", "polygon", "stellar:testnet"}
PRICE_BUCKETS: dict[str, tuple[float | None, float | None]] = {
    "lt_001":  (None, 0.001),
    "001_005": (0.001, 0.005),
    "005_01":  (0.005, 0.01),
    "01_05":   (0.01, 0.05),
    "05_1":    (0.05, 0.1),
    "gt_1":    (0.1, None),
}
SORTABLE_KEYS = {
    "tx_24h":     "tx_24h",
    "volume_24h": "volume_24h",
    "tx_total":   "tx_total",
    "price":      "price_amount",
    "real_pct":   "organic_traffic_pct",
    "wash_pct":   "suspected_wash_pct",
    "first_seen": "first_seen",
    "alpha":      "name",
}


def _hash_filters(filters: dict) -> str:
    import hashlib, json as _j
    return hashlib.sha1(_j.dumps(filters, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _coerce_filters(
    search: str | None,
    category: str | None,
    chain: str | None,
    price_bucket: str | None,
    min_real_pct: float | None,
    max_wash_pct: float | None,
    active_only: bool,
    show_placeholder: bool,
    sort: str,
    order: str,
    page: int,
    page_size: int,
) -> dict:
    return {
        "search": (search or "").strip().lower() or None,
        "category": category if category else None,
        "chain": chain if chain in VALID_CHAINS else None,
        "price_bucket": price_bucket if price_bucket in PRICE_BUCKETS else None,
        "min_real_pct": max(0, min(100, min_real_pct)) if min_real_pct is not None else None,
        "max_wash_pct": max(0, min(100, max_wash_pct)) if max_wash_pct is not None else None,
        "active_only": bool(active_only),
        "show_placeholder": bool(show_placeholder),
        "sort": sort if sort in SORTABLE_KEYS else "tx_24h",
        "order": "asc" if order == "asc" else "desc",
        "page": max(1, page),
        "page_size": max(1, min(200, page_size)),
    }


async def query_services_list(conn, f: dict) -> dict:
    where: list[str] = ["s.is_active = TRUE", "s.category IS NOT NULL"]
    args: list = []

    def add(cond: str, val):
        args.append(val)
        where.append(cond.replace("$$", f"${len(args)}"))

    if not f["show_placeholder"]:
        where.append("s.category != 'premium_placeholder'")
    if f["category"]:
        add("s.category = $$", f["category"])
    if f["chain"]:
        add("s.chain = $$", f["chain"])
    if f["price_bucket"]:
        lo, hi = PRICE_BUCKETS[f["price_bucket"]]
        if lo is not None:
            add("s.price_amount >= $$", lo)
        if hi is not None:
            add("s.price_amount < $$", hi)
    if f["min_real_pct"] is not None:
        add("COALESCE(s.organic_traffic_pct, 0) >= $$", f["min_real_pct"])
    if f["max_wash_pct"] is not None:
        add("COALESCE(s.suspected_wash_pct, 0) <= $$", f["max_wash_pct"])
    if f["search"]:
        add(
            "(LOWER(COALESCE(s.name,'')) LIKE '%' || $$ || '%' "
            "OR LOWER(COALESCE(s.description,'')) LIKE '%' || $$ || '%' "
            "OR LOWER(s.seller_address) LIKE '%' || $$ || '%')",
            f["search"],
        )
        # the same value is referenced 3 times — duplicate it
        args.extend([f["search"], f["search"]])
        # rewrite the last where clause to reference last 3 placeholders
        n = len(args)
        where[-1] = (
            "(LOWER(COALESCE(s.name,'')) LIKE '%' || $" + str(n - 2) + " || '%' "
            "OR LOWER(COALESCE(s.description,'')) LIKE '%' || $" + str(n - 1) + " || '%' "
            "OR LOWER(s.seller_address) LIKE '%' || $" + str(n) + " || '%')"
        )

    where_sql = " AND ".join(where)
    sort_col = SORTABLE_KEYS[f["sort"]]
    order_kw = "ASC" if f["order"] == "asc" else "DESC"
    nulls_kw = "NULLS LAST" if order_kw == "DESC" else "NULLS FIRST"

    # Active-only filter post-aggregation (we need tx_24h column)
    having_clause = "WHERE COALESCE(s24.tx_24h, 0) > 0" if f["active_only"] else ""

    query = f"""
        WITH svc_24h AS (
            SELECT service_id, COUNT(*)::int AS tx_24h, SUM(amount)::float AS volume_24h
            FROM transactions WHERE time >= NOW() - INTERVAL '24 hours' GROUP BY 1
        ),
        svc_total AS (
            SELECT service_id, COUNT(*)::int AS tx_total
            FROM transactions GROUP BY 1
        ),
        filtered AS (
            SELECT s.id, s.chain, s.seller_address, s.resource_url, s.name, s.description,
                   s.category, s.price_amount, s.first_seen,
                   s.organic_traffic_pct, s.suspected_wash_pct,
                   COALESCE(s24.tx_24h, 0) AS tx_24h,
                   COALESCE(s24.volume_24h, 0) AS volume_24h,
                   COALESCE(st.tx_total, 0) AS tx_total
            FROM services s
            LEFT JOIN svc_24h s24 ON s24.service_id = s.id
            LEFT JOIN svc_total st ON st.service_id = s.id
            WHERE {where_sql}
        ),
        active_filtered AS (
            SELECT * FROM filtered {having_clause}
        ),
        counted AS (
            SELECT *, COUNT(*) OVER () AS total_rows,
                   SUM(volume_24h) OVER () AS total_volume_24h,
                   SUM(tx_24h) OVER ()::int AS total_tx_24h
            FROM active_filtered
        )
        SELECT * FROM counted
        ORDER BY {sort_col} {order_kw} {nulls_kw}, id
        LIMIT {f['page_size']} OFFSET {(f['page'] - 1) * f['page_size']}
    """
    rows = await conn.fetch(query, *args)
    services = []
    total_rows = 0
    total_vol = 0.0
    total_tx = 0
    for r in rows:
        total_rows = int(r["total_rows"] or 0)
        total_vol = float(r["total_volume_24h"] or 0)
        total_tx = int(r["total_tx_24h"] or 0)
        services.append({
            "id": r["id"],
            "chain": r["chain"],
            "seller_address": r["seller_address"],
            "resource_url": r["resource_url"],
            "name": (r["name"] or "")[:200],
            "description": (r["description"] or "")[:400],
            "category": r["category"],
            "price_amount": float(r["price_amount"]) if r["price_amount"] is not None else None,
            "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
            "tx_24h": int(r["tx_24h"] or 0),
            "volume_24h": float(r["volume_24h"] or 0),
            "tx_total": int(r["tx_total"] or 0),
            "real_volume_pct": float(r["organic_traffic_pct"]) if r["organic_traffic_pct"] is not None else 0.0,
            "wash_pct": float(r["suspected_wash_pct"]) if r["suspected_wash_pct"] is not None else 0.0,
        })

    # Per-service buyer-label distribution (only for the page's services)
    if services:
        ids = [s["id"] for s in services]
        label_rows = await conn.fetch("""
            WITH latest AS (
                SELECT DISTINCT ON (buyer_address) buyer_address, label
                FROM buyer_labels ORDER BY buyer_address, time DESC
            )
            SELECT t.service_id, COALESCE(l.label, 'unlabeled') AS label, COUNT(*)::int AS n
            FROM transactions t
            LEFT JOIN latest l ON l.buyer_address = t.buyer_address
            WHERE t.service_id = ANY($1::int[])
              AND t.time >= NOW() - INTERVAL '30 days'
            GROUP BY 1, 2
        """, ids)
        labels_by_id: dict[int, dict[str, int]] = {}
        for r in label_rows:
            labels_by_id.setdefault(r["service_id"], {})[r["label"]] = r["n"]
        for s in services:
            labels = labels_by_id.get(s["id"], {})
            tot = sum(labels.values()) or 1
            s["label_distribution"] = {l: round(n / tot, 4) for l, n in labels.items()}

    page_size = f["page_size"]
    total_pages = (total_rows + page_size - 1) // page_size if total_rows else 0

    return {
        "services": services,
        "pagination": {
            "page": f["page"],
            "page_size": page_size,
            "total": total_rows,
            "total_pages": total_pages,
        },
        "summary": {
            "total_volume_24h": total_vol,
            "total_tx_24h": total_tx,
        },
        "filters_applied": f,
    }


@app.get("/api/v1/services")
async def services_list(
    search: str | None = None,
    category: str | None = None,
    chain: str | None = None,
    price_bucket: str | None = None,
    min_real_pct: float | None = None,
    max_wash_pct: float | None = None,
    active_only: bool = False,
    show_placeholder: bool = False,
    sort: str = "tx_24h",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
):
    f = _coerce_filters(
        search, category, chain, price_bucket, min_real_pct, max_wash_pct,
        active_only, show_placeholder, sort, order, page, page_size,
    )
    h = _hash_filters(f)
    key = SERVICES_LIST_KEY_FMT.format(h=h)
    r = app.state.redis
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        payload = await query_services_list(conn, f)
    import json as _j
    await r.set(key, _j.dumps(payload), ex=SERVICES_TTL_SECONDS)
    return payload


@app.get("/api/v1/services/{service_id}")
async def service_detail(service_id: int):
    r = app.state.redis
    key = SERVICE_DETAIL_KEY_FMT.format(id=service_id)
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        base = await conn.fetchrow("""
            SELECT s.id, s.chain, s.seller_address, s.resource_url, s.name, s.description,
                   s.category, s.price_amount::float AS price_amount, s.first_seen, s.last_seen,
                   s.organic_traffic_pct, s.suspected_wash_pct,
                   s.metadata->>'developer_volume_pct' AS dev_pct
            FROM services s WHERE s.id = $1
        """, service_id)
        if base is None:
            raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
        agg = await conn.fetchrow("""
            SELECT COUNT(*)::int AS tx_total,
                   SUM(amount)::float AS volume_total,
                   COUNT(*) FILTER (WHERE time >= NOW() - INTERVAL '24 hours')::int AS tx_24h,
                   COALESCE(SUM(amount) FILTER (WHERE time >= NOW() - INTERVAL '24 hours'), 0)::float AS volume_24h
            FROM transactions WHERE service_id = $1
        """, service_id)
        time_series = await conn.fetch("""
            SELECT date_trunc('day', time) AS day,
                   COUNT(*)::int AS tx_count,
                   SUM(amount)::float AS volume
            FROM transactions
            WHERE service_id = $1 AND time >= NOW() - INTERVAL '30 days'
            GROUP BY 1 ORDER BY 1
        """, service_id)
        label_rows = await conn.fetch("""
            WITH latest AS (
                SELECT DISTINCT ON (buyer_address) buyer_address, label
                FROM buyer_labels ORDER BY buyer_address, time DESC
            )
            SELECT COALESCE(l.label, 'unlabeled') AS label, COUNT(*)::int AS n_tx
            FROM transactions t
            LEFT JOIN latest l ON l.buyer_address = t.buyer_address
            WHERE t.service_id = $1 AND t.time >= NOW() - INTERVAL '30 days'
            GROUP BY 1
        """, service_id)
        top_buyers = await conn.fetch("""
            WITH latest AS (
                SELECT DISTINCT ON (buyer_address) buyer_address, label, confidence
                FROM buyer_labels ORDER BY buyer_address, time DESC
            )
            SELECT t.buyer_address, l.label, l.confidence,
                   COUNT(*)::int AS tx_count,
                   SUM(t.amount)::float AS volume
            FROM transactions t
            LEFT JOIN latest l ON l.buyer_address = t.buyer_address
            WHERE t.service_id = $1
            GROUP BY t.buyer_address, l.label, l.confidence
            ORDER BY tx_count DESC LIMIT 10
        """, service_id)

    label_total = sum(r["n_tx"] for r in label_rows) or 1
    payload = {
        "service": {
            "id": base["id"],
            "chain": base["chain"],
            "seller_address": base["seller_address"],
            "resource_url": base["resource_url"],
            "name": base["name"],
            "description": base["description"],
            "category": base["category"],
            "price_amount": base["price_amount"],
            "first_seen": base["first_seen"].isoformat() if base["first_seen"] else None,
            "last_seen": base["last_seen"].isoformat() if base["last_seen"] else None,
            "real_volume_pct": float(base["organic_traffic_pct"]) if base["organic_traffic_pct"] is not None else 0.0,
            "wash_pct": float(base["suspected_wash_pct"]) if base["suspected_wash_pct"] is not None else 0.0,
            "developer_volume_pct": float(base["dev_pct"]) if base["dev_pct"] else 0.0,
        },
        "stats": {
            "tx_total": int(agg["tx_total"] or 0),
            "volume_total": float(agg["volume_total"] or 0),
            "tx_24h": int(agg["tx_24h"] or 0),
            "volume_24h": float(agg["volume_24h"] or 0),
        },
        "time_series_30d": [
            {
                "date": r["day"].date().isoformat(),
                "tx_count": int(r["tx_count"] or 0),
                "volume": float(r["volume"] or 0),
            }
            for r in time_series
        ],
        "label_distribution": [
            {
                "label": r["label"],
                "n_tx": r["n_tx"],
                "share_pct": round(100 * r["n_tx"] / label_total, 2),
            }
            for r in label_rows
        ],
        "top_buyers": [
            {
                "buyer_address": r["buyer_address"],
                "label": r["label"],
                "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                "tx_count": int(r["tx_count"] or 0),
                "volume": float(r["volume"] or 0),
            }
            for r in top_buyers
        ],
    }
    import json as _j
    await r.set(key, _j.dumps(payload), ex=SERVICES_TTL_SECONDS)
    return payload


@app.get("/api/v1/health")
async def health():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        await app.state.redis.ping()
        return {"ok": True, "ts": datetime.now(tz=timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ─── Day 14: /trends + /wash-report ────────────────────────────────────
TRENDS_KEY = "x402watch:trends:v1"
WASH_REPORT_KEY = "x402watch:wash-report:v1"
TRENDS_TTL_SECONDS = 300
WASH_REPORT_TTL_SECONDS = 300

# 8 wash labels in priority order (mirrors src/lib/wash.ts on the frontend).
WASH_REPORT_LABELS = (
    "organic_user",
    "self_test",
    "developer",
    "suspected_wash",
    "ai_agent",
    "analytics_bot",
    "exchange_user",
    "verifier",
)


# ─── Trends queries ────────────────────────────────────────────────────
async def query_trends_summary(conn) -> dict:
    new_24h = await conn.fetchval(
        "SELECT COUNT(*)::int FROM services "
        "WHERE first_seen >= NOW() - INTERVAL '24 hours' AND is_active = TRUE"
    )
    new_prev = await conn.fetchval(
        "SELECT COUNT(*)::int FROM services "
        "WHERE first_seen >= NOW() - INTERVAL '48 hours' "
        "  AND first_seen <  NOW() - INTERVAL '24 hours' "
        "  AND is_active = TRUE"
    )
    tx_24h = await conn.fetchval(
        "SELECT COUNT(*)::int FROM transactions WHERE time >= NOW() - INTERVAL '24 hours'"
    )
    vol_24h = await conn.fetchval(
        "SELECT COALESCE(SUM(amount), 0)::float "
        "FROM transactions WHERE time >= NOW() - INTERVAL '24 hours'"
    )
    buyers_24h = await conn.fetchval(
        "SELECT COUNT(DISTINCT buyer_address)::int "
        "FROM transactions WHERE time >= NOW() - INTERVAL '24 hours'"
    )
    new_24h = int(new_24h or 0)
    new_prev = int(new_prev or 0)
    if new_prev == 0:
        change_pct = 100.0 if new_24h > 0 else 0.0
    else:
        change_pct = (new_24h - new_prev) / new_prev * 100.0
    return {
        "new_services_24h": new_24h,
        "new_services_prev_24h": new_prev,
        "new_services_change_pct": round(change_pct, 1),
        "total_tx_24h": int(tx_24h or 0),
        "total_volume_24h": round(float(vol_24h or 0), 2),
        "active_buyers_24h": int(buyers_24h or 0),
    }


async def query_daily_new_services_14d(conn) -> list[dict]:
    rows = await conn.fetch(
        "SELECT date_trunc('day', first_seen)::date AS day, COUNT(*)::int AS n "
        "FROM services WHERE first_seen >= NOW() - INTERVAL '14 days' AND is_active = TRUE "
        "GROUP BY 1 ORDER BY 1"
    )
    return [{"date": r["day"].isoformat(), "count": int(r["n"] or 0)} for r in rows]


async def query_recent_new_services(conn) -> list[dict]:
    rows = await conn.fetch("""
        SELECT id, name,
               COALESCE(category, 'other') AS category,
               chain, price_amount::float AS price_amount, first_seen
        FROM services
        WHERE first_seen >= NOW() - INTERVAL '24 hours'
          AND is_active = TRUE
          AND (category IS NULL OR category != 'premium_placeholder')
        ORDER BY first_seen DESC
        LIMIT 10
    """)
    return [
        {
            "id": r["id"],
            "name": (r["name"] or "")[:200],
            "category": r["category"],
            "chain": r["chain"],
            "price_amount": float(r["price_amount"]) if r["price_amount"] is not None else None,
            "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
        }
        for r in rows
    ]


async def query_category_movers(conn) -> list[dict]:
    rows = await conn.fetch("""
        WITH win AS (
            SELECT s.category,
                   COALESCE(SUM(t.amount) FILTER (
                       WHERE t.time >= NOW() - INTERVAL '24 hours'
                   ), 0)::float AS volume_24h,
                   COALESCE(SUM(t.amount) FILTER (
                       WHERE t.time >= NOW() - INTERVAL '48 hours'
                         AND t.time <  NOW() - INTERVAL '24 hours'
                   ), 0)::float AS volume_prev,
                   COUNT(*) FILTER (
                       WHERE t.time >= NOW() - INTERVAL '24 hours'
                   )::int AS tx_24h,
                   COUNT(*) FILTER (
                       WHERE t.time >= NOW() - INTERVAL '48 hours'
                         AND t.time <  NOW() - INTERVAL '24 hours'
                   )::int AS tx_prev
            FROM transactions t
            JOIN services s ON s.id = t.service_id
            WHERE t.time >= NOW() - INTERVAL '48 hours'
              AND s.category IS NOT NULL
              AND s.category != 'premium_placeholder'
            GROUP BY 1
        )
        SELECT *
        FROM win
        WHERE volume_24h > 0 OR volume_prev > 0
    """)
    out = []
    for r in rows:
        v_cur = float(r["volume_24h"] or 0)
        v_prev = float(r["volume_prev"] or 0)
        t_cur = int(r["tx_24h"] or 0)
        t_prev = int(r["tx_prev"] or 0)
        v_change = (
            (100.0 if v_cur > 0 else 0.0)
            if v_prev == 0
            else (v_cur - v_prev) / v_prev * 100.0
        )
        t_change = (
            (100.0 if t_cur > 0 else 0.0)
            if t_prev == 0
            else (t_cur - t_prev) / t_prev * 100.0
        )
        out.append({
            "category": r["category"],
            "volume_24h": round(v_cur, 2),
            "volume_prev": round(v_prev, 2),
            "volume_change_pct": round(v_change, 1),
            "tx_24h": t_cur,
            "tx_prev": t_prev,
            "tx_change_pct": round(t_change, 1),
        })
    out.sort(key=lambda d: abs(d["volume_change_pct"]), reverse=True)
    return out


async def query_hot_services(conn) -> list[dict]:
    rows = await conn.fetch("""
        WITH cur AS (
            SELECT service_id,
                   COUNT(*) FILTER (
                       WHERE time >= NOW() - INTERVAL '24 hours'
                   )::int AS tx_24h,
                   COUNT(*) FILTER (
                       WHERE time >= NOW() - INTERVAL '48 hours'
                         AND time <  NOW() - INTERVAL '24 hours'
                   )::int AS tx_prev
            FROM transactions
            WHERE time >= NOW() - INTERVAL '48 hours'
            GROUP BY 1
        )
        SELECT s.id, s.name, s.category, s.chain,
               cur.tx_24h, cur.tx_prev,
               COALESCE(s.organic_traffic_pct, 0)::float AS real_volume_pct,
               COALESCE(s.suspected_wash_pct, 0)::float AS wash_pct
        FROM cur
        JOIN services s ON s.id = cur.service_id
        WHERE cur.tx_24h >= 100
          AND s.is_active = TRUE
          AND s.category != 'premium_placeholder'
    """)
    out = []
    for r in rows:
        t_cur = int(r["tx_24h"] or 0)
        t_prev = int(r["tx_prev"] or 0)
        # tx_prev=0 → treat new traffic as 100%+ (proportional to magnitude
        # via a /1 floor) so new-and-large surges rank above small ones.
        change = (t_cur * 100.0) if t_prev == 0 else (t_cur - t_prev) / t_prev * 100.0
        if change < 50:
            continue
        out.append({
            "id": r["id"],
            "name": (r["name"] or "")[:200],
            "category": r["category"],
            "chain": r["chain"],
            "tx_24h": t_cur,
            "tx_prev": t_prev,
            "tx_change_pct": round(change, 1),
            "real_volume_pct": round(float(r["real_volume_pct"] or 0), 1),
            "wash_pct": round(float(r["wash_pct"] or 0), 1),
        })
    out.sort(key=lambda d: d["tx_change_pct"], reverse=True)
    return out[:20]


async def build_trends_payload() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        summary = await query_trends_summary(conn)
        daily = await query_daily_new_services_14d(conn)
        recent = await query_recent_new_services(conn)
        movers = await query_category_movers(conn)
        hot = await query_hot_services(conn)
    return {
        "summary": summary,
        "daily_new_services": daily,
        "recent_new_services": recent,
        "category_movers": movers,
        "hot_services": hot,
    }


@app.get("/api/v1/trends")
async def trends():
    r = app.state.redis
    cached = await r.get(TRENDS_KEY)
    if cached:
        import json as _j
        return _j.loads(cached)
    payload = await build_trends_payload()
    import json as _j
    await r.set(TRENDS_KEY, _j.dumps(payload), ex=TRENDS_TTL_SECONDS)
    return payload


# ─── Wash report queries ───────────────────────────────────────────────
async def query_wash_stats(conn) -> dict:
    row = await conn.fetchrow("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        ),
        active AS (
            SELECT DISTINCT buyer_address
            FROM transactions
            WHERE time >= NOW() - INTERVAL '30 days'
        )
        SELECT
            (SELECT COUNT(*)::int FROM active) AS total_active_buyers_30d,
            (SELECT COUNT(*)::int FROM active a
                JOIN latest l ON l.buyer_address = a.buyer_address
                WHERE l.label = 'suspected_wash') AS suspected_wash_count,
            (SELECT COUNT(*)::int FROM active a
                JOIN latest l ON l.buyer_address = a.buyer_address
                WHERE l.label = 'self_test') AS self_test_count
    """)
    real_pct = await conn.fetchval("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT COALESCE(
            SUM(CASE WHEN l.label IN ('organic_user','ai_agent','exchange_user')
                     THEN t.amount ELSE 0 END)
            / NULLIF(SUM(t.amount), 0) * 100,
            0
        )::float
        FROM transactions t
        LEFT JOIN latest l ON l.buyer_address = t.buyer_address
        WHERE t.time >= NOW() - INTERVAL '30 days'
    """)
    return {
        "total_active_buyers_30d": int(row["total_active_buyers_30d"] or 0),
        "real_volume_pct": round(float(real_pct or 0), 1),
        "suspected_wash_count": int(row["suspected_wash_count"] or 0),
        "self_test_count": int(row["self_test_count"] or 0),
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
    }


async def query_wash_label_distribution(conn) -> dict[str, int]:
    rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        ),
        active AS (
            SELECT DISTINCT buyer_address
            FROM transactions
            WHERE time >= NOW() - INTERVAL '30 days'
        )
        SELECT COALESCE(l.label, 'unlabeled') AS label, COUNT(*)::int AS n
        FROM active a
        LEFT JOIN latest l ON l.buyer_address = a.buyer_address
        GROUP BY 1
    """)
    counts = {r["label"]: int(r["n"] or 0) for r in rows}
    # Always emit all 8 keys (zero when no buyer carries the label) so the
    # frontend can render the full pattern table without conditional logic.
    return {label: counts.get(label, 0) for label in WASH_REPORT_LABELS}


async def query_wash_time_series(conn) -> list[dict]:
    rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address) buyer_address, label
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT date_trunc('day', t.time)::date AS day,
               COUNT(*)::int AS n_total,
               COUNT(*) FILTER (WHERE l.label = 'suspected_wash')::int AS n_wash,
               COUNT(*) FILTER (WHERE l.label = 'self_test')::int AS n_self_test
        FROM transactions t
        LEFT JOIN latest l ON l.buyer_address = t.buyer_address
        WHERE t.time >= NOW() - INTERVAL '14 days'
        GROUP BY 1 ORDER BY 1
    """)
    out = []
    for r in rows:
        n = int(r["n_total"] or 0) or 1
        out.append({
            "date": r["day"].isoformat(),
            "wash_pct": round(int(r["n_wash"] or 0) / n * 100, 2),
            "self_test_pct": round(int(r["n_self_test"] or 0) / n * 100, 2),
        })
    return out


# Hardcoded case studies — each entry is fully anonymized and contains no
# service names, seller addresses, or service IDs by construction. The
# frontend trusts this guarantee; do not introduce a code path that pulls
# identifying fields into this list.
WASH_CASE_STUDIES: list[dict] = [
    {
        "anonymous_id": "A",
        "pattern_type": "sophisticated_sybil",
        "buyer_count": 60,
        "confidence": 0.90,
        "wash_pct": 93.4,
        "signals": ["uniform_amount", "coordinated_start", "uniform_tx_count_cv", "cohort_size"],
        "details": [
            "All buyers paying exactly $0.02 (uniform amount: 97%)",
            "All started within a 12-minute window (coordinated start: 88%)",
            "Each making 78–79 transactions (tx count CV: 0.23)",
            "Random wallet addresses (no vanity pattern)",
        ],
    },
    {
        "anonymous_id": "B",
        "pattern_type": "vanity_cluster",
        "buyer_count": 17,
        "confidence": 0.97,
        "wash_pct": 100.0,
        "signals": ["vanity_strict", "single_service"],
        "details": [
            "17 wallets sharing identical 4-char prefix and 3-char suffix pattern",
            "Statistical impossibility for randomly generated addresses",
            "All paying a single service (single-service concentration)",
        ],
    },
    {
        "anonymous_id": "C",
        "pattern_type": "operator_self_test",
        "buyer_count": 8,
        "confidence": 0.66,
        "wash_pct": 0.0,
        "signals": ["vanity_broad", "single_service", "single_tx", "tiny_amount"],
        "details": [
            "Small cohort (n<10) of vanity-clustered wallets",
            "Operator-controlled test traffic during service launch",
            "Carved out as legitimate self_test, not classified as wash",
        ],
    },
    {
        "anonymous_id": "D",
        "pattern_type": "developer_dominance",
        "buyer_count": 102,
        "confidence": 0.85,
        "wash_pct": 0.6,
        "signals": ["single_service_concentration", "high_tx_volume", "regular_intervals"],
        "details": [
            "102 distinct wallets, each paying a single service",
            "Heavy bot pattern (top_svc_share ≥ 0.90)",
            "Conservatively excluded from real_volume",
            "May include legitimate production bots (operator self-disclosure pending)",
        ],
    },
    {
        "anonymous_id": "E",
        "pattern_type": "clean_organic",
        "buyer_count": 45,
        "confidence": 0.75,
        "wash_pct": 0.0,
        "signals": ["diverse_amounts", "diverse_timing", "multi_service_buyers"],
        "details": [
            "Diverse buyer base with varied transaction amounts",
            "Distributed timing across the 30-day window",
            "Buyers also use other unrelated services",
            "100% organic_user classification",
        ],
    },
]


async def build_wash_report_payload() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await query_wash_stats(conn)
        labels = await query_wash_label_distribution(conn)
        series = await query_wash_time_series(conn)
    return {
        "stats": stats,
        "label_distribution": labels,
        "wash_pct_time_series": series,
        "case_studies": WASH_CASE_STUDIES,
    }


@app.get("/api/v1/wash-report")
async def wash_report():
    r = app.state.redis
    cached = await r.get(WASH_REPORT_KEY)
    if cached:
        import json as _j
        return _j.loads(cached)
    payload = await build_wash_report_payload()
    import json as _j
    await r.set(WASH_REPORT_KEY, _j.dumps(payload), ex=WASH_REPORT_TTL_SECONDS)
    return payload


# ─── Day 21: paid x402 endpoints ────────────────────────────────────────
import os as _os21
from x402.http import HTTPFacilitatorClient, FacilitatorConfig, PaymentOption
from cdp.x402 import create_facilitator_config
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.server import x402ResourceServer
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.mechanisms.svm.exact import ExactSvmServerScheme
from x402.extensions.bazaar import (
    bazaar_resource_server_extension,
    declare_discovery_extension,
    OutputConfig,
)


X402_PAY_TO = _os21.environ["X402_WATCH_PAY_TO"]
X402_NETWORK = "eip155:8453"  # Base mainnet (USDC native)
SOLANA_NETWORK = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"  # Solana mainnet beta
SOLANA_PAY_TO = _os21.environ.get(
    "X402_WATCH_SOLANA_PAY_TO",
    "3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9",  # KR Crypto pattern reuse
)
_cdp_id = _os21.environ.get("CDP_API_KEY_ID")
_cdp_secret = _os21.environ.get("CDP_API_KEY_SECRET")
if _cdp_id and _cdp_secret:
    # Mainnet — Coinbase Developer Platform facilitator (CDP keys required).
    _facilitator = HTTPFacilitatorClient(
        create_facilitator_config(api_key_id=_cdp_id, api_key_secret=_cdp_secret)
    )
    X402_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"
else:
    # Testnet fallback — public facilitator, Base Sepolia only.
    X402_FACILITATOR_URL = _os21.environ.get(
        "X402_FACILITATOR_URL", "https://x402.org/facilitator"
    )
    _facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=X402_FACILITATOR_URL))
x402_server = x402ResourceServer(facilitator_clients=_facilitator)
x402_server.register("eip155:8453", ExactEvmServerScheme())  # Base mainnet (CDP facilitator)
x402_server.register(SOLANA_NETWORK, ExactSvmServerScheme())
x402_server.register_extension(bazaar_resource_server_extension)


def _accept(price: str) -> list[PaymentOption]:
    return [
        PaymentOption(
            scheme="exact",
            pay_to=X402_PAY_TO,
            price=price,
            network=X402_NETWORK,
        ),
        PaymentOption(
            scheme="exact",
            pay_to=SOLANA_PAY_TO,
            price=price,
            network=SOLANA_NETWORK,
        ),
    ]


# ─── Cache keys ─────────────────────────────────────────────────────────
WASH_DETAIL_KEY_FMT = "x402watch:paid:wash-detail:{id}:v1"
BUYER_PROFILE_KEY_FMT = "x402watch:paid:buyer-profile:{addr}:v1"
SVC_TX_KEY_FMT = "x402watch:paid:svc-tx:{id}:v1"
CAT_HISTORY_KEY_FMT = "x402watch:paid:cat-history:{slug}:v1"
PAID_TTL_SECONDS = 300  # 5 minutes — same as the rest of the API


# ─── Endpoint 1: /services/{id}/wash-detail ($0.005) ────────────────────
async def query_wash_detail(conn, service_id: int) -> dict | None:
    base = await conn.fetchrow(
        "SELECT id, name, category, seller_address FROM services WHERE id = $1",
        service_id,
    )
    if base is None:
        return None
    rows = await conn.fetch("""
        WITH latest AS (
            SELECT DISTINCT ON (buyer_address)
                   buyer_address, label, confidence, reason
            FROM buyer_labels ORDER BY buyer_address, time DESC
        )
        SELECT t.buyer_address,
               COALESCE(l.label, 'unlabeled') AS label,
               l.confidence,
               l.reason,
               COUNT(*)::int AS tx_count,
               SUM(t.amount)::float AS volume,
               MIN(t.time) AS first_tx,
               MAX(t.time) AS last_tx
        FROM transactions t
        LEFT JOIN latest l ON l.buyer_address = t.buyer_address
        WHERE t.service_id = $1
        GROUP BY t.buyer_address, l.label, l.confidence, l.reason
        ORDER BY tx_count DESC
        LIMIT 50
    """, service_id)
    buyers = [
        {
            "address": r["buyer_address"],
            "label": r["label"],
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "reason": r["reason"] if r["reason"] else "",
            "tx_count": int(r["tx_count"] or 0),
            "volume": float(r["volume"] or 0),
            "first_tx": r["first_tx"].isoformat() if r["first_tx"] else None,
            "last_tx": r["last_tx"].isoformat() if r["last_tx"] else None,
        }
        for r in rows
    ]
    summary = await conn.fetchrow("""
        SELECT COUNT(DISTINCT buyer_address)::int AS cohort_size,
               PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY amount)::float AS median_amount,
               COUNT(DISTINCT amount)::int AS distinct_amounts
        FROM transactions WHERE service_id = $1
    """, service_id)
    return {
        "service": {
            "id": base["id"],
            "name": (base["name"] or "")[:200],
            "category": base["category"],
        },
        "buyers": buyers,
        "cohort_summary": {
            "cohort_size": int(summary["cohort_size"] or 0),
            "median_amount": float(summary["median_amount"] or 0),
            "distinct_amounts": int(summary["distinct_amounts"] or 0),
        },
    }


@app.get("/api/v1/services/{service_id}/wash-detail")
async def services_wash_detail(service_id: int):
    r = app.state.redis
    key = WASH_DETAIL_KEY_FMT.format(id=service_id)
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        payload = await query_wash_detail(conn, service_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    import json as _j
    await r.set(key, _j.dumps(payload), ex=PAID_TTL_SECONDS)
    return payload


# ─── Endpoint 2: /buyers/{address}/profile ($0.005) ─────────────────────
async def query_buyer_profile(conn, address: str) -> dict:
    label_row = await conn.fetchrow("""
        SELECT label, confidence, reason, time AS labeled_at
        FROM buyer_labels
        WHERE buyer_address = $1
        ORDER BY time DESC
        LIMIT 1
    """, address)
    services_rows = await conn.fetch("""
        SELECT s.id, s.category, s.chain,
               COUNT(*)::int AS tx_count,
               SUM(t.amount)::float AS volume
        FROM transactions t
        JOIN services s ON s.id = t.service_id
        WHERE t.buyer_address = $1
        GROUP BY s.id, s.category, s.chain
        ORDER BY tx_count DESC
        LIMIT 100
    """, address)
    pattern = await conn.fetchrow("""
        SELECT COUNT(*)::int AS tx_count,
               SUM(amount)::float AS total_volume,
               MIN(time) AS first_seen,
               MAX(time) AS last_seen,
               EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))::float AS span_seconds
        FROM transactions WHERE buyer_address = $1
    """, address)
    return {
        "address": address,
        "label": label_row["label"] if label_row else "unlabeled",
        "confidence": float(label_row["confidence"]) if label_row and label_row["confidence"] is not None else None,
        "reason": label_row["reason"] if label_row and label_row["reason"] else "",
        "labeled_at": label_row["labeled_at"].isoformat() if label_row and label_row["labeled_at"] else None,
        "services_used": [
            {
                "id": s["id"],
                "category": s["category"],
                "chain": s["chain"],
                "tx_count": int(s["tx_count"] or 0),
                "volume": float(s["volume"] or 0),
            }
            for s in services_rows
        ],
        "summary": {
            "tx_count": int(pattern["tx_count"] or 0),
            "total_volume": float(pattern["total_volume"] or 0),
            "first_seen": pattern["first_seen"].isoformat() if pattern["first_seen"] else None,
            "last_seen": pattern["last_seen"].isoformat() if pattern["last_seen"] else None,
            "span_seconds": float(pattern["span_seconds"] or 0),
        },
    }


@app.get("/api/v1/buyers/{address}/profile")
async def buyer_profile(address: str):
    r = app.state.redis
    key = BUYER_PROFILE_KEY_FMT.format(addr=address.lower())
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        payload = await query_buyer_profile(conn, address)
    import json as _j
    await r.set(key, _j.dumps(payload), ex=PAID_TTL_SECONDS)
    return payload


# ─── Endpoint 3: /services/{id}/transactions ($0.01) ────────────────────
async def query_service_transactions(conn, service_id: int) -> dict | None:
    base = await conn.fetchrow("SELECT id, name, chain FROM services WHERE id = $1", service_id)
    if base is None:
        return None
    rows = await conn.fetch("""
        SELECT tx_hash, buyer_address, amount::float AS amount, time
        FROM transactions
        WHERE service_id = $1 AND time >= NOW() - INTERVAL '30 days'
        ORDER BY time DESC
        LIMIT 5000
    """, service_id)
    return {
        "service": {
            "id": base["id"],
            "name": (base["name"] or "")[:200],
            "chain": base["chain"],
        },
        "transactions": [
            {
                "tx_hash": r["tx_hash"],
                "buyer": r["buyer_address"],
                "amount": float(r["amount"] or 0),
                "time": r["time"].isoformat() if r["time"] else None,
            }
            for r in rows
        ],
        "total": len(rows),
        "window": "30d",
        "limit": 5000,
    }


@app.get("/api/v1/services/{service_id}/transactions")
async def services_transactions(service_id: int):
    r = app.state.redis
    key = SVC_TX_KEY_FMT.format(id=service_id)
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        payload = await query_service_transactions(conn, service_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    import json as _j
    await r.set(key, _j.dumps(payload), ex=PAID_TTL_SECONDS)
    return payload


# ─── Endpoint 4: /categories/{slug}/full-history ($0.02) ────────────────
async def query_category_full_history(conn, slug: str) -> dict | None:
    exists = await conn.fetchval(
        "SELECT 1 FROM services WHERE category = $1 LIMIT 1", slug
    )
    if not exists:
        return None
    rows = await conn.fetch("""
        SELECT date_trunc('hour', time) AS hour,
               MAX(total_volume_24h)::float AS volume_24h,
               MAX(total_tx_24h)::int AS tx_24h
        FROM category_stats
        WHERE chain = 'all' AND category = $1
          AND time >= NOW() - INTERVAL '365 days'
        GROUP BY 1 ORDER BY 1
    """, slug)
    return {
        "category": slug,
        "points": [
            {
                "time": r["hour"].isoformat(),
                "volume_24h": float(r["volume_24h"] or 0),
                "tx_24h": int(r["tx_24h"] or 0),
            }
            for r in rows
        ],
        "total": len(rows),
        "window": "365d",
        "granularity": "1h",
    }


@app.get("/api/v1/categories/{slug}/full-history")
async def category_full_history(slug: str):
    r = app.state.redis
    key = CAT_HISTORY_KEY_FMT.format(slug=slug)
    cached = await r.get(key)
    if cached:
        import json as _j
        return _j.loads(cached)
    pool = await get_pool()
    async with pool.acquire() as conn:
        payload = await query_category_full_history(conn, slug)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"category not found: {slug}")
    import json as _j
    await r.set(key, _j.dumps(payload), ex=PAID_TTL_SECONDS)
    return payload


# ─── Endpoint 5: POST /wash/check ($0.05) ───────────────────────────────
from pydantic import BaseModel as _BM21


class WashCheckBody(_BM21):
    address: str


@app.post("/api/v1/wash/check")
async def wash_check(body: WashCheckBody):
    """Real-time wash analysis for any wallet or seller address.

    Phase 1 returns the latest cached label for the address. Real-time
    re-classification (re-running the labeller pipeline on demand) is a
    Phase 2 follow-up.
    """
    address = body.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    pool = await get_pool()
    async with pool.acquire() as conn:
        label_row = await conn.fetchrow("""
            SELECT label, confidence, reason, time AS labeled_at
            FROM buyer_labels
            WHERE buyer_address = $1
            ORDER BY time DESC LIMIT 1
        """, address)
        seller = await conn.fetchrow("""
            SELECT id, name, category, suspected_wash_pct
            FROM services WHERE seller_address = $1
            ORDER BY last_seen DESC NULLS LAST, first_seen DESC NULLS LAST
            LIMIT 1
        """, address) if address.startswith("0x") else None
        sample_signals = await conn.fetchrow("""
            SELECT COUNT(*)::int AS tx_count,
                   COUNT(DISTINCT amount)::int AS distinct_amounts,
                   MIN(time) AS first_tx,
                   MAX(time) AS last_tx
            FROM transactions WHERE buyer_address = $1
        """, address)
    label = label_row["label"] if label_row else "unlabeled"
    return {
        "address": address,
        "label": label,
        "confidence": float(label_row["confidence"]) if label_row and label_row["confidence"] is not None else None,
        "reason": label_row["reason"] if label_row and label_row["reason"] else "",
        "labeled_at": label_row["labeled_at"].isoformat() if label_row and label_row["labeled_at"] else None,
        "as_seller": (
            {
                "service_id": seller["id"],
                "name": (seller["name"] or "")[:200],
                "category": seller["category"],
                "suspected_wash_pct": float(seller["suspected_wash_pct"] or 0),
            }
            if seller else None
        ),
        "signals": {
            "tx_count": int(sample_signals["tx_count"] or 0) if sample_signals else 0,
            "distinct_amounts": int(sample_signals["distinct_amounts"] or 0) if sample_signals else 0,
            "first_tx": sample_signals["first_tx"].isoformat() if sample_signals and sample_signals["first_tx"] else None,
            "last_tx": sample_signals["last_tx"].isoformat() if sample_signals and sample_signals["last_tx"] else None,
        },
        "note": "Phase 1 uses cached label data. Real-time re-classification is Phase 2.",
    }


# ─── Routes config + payment middleware ─────────────────────────────────
x402_routes = {
    "GET /api/v1/services/:service_id/wash-detail": RouteConfig(
        accepts=_accept("$0.005"),
        description="Top 50 buyers per service with full label classification, "
                    "confidence scores, and signal-by-signal breakdown.",
        mime_type="application/json",
        extensions=declare_discovery_extension(
                output=OutputConfig(
                    example={"service": {"id": 14388}, "buyers": [], "cohort_summary": {}},
                ),
            ),
    ),
    "GET /api/v1/buyers/:address/profile": RouteConfig(
        accepts=_accept("$0.005"),
        description="Single buyer wallet's 8-label classification with confidence, "
                    "all services used, and transaction patterns.",
        mime_type="application/json",
        extensions=declare_discovery_extension(
                output=OutputConfig(
                    example={"address": "0x...", "label": "organic_user", "confidence": 0.85},
                ),
            ),
    ),
    "GET /api/v1/services/:service_id/transactions": RouteConfig(
        accepts=_accept("$0.01"),
        description="Raw 30-day transaction list for a single service, up to 5000 rows.",
        mime_type="application/json",
        extensions=declare_discovery_extension(
                output=OutputConfig(
                    example={"service": {"id": 14388}, "transactions": [], "total": 0},
                ),
            ),
    ),
    "GET /api/v1/categories/:slug/full-history": RouteConfig(
        accepts=_accept("$0.02"),
        description="365-day hourly time-series for a category: services count, "
                    "total volume, transaction count.",
        mime_type="application/json",
        extensions=declare_discovery_extension(
                output=OutputConfig(
                    example={"category": "ai_inference", "points": [], "total": 0},
                ),
            ),
    ),
    "POST /api/v1/wash/check": RouteConfig(
        accepts=_accept("$0.05"),
        description="On-demand wash analysis for any wallet or seller address.",
        mime_type="application/json",
        extensions=declare_discovery_extension(
                body_type="json",
                input={"address": "0x..."},
                input_schema={
                    "type": "object",
                    "required": ["address"],
                    "properties": {
                        "address": {"type": "string", "description": "Wallet or seller address"},
                    },
                },
                output=OutputConfig(
                    example={"address": "0x...", "label": "suspected_wash", "confidence": 0.9},
                ),
            ),
    ),
}


# Attach the x402 payment middleware. Existing free endpoints (/landing-stats,
# /services list, etc.) are NOT in this routes dict and pass through unchanged.
app.add_middleware(
    PaymentMiddlewareASGI,
    routes=x402_routes,
    server=x402_server,
)


# ─── Day 21: telegram payment notifications (rich format) ──────────────
# Single middleware. Captures the paid 200 response, increments per-IP
# stats in Redis (lifetime + daily KST counter + first_seen + total
# volume), classifies the IP via ipinfo.io with 24h cache, and sends a
# Korean-formatted Telegram alert. Background task — does not block the
# user response.
import asyncio as _asyncio_tg
import logging as _logging_tg
import re as _re_tg
import time as _time_tg
import json as _json_tg
from datetime import datetime as _dt_tg, timezone as _tz_tg, timedelta as _td_tg
import httpx as _httpx_tg
from fastapi import Request as _Request_tg
# x402watch alerts hardening — additive imports
from app._stats import write as _stats_write
from app.telegram_notify import notify_post_settle_failure as _notify_post_settle


# Quiet httpx — KR Crypto learning: URL logs sometimes carry tokens.
_logging_tg.getLogger("httpx").setLevel(_logging_tg.WARNING)
_logging_tg.getLogger("httpcore").setLevel(_logging_tg.WARNING)

_TG_BOT = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
_KST = _tz_tg(_td_tg(hours=9))

# Owner IPs are skipped from alerts and stats. Server self-IP and loopback
# are always included so curl-from-the-box smoke tests don't pollute
# counters; KR residential IPs come from OWNER_IPS_EXTRA env var (csv).
_OWNER_IPS: set[str] = {"168.138.195.65", "127.0.0.1", "::1"}
_owner_extra = os.getenv("OWNER_IPS_EXTRA", "")
for _ip in (s.strip() for s in _owner_extra.split(",")):
    if _ip:
        _OWNER_IPS.add(_ip)

_PAID_PATTERNS: list[tuple[_re_tg.Pattern[str], str, str, float]] = [
    (_re_tg.compile(r"^/api/v1/services/[^/]+/wash-detail$"),
     "GET", "/api/v1/services/{id}/wash-detail", 0.005),
    (_re_tg.compile(r"^/api/v1/buyers/[^/]+/profile$"),
     "GET", "/api/v1/buyers/{address}/profile", 0.005),
    (_re_tg.compile(r"^/api/v1/services/[^/]+/transactions$"),
     "GET", "/api/v1/services/{id}/transactions", 0.01),
    (_re_tg.compile(r"^/api/v1/categories/[^/]+/full-history$"),
     "GET", "/api/v1/categories/{slug}/full-history", 0.02),
    (_re_tg.compile(r"^/api/v1/wash/check$"),
     "POST", "/api/v1/wash/check", 0.05),
]


def _match_paid(path: str, method: str):
    for pat, m, label, price in _PAID_PATTERNS:
        if method == m and pat.match(path):
            return label, price
    return None


# Heuristic: ASN org-string keywords we treat as datacenter / hosting.
_DC_KEYWORDS = (
    "amazon", "aws", "google", "gcp", "microsoft", "azure", "oracle",
    "digital ocean", "digitalocean", "ovh", "hetzner", "linode", "vultr",
    "alibaba", "tencent", "baidu", "leaseweb", "datacenter", "data center",
    "scaleway", "fastly", "cloudflare", "akamai", "ipxo", "choopa", "contabo",
    "hosting", "server", " llc", "incapsula", "limelight", "stackpath",
)


def _classify_org(org: str) -> tuple[str, str]:
    """Return (emoji, label) — 🏢 datacenter / 🏠 residential / ❓ unknown."""
    o = (org or "").lower()
    if not o:
        return "❓", "unknown"
    if any(k in o for k in _DC_KEYWORDS):
        return "🏢", "datacenter"
    return "🏠", "residential"


async def _ipinfo(ip: str, redis_client) -> dict:
    """Fetch ipinfo.io with 24h Redis cache (free unauth tier)."""
    if not ip or ip in ("127.0.0.1", "::1", "unknown"):
        return {}
    cache_key = f"ipinfo:{ip}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return _json_tg.loads(cached)
    except Exception:
        pass
    try:
        async with _httpx_tg.AsyncClient(timeout=5) as c:
            r = await c.get(f"https://ipinfo.io/{ip}/json")
            if r.status_code == 200:
                data = r.json()
                try:
                    await redis_client.set(cache_key, _json_tg.dumps(data), ex=86400)
                except Exception:
                    pass
                return data
    except Exception as e:
        log.warning("ipinfo lookup failed for %s: %s", ip, e)
    return {}


async def _record_payment_stats(redis_client, ip: str, amount: float) -> dict:
    """Atomically bump per-IP counters; return post-increment values."""
    today_kst = _dt_tg.now(_KST).date().isoformat()
    stats_key = f"ipstats:{ip}"
    daily_field = f"daily:{today_kst}"
    daily_key = f"daily:{today_kst}"
    pipe = redis_client.pipeline()
    pipe.hincrby(stats_key, "total_count", 1)
    pipe.hincrbyfloat(stats_key, "total_volume_usd", amount)
    pipe.hincrby(stats_key, daily_field, 1)
    pipe.hsetnx(stats_key, "first_seen", _dt_tg.now(_tz_tg.utc).isoformat())
    pipe.hget(stats_key, "first_seen")
    pipe.hset(stats_key, "last_seen", _dt_tg.now(_tz_tg.utc).isoformat())
    # Per-day aggregates for the morning summary
    pipe.hincrby(daily_key, "count", 1)
    pipe.hincrbyfloat(daily_key, "revenue", amount)
    pipe.expire(daily_key, 60 * 60 * 24 * 60)  # keep 60 days
    res = await pipe.execute()
    first_seen = res[4]
    if isinstance(first_seen, bytes):
        first_seen = first_seen.decode()
    return {
        "total_count": int(res[0]),
        "total_volume": float(res[1] or 0),
        "daily_count": int(res[2]),
        "first_seen": first_seen or "",
    }


def _user_label(stats: dict) -> str:
    daily = stats["daily_count"]
    total = stats["total_count"]
    if total <= 1:
        return "🆕 신규"
    if daily <= 1:
        return "🔄 재방문"
    return f"⭐ 정기 사용 (오늘 {daily}건째)"


def _days_since(first_seen_iso: str) -> tuple[str, int]:
    if not first_seen_iso:
        return "—", 0
    try:
        first = _dt_tg.fromisoformat(first_seen_iso.replace("Z", "+00:00"))
    except Exception:
        return "—", 0
    if first.tzinfo is None:
        first = first.replace(tzinfo=_tz_tg.utc)
    first_kst = first.astimezone(_KST)
    now_kst = _dt_tg.now(_KST)
    days = (now_kst.date() - first_kst.date()).days
    return f"{first_kst.month}월 {first_kst.day}일", days


def _format_alert(endpoint: str, price_usd: float, ip: str, ipinfo: dict, stats: dict) -> str:
    org = (ipinfo.get("org") or "")
    city = ipinfo.get("city") or ""
    country = ipinfo.get("country") or ""
    emoji, kind = _classify_org(org)
    loc_parts = [p for p in (city, country) if p]
    loc = ", ".join(loc_parts) if loc_parts else "?"
    ip_line = f"{ip} {emoji} {kind} ({loc})"
    user_label = _user_label(stats)
    first_label, days = _days_since(stats["first_seen"])
    days_str = "오늘" if days == 0 else f"{days}일 전"
    now_kst = _dt_tg.now(_KST)
    return "\n".join([
        "🛡️ ━━━ x402watch ━━━",
        f"💰 결제 ${price_usd:.3f} USDC",
        "",
        f"엔드포인트: {endpoint}",
        f"IP: {ip_line}",
        f"사용자: {user_label}",
        f"누적: {stats['total_count']}건 / ${stats['total_volume']:.4f}",
        f"첫 결제: {first_label} ({days_str})",
        f"시간: {now_kst.strftime('%H:%M:%S')}",
    ])


async def _tg_send(text: str) -> None:
    """Best-effort telegram POST. Never raises into the request."""
    if not _TG_BOT or not _TG_CHAT:
        return
    try:
        async with _httpx_tg.AsyncClient(timeout=5) as c:
            await c.post(
                f"https://api.telegram.org/bot{_TG_BOT}/sendMessage",
                json={"chat_id": _TG_CHAT, "text": text},
            )
    except Exception:
        pass


def _client_ip(request: _Request_tg) -> str:
    cf = request.headers.get("cf-connecting-ip", "").strip()
    if cf:
        return cf
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    xri = request.headers.get("x-real-ip", "").strip()
    if xri:
        return xri
    return request.client.host if request.client else "unknown"


# 5-min per (endpoint, ip) dedupe — avoids spam during retry storms.
_TG_TTL_SECONDS = 300
_tg_seen: dict[str, float] = {}


@app.middleware("http")
async def payment_notify_middleware(request: _Request_tg, call_next):
    response = await call_next(request)
    matched = _match_paid(request.url.path, request.method)
    # x402watch alerts hardening — post-settle failure:
    # 5xx after X-Payment means we may have settled then failed to honour.
    if matched is not None and response.status_code >= 500 \
            and request.headers.get("x-payment"):
        _endpoint_label, _amount = matched
        _ip = _client_ip(request)
        settle_info = _decode_x_payment_response((response.headers.get("payment-response", "") or response.headers.get("x-payment-response", "")))
        _stats_write({
            "kind": "post_settle_fail",
            "endpoint": _endpoint_label,
            "status": response.status_code,
            "ip": _ip,
            "amount_usd": _amount,
            "tx_hash": settle_info["tx_hash"],
            "network": settle_info["network"],
            "buyer_wallet": settle_info["buyer_wallet"],
        })
        _asyncio_tg.create_task(_notify_post_settle(
            endpoint=_endpoint_label,
            status=response.status_code,
            ip=_ip,
            payer_wallet=settle_info["buyer_wallet"],
            tx_hash=settle_info["tx_hash"],
            amount_usd=_amount,
        ))
        return response
    if matched is None or response.status_code != 200:
        return response
    endpoint_label, amount = matched

    ip = _client_ip(request)
    dedupe_key = f"{endpoint_label}:{ip}"
    now = _time_tg.monotonic()
    if now - _tg_seen.get(dedupe_key, 0.0) < _TG_TTL_SECONDS:
        return response
    _tg_seen[dedupe_key] = now
    if len(_tg_seen) > 10000:
        cutoff = now - _TG_TTL_SECONDS
        for k in list(_tg_seen):
            if _tg_seen[k] < cutoff:
                _tg_seen.pop(k, None)

    async def _enrich_and_notify():
        try:
            # Owner shortcut: minimal ping, no stats, no enrichment.
            if ip in _OWNER_IPS:
                log.info("owner payment (no stats): %s $%s from %s",
                         endpoint_label, amount, ip)
                await _tg_send(
                    f"🛠️ x402watch owner test — ${amount:.3f} {endpoint_label}"
                )
                return
            redis_client = app.state.redis
            stats = await _record_payment_stats(redis_client, ip, amount)
            # Side-band per-day aggregates that need post-record stats.
            today_kst = _dt_tg.now(_KST).date().isoformat()
            daily_key = f"daily:{today_kst}"
            sb = redis_client.pipeline()
            sb.hincrby(daily_key, f"endpoint:{endpoint_label}", 1)
            if stats["total_count"] == 1:
                sb.sadd(f"{daily_key}:new_ips", ip)
                sb.expire(f"{daily_key}:new_ips", 60 * 60 * 24 * 60)
            await sb.execute()
            ipinfo = await _ipinfo(ip, redis_client)
            text = _format_alert(endpoint_label, amount, ip, ipinfo, stats)
            settle_info = _decode_x_payment_response((response.headers.get("payment-response", "") or response.headers.get("x-payment-response", "")))
            _stats_write({
                "kind": "payment",
                "endpoint": endpoint_label,
                "amount_usd": amount,
                "ip": ip,
                "ipinfo": ipinfo,
                "total_count": stats.get("total_count"),
                "daily_count": stats.get("daily_count"),
                "tx_hash": settle_info["tx_hash"],
                "network": settle_info["network"],
                "buyer_wallet": settle_info["buyer_wallet"],
            })
            log.info(
                "payment notification: %s $%s from %s (total=%d daily=%d)",
                endpoint_label, amount, ip,
                stats["total_count"], stats["daily_count"],
            )
            await _tg_send(text)
        except Exception as e:
            log.error("payment notify enrichment failed: %s", e)

    _asyncio_tg.create_task(_enrich_and_notify())
    return response


# PR #36 v2 — X402ResourceRewriter must wrap app from outside
# Place at the very end of the module so uvicorn loads the wrapped app.
from app.x402_meta import setup_x402_meta, X402ResourceRewriter

def _decode_x_payment_response(header_value: str) -> dict:
    """Decode the x402 `X-Payment-Response` header (base64 JSON).

    Returns ``{"tx_hash": ..., "network": ..., "buyer_wallet": ...}``.
    Every field is ``None`` on any failure (empty header, malformed
    base64, malformed JSON, ``success != True``). Defensive — never
    raises into the request path."""
    if not header_value:
        return {"tx_hash": None, "network": None, "buyer_wallet": None}
    try:
        import base64
        import json as _json
        decoded = _json.loads(base64.b64decode(header_value).decode())
        if decoded.get("success"):
            return {
                "tx_hash": decoded.get("transaction"),
                "network": decoded.get("network"),
                "buyer_wallet": decoded.get("payer"),
            }
    except Exception as _e:
        log.warning("x-payment-response decode failed: %s", _e)
    return {"tx_hash": None, "network": None, "buyer_wallet": None}

setup_x402_meta(app)
app = X402ResourceRewriter(app)
