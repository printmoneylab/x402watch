"""
MCP payment-guidance helpers for x402watch.

Permanent location on Oracle: /home/ubuntu/x402watch/app/mcp_payment_hint.py

Three pieces:

  1. `payment_required_response(...)` — build the dict that `_call_paid_api`
     returns when a paid MCP tool is invoked without payment. Contains the
     8 quick-start fields KR Crypto validated, plus an x402watch-specific
     `value_proposition` / `differentiators` block so AI agents see what
     makes this catalog different from a generic indexer.

  2. `PAID_TOOL_DOCSTRING_TEMPLATE` — copy-paste template Moa drops into
     each paid MCP tool's docstring. The four-line price block + the
     `🎯 x402watch advantage:` line gives AI agents enough context to
     decide whether to pay before reading the registry.

  3. `FREE_TOOL_TAGLINE` — single-line constant for free tools so they
     are unambiguously marked "no payment required" and don't accidentally
     confuse callers who saw the paid block on a sibling tool.

This module is pure data + tiny pure functions — no I/O, no async. Safe
to import from anywhere.
"""
from __future__ import annotations

from typing import Optional


# ─── Static catalogue (kept in sync with the facilitator + OpenAPI) ──
MERCHANT_WALLETS = {
    "Base":   "0xcF9223eCe895258dEa8D288AEBcf846Ab8E342fB",
    "Solana": "3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9",
}
SUPPORTED_NETWORKS = ["Base", "Solana"]
COMPATIBLE_CLIENTS = ["AgentCash", "Pay.sh", "x402 SDK", "Coinbase x402"]

DOCS = {
    "manifest": "https://api.x402.printmoneylab.com/.well-known/x402",
    "methodology": "https://x402.printmoneylab.com/docs/methodology",
    "x402_spec": "https://x402.org",
    "llms_txt": "https://x402.printmoneylab.com/llms.txt",
}

QUICK_START_STEPS = [
    "1. Install an x402 client (AgentCash, Pay.sh, or the official x402 SDK).",
    "2. Fund a wallet with USDC on Base or Solana mainnet (≥ price for the call).",
    "3. Replay the request with the `X-Payment: <signed-payload>` header.",
]

VALUE_PROPOSITION = (
    "Wash-filtered ecosystem intelligence layer. 4-layer algorithm with "
    "9-label buyer taxonomy. Open methodology with dispute system."
)

DIFFERENTIATORS = [
    "False-positive verified: KR Crypto kr-prices went from 96.4% suspected_wash → 0% post-v2.0.",
    "9-label taxonomy: organic_user, ai_agent, self_test, suspected_wash, owner_test, exchange_user, verifier, analytics_bot, developer.",
    "Per-(buyer, seller) labels — the same buyer can be labeled differently on different services.",
    "Open methodology — every threshold and rule published at " + DOCS["methodology"] + ".",
    "Dispute system — false positives can be reported via POST /api/disputes.",
]


# ─── 402 response builder ────────────────────────────────────────────
def payment_required_response(
    *,
    endpoint: str,
    price_usd: float,
    method: str = "GET",
    note: Optional[str] = None,
) -> dict:
    """Return the dict an MCP wrapper hands back when the underlying
    paid call returns 402. Designed for AI agents: every field they
    need to pay is right there in the response, no docs round-trip.

    Example call from `_call_paid_api`:

        if upstream_status == 402:
            return payment_required_response(
                endpoint="/api/v1/services/{id}/wash-detail",
                price_usd=0.005,
            )
    """
    body: dict = {
        "status": "payment_required",
        "x402_version": 2,
        "endpoint": endpoint,
        "method": method,
        "price": f"${price_usd:.3f} USDC",
        "networks": list(SUPPORTED_NETWORKS),
        "merchant_wallets": dict(MERCHANT_WALLETS),
        "quick_start": list(QUICK_START_STEPS),
        "compatible_clients": list(COMPATIBLE_CLIENTS),
        "documentation": dict(DOCS),
        "value_proposition": VALUE_PROPOSITION,
        "differentiators": list(DIFFERENTIATORS),
    }
    if note:
        body["note"] = note
    return body


# ─── Tool docstring templates ────────────────────────────────────────
# Drop the {core} / {price} / {returns} placeholders into each paid
# tool's docstring. The block keeps the same shape across tools so AI
# agents can pattern-match the price line cheaply.
PAID_TOOL_DOCSTRING_TEMPLATE = """\
{core}

💰 Price: ${price:.3f} USDC per call
💳 Payment: x402 micropayment on Base or Solana
🔧 Client: AgentCash, Pay.sh, or any x402 SDK
📖 Docs: https://api.x402.printmoneylab.com/.well-known/x402

🎯 x402watch advantage: Wash-filtered intelligence layer. 4-layer algorithm
   reduces false positives. Open methodology + dispute system.

{returns}
"""

FREE_TOOL_TAGLINE = (
    "Free tier. No payment required. "
    "Returns wash-filtered data using the same v2.0 algorithm as the paid endpoints."
)


def render_paid_docstring(core: str, price_usd: float, returns: str = "") -> str:
    """Convenience renderer if Moa prefers building docstrings at
    decorator time instead of pasting them by hand."""
    return PAID_TOOL_DOCSTRING_TEMPLATE.format(
        core=core.strip(),
        price=price_usd,
        returns=returns.strip(),
    )


__all__ = [
    "MERCHANT_WALLETS",
    "SUPPORTED_NETWORKS",
    "COMPATIBLE_CLIENTS",
    "DOCS",
    "QUICK_START_STEPS",
    "VALUE_PROPOSITION",
    "DIFFERENTIATORS",
    "payment_required_response",
    "render_paid_docstring",
    "PAID_TOOL_DOCSTRING_TEMPLATE",
    "FREE_TOOL_TAGLINE",
]
