"""
Catalogue of x402watch paid endpoints — single source of truth for the
five wrapper tools that should carry the paid docstring template.

Permanent location on Oracle: /home/ubuntu/x402watch/app/paid_tools_catalog.py

Used by:
  - app/mcp_server.py (wiring step F)
  - scripts/verify_wireup.py (post-apply sanity check)
  - app/mcp_payment_hint.py (indirectly — prices match the template renderer)

If pricing changes, update here once and re-render the docstrings via
render_paid_docstring(). The values must agree with PR #36 v2.2's
oracle-patches/pr36-openapi/x402_meta.py PAID_ENDPOINTS list — that
file owns the OpenAPI metadata and is the canonical wallet/asset
config; this file is a thin Python catalogue for the MCP layer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaidEndpoint:
    path: str             # FastAPI path template, e.g. "/api/v1/services/{id}/wash-detail"
    method: str           # "GET" or "POST"
    price_usd: float      # USDC price per call (e.g. 0.005)
    summary: str          # one-line description for the docstring `core` slot
    returns: str          # one-line description for the docstring `returns` slot


# Order matches the OpenAPI catalog in PR #36 v2.2. Keep in sync.
PAID_ENDPOINTS: list[PaidEndpoint] = [
    PaidEndpoint(
        path="/api/v1/services/{id}/wash-detail",
        method="GET",
        price_usd=0.005,
        summary=(
            "Top 50 buyers for a service with full label classification, "
            "confidence scores, and signal-by-signal breakdown."
        ),
        returns="Returns service + buyers[] (label, confidence, reason, tx, volume) + cohort_summary.",
    ),
    PaidEndpoint(
        path="/api/v1/services/{id}/transactions",
        method="GET",
        price_usd=0.010,
        summary="Full transaction history for a service, paginated by time.",
        returns="Returns service + transactions[] (time, buyer, amount, label) + pagination.",
    ),
    PaidEndpoint(
        path="/api/v1/categories/{cat}/full-history",
        method="GET",
        price_usd=0.020,
        summary="Full daily time-series and label distribution for a category.",
        returns="Returns category + time_series[] + label_distribution + top_services.",
    ),
    PaidEndpoint(
        path="/api/v1/wash/check",
        method="POST",
        price_usd=0.050,
        summary="On-demand wash-filter evaluation of an arbitrary (buyer, seller) pair.",
        returns="Returns label + confidence + reason + matched_signals[].",
    ),
    PaidEndpoint(
        path="/api/v1/buyers/{address}/profile",
        method="GET",
        price_usd=0.005,
        summary="Global label + per-pair breakdown + dispute count for a buyer wallet.",
        returns="Returns buyer + global_label + per_seller[] + disputes_summary.",
    ),
]


def find_by_path(path: str, method: str = "GET") -> PaidEndpoint | None:
    """Look up a paid endpoint by its FastAPI path template + method."""
    method = method.upper()
    for ep in PAID_ENDPOINTS:
        if ep.path == path and ep.method == method:
            return ep
    return None


def is_paid(path: str, method: str = "GET") -> bool:
    return find_by_path(path, method) is not None


__all__ = ["PaidEndpoint", "PAID_ENDPOINTS", "find_by_path", "is_paid"]
