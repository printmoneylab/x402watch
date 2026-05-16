"""
PR #36 reviewer-feedback patch for x402watch Oracle FastAPI.

Permanent location: /home/ubuntu/x402watch/app/x402_meta.py

Drop-in module that fixes three things flagged by Tate Lyman during
the solana-foundation/pay-skills PR #36 audit:

  1. /openapi.json now declares every paid x402 endpoint with an
     x-payment-info block + 402 response, plus info.x-guidance and
     top-level x-discovery. Free routes get an explicit `security: []`
     so OpenAPI-first agents can tell paid from free at a glance.

  2. Every 402 challenge now repeats `resource` and `extra.resource`
     inside each accepts[] entry (mirroring KR Crypto PR #35 pattern).
     Currently the resource only lives at the top level of the
     payment-required header; this middleware re-encodes the header so
     accepts[i].resource == top-level resource.url and also writes the
     full challenge JSON into the response body (currently empty `{}`)
     for clients that expect body parity with the header.

  3. POST /api/v1/wash/check OPTIONS preflight now responds 204 with
     `Access-Control-Allow-Methods: GET, POST, OPTIONS`. The existing
     CORSMiddleware sets allow_methods=["GET"], which 400s a POST
     preflight; this module's `X402PreflightMiddleware` short-circuits
     OPTIONS for the paid endpoints with the full method list before
     CORSMiddleware sees it.

Wireup from app/api.py — three lines:

    from app.x402_meta import setup_x402_meta
    # ... after FastAPI(...) is constructed and routes are mounted ...
    setup_x402_meta(app)

`setup_x402_meta` is idempotent — calling it twice is a no-op.

Environment / config: nothing new. Reuses the existing payTo wallets
and asset choices already configured in the x402 facilitator.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Iterable, Optional

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

log = logging.getLogger("x402_meta")


# ─── Paid endpoint catalogue ─────────────────────────────────────────
# Mirrors the live x402 facilitator config. Keep in sync if pricing or
# routes change. Method matters for OpenAPI x-payment-info (so a buyer
# profile GET and a wash/check POST get tagged on their own operation
# object, not on a sibling path's operation).
PAID_ENDPOINTS: list[dict[str, Any]] = [
    {
        "path": "/api/v1/services/{id}/wash-detail",
        "method": "get",
        "amount": "5000",       # 0.005 USDC, 6 decimals
        "price_usd": "0.005",
        "description": "Top 50 buyers per service with full label classification, "
                       "confidence scores, and signal-by-signal breakdown.",
    },
    {
        "path": "/api/v1/services/{id}/transactions",
        "method": "get",
        "amount": "10000",
        "price_usd": "0.010",
        "description": "Full transaction history for a service (paginated).",
    },
    {
        "path": "/api/v1/categories/{cat}/full-history",
        "method": "get",
        "amount": "20000",
        "price_usd": "0.020",
        "description": "Full daily time-series and label distribution for a category.",
    },
    {
        "path": "/api/v1/wash/check",
        "method": "post",
        "amount": "50000",
        "price_usd": "0.050",
        "description": "Submit an arbitrary buyer/seller pair for an on-demand "
                       "wash-filter evaluation. Returns label + confidence + reason.",
    },
    {
        "path": "/api/v1/buyers/{address}/profile",
        "method": "get",
        "amount": "5000",
        "price_usd": "0.005",
        "description": "Global label + per-pair breakdown + dispute count for a buyer wallet.",
    },
]

PAID_PATH_METHODS = {(p["path"], p["method"]) for p in PAID_ENDPOINTS}

# Accepts entries reused for both the 402 challenge and OpenAPI
# x-payment-info. The actual values must match what the x402 facilitator
# emits at runtime — if Moa ever rotates the payTo addresses or the
# USDC contract address, update these once here.
ACCEPTS_TEMPLATE: list[dict[str, Any]] = [
    {
        "scheme": "exact",
        "network": "eip155:8453",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
        "payTo": "0xcF9223eCe895258dEa8D288AEBcf846Ab8E342fB",
        "maxTimeoutSeconds": 300,
        "extra": {"name": "USD Coin", "version": "2"},
    },
    {
        "scheme": "exact",
        "network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
        "asset": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC on Solana
        "payTo": "3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9",
        "maxTimeoutSeconds": 300,
        "extra": {"feePayer": "BENrLoUbndxoNMUS5JXApGMtNykLjFXXixMtpDwDR9SP"},
    },
]


# ─── Custom OpenAPI generator ────────────────────────────────────────
def _build_x_payment_info(amount: str, resource_path_template: str) -> dict[str, Any]:
    """One x-payment-info block to attach to a paid operation. We embed
    a `accepts` array shaped like the runtime 402 challenge so an
    OpenAPI-first client can re-use the same parser for both."""
    accepts = []
    for tmpl in ACCEPTS_TEMPLATE:
        entry = dict(tmpl)
        entry["amount"] = amount
        # OpenAPI examples use the path template so it's clear this is
        # a per-route value the client will substitute.
        entry["resource"] = f"https://api.x402.printmoneylab.com{resource_path_template}"
        entry["extra"] = dict(entry["extra"]) | {"resource": entry["resource"]}
        accepts.append(entry)
    return {
        "required": True,
        "x402Version": 2,
        "scheme": "exact",
        "accepts": accepts,
    }


def custom_openapi_factory(app: FastAPI):
    """Returns the function FastAPI calls to lazily build /openapi.json.
    Caches into app.openapi_schema after the first build."""

    def custom_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )

        # info.x-guidance — short hint for OpenAPI-first agents on how
        # to interpret paid vs free routes.
        info = schema.setdefault("info", {})
        info["x-guidance"] = (
            "Endpoints with `x-payment-info` require an x402 payment. "
            "Send an empty request to receive a 402 with a `payment-required` "
            "header; complete payment via the x402 facilitator; replay the "
            "request with `X-Payment: <signed-payload>`. Endpoints with "
            "`security: []` are free."
        )

        # x-discovery — top-level pointer for catalogue crawlers.
        schema["x-discovery"] = {
            "publisher": "PrintMoneyLab",
            "site": "https://x402.printmoneylab.com",
            "x402Version": 2,
            "ownershipProofs": [
                {
                    "platform": "github",
                    "url": "https://github.com/printmoneylab/x402watch",
                },
                {
                    "platform": "twitter",
                    "url": "https://twitter.com/printmoneylab",
                },
            ],
            "paymentNetworks": ["eip155:8453", "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"],
        }

        # Per-endpoint annotations.
        paths = schema.setdefault("paths", {})
        for spec in PAID_ENDPOINTS:
            path, method = spec["path"], spec["method"]
            ops = paths.setdefault(path, {})
            op = ops.setdefault(method, {})
            # Tag, summary, description if not already present.
            op.setdefault("summary", spec["description"][:60])
            op.setdefault("description", spec["description"])
            op["x-payment-info"] = _build_x_payment_info(spec["amount"], path)
            responses = op.setdefault("responses", {})
            responses["402"] = {
                "description": "Payment required. Body and `payment-required` "
                               "header contain the x402 challenge.",
                "headers": {
                    "payment-required": {
                        "description": "Base64-encoded JSON x402 challenge.",
                        "schema": {"type": "string"},
                    }
                },
                "content": {"application/json": {"schema": {"type": "object"}}},
            }
            # security: leave as-is (or undefined) — the x-payment-info
            # block is the canonical payment marker.

        # Free routes get an explicit `security: []` so OpenAPI-first
        # agents distinguish "no auth needed" from "missing metadata".
        for path, ops in paths.items():
            for method, op in (ops or {}).items():
                if not isinstance(op, dict):
                    continue
                if (path, method) in PAID_PATH_METHODS:
                    continue
                op.setdefault("security", [])

        app.openapi_schema = schema
        return schema

    return custom_openapi


# ─── Middleware: POST-aware preflight + accepts.resource injection ───
ALLOWED_ORIGIN_DEFAULT = "*"
ALLOWED_HEADERS_DEFAULT = "Content-Type, X-Payment, Authorization"
ALLOWED_METHODS = "GET, POST, OPTIONS"
PREFLIGHT_MAX_AGE = "86400"


class X402PreflightMiddleware(BaseHTTPMiddleware):
    """Handles OPTIONS preflight for paid endpoints with the full method
    list. The existing CORSMiddleware can keep its narrower allow_methods
    for everything else — this middleware sits in front of it and
    short-circuits the OPTIONS for paid routes only."""

    def __init__(self, app, paid_paths: Iterable[str] = (p["path"] for p in PAID_ENDPOINTS)):
        super().__init__(app)
        # Convert {id}/{cat}/{address} templates into prefix matches:
        # /api/v1/services/{id}/wash-detail → ("/api/v1/services/", "/wash-detail")
        self._tpl_segments = [self._split_template(p) for p in paid_paths]

    @staticmethod
    def _split_template(path: str) -> tuple[str, ...]:
        """Returns the static segments around every `{param}` placeholder."""
        out: list[str] = []
        cur = ""
        in_param = False
        for ch in path:
            if ch == "{":
                if cur:
                    out.append(cur)
                cur = ""
                in_param = True
            elif ch == "}":
                in_param = False
            elif not in_param:
                cur += ch
        if cur:
            out.append(cur)
        return tuple(out)

    def _matches_paid(self, request_path: str) -> bool:
        for segments in self._tpl_segments:
            pos = 0
            ok = True
            for i, seg in enumerate(segments):
                idx = request_path.find(seg, pos)
                if idx == -1:
                    ok = False
                    break
                if i == 0 and idx != 0:
                    ok = False
                    break
                pos = idx + len(seg)
            # Last segment must end the path (no trailing /something_else).
            if ok and pos == len(request_path):
                return True
        return False

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" and self._matches_paid(request.url.path):
            origin = request.headers.get("origin", ALLOWED_ORIGIN_DEFAULT)
            req_headers = request.headers.get(
                "access-control-request-headers", ALLOWED_HEADERS_DEFAULT
            )
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Vary": "Origin",
                    "Access-Control-Allow-Methods": ALLOWED_METHODS,
                    "Access-Control-Allow-Headers": req_headers,
                    "Access-Control-Max-Age": PREFLIGHT_MAX_AGE,
                },
            )
        return await call_next(request)


REWRITER_VERSION = "v2.2"

# CORS headers attached to 402 responses so browser clients can read
# the body and the payment-required header. The facilitator emits 402s
# outside the FastAPI user-middleware chain, so the existing
# CORSMiddleware never gets to inject these — we have to do it here.
ACAO_EXPOSE_HEADERS = "payment-required, x-x402-rewriter"


class X402ResourceRewriter:
    """Pure ASGI middleware that rewrites every 402 response so each
    accepts[i] entry repeats the top-level resource URL in both
    `resource` and `extra.resource`, and the body mirrors the
    payment-required header.

    The previous attempt used a Starlette `BaseHTTPMiddleware` and
    didn't fire on production 402s — most likely because the x402
    facilitator emits the 402 from a position outside our user-
    middleware chain, so the response is finalised before `dispatch()`
    is reached on the unwind. `BaseHTTPMiddleware` is also known to
    have edge cases with buffered/streaming responses where the body
    iterator is consumed before the dispatcher sees it.

    A pure ASGI middleware wrapped around `app` from the outside
    (`app = X402ResourceRewriter(app)`) is guaranteed to sit outside
    every other piece of the stack — facilitator middleware, CORS
    middleware, exception handlers, and anything else — so it always
    sees the final outgoing response.

    Adds `X-X402-Rewriter: v2.2` to every response it touches so the
    wiring can be verified in two seconds with `curl -I`.

    v2.2: on 402 responses, also injects the CORS triple browsers need
    to actually read the body and the `payment-required` header —
    Access-Control-Allow-Origin (echoes the request Origin), Vary:
    Origin, Access-Control-Expose-Headers. The existing CORSMiddleware
    handles 2xx fine but never sees 402s because the facilitator emits
    them outside the user-middleware chain.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        # Capture request Origin so we can echo it back on the 402.
        request_origin: Optional[bytes] = None
        for name, value in scope.get("headers") or []:
            if name.lower() == b"origin":
                request_origin = value
                break

        # Per-request state. We only intercept (buffer the body) when
        # the response is a 402; everything else streams through.
        state = {
            "start": None,
            "intercept": False,
            "body_chunks": [],
            "tracer_sent": False,
            "origin": request_origin,
        }

        async def send_wrapper(message):
            mtype = message.get("type")

            if mtype == "http.response.start":
                state["start"] = message
                state["intercept"] = message.get("status") == 402
                if not state["intercept"]:
                    # Add tracer header to everything so we can prove
                    # the rewriter is in the chain even on 200s.
                    headers = list(message.get("headers") or [])
                    headers.append((b"x-x402-rewriter", REWRITER_VERSION.encode()))
                    new_msg = dict(message)
                    new_msg["headers"] = headers
                    await send(new_msg)
                # If intercepting we hold the start message until the
                # body is fully buffered, since we need to recompute
                # content-length and possibly amend headers.

            elif mtype == "http.response.body":
                if state["intercept"]:
                    state["body_chunks"].append(message.get("body", b""))
                    if not message.get("more_body", False):
                        await self._rewrite_and_send(state, send)
                else:
                    await send(message)

            else:
                # Other message types (rare on HTTP): pass through.
                await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    def _inject_cors(headers: list, origin: Optional[bytes]) -> list:
        """Append the CORS triple browsers need to read a 402 body +
        the payment-required header. Idempotent — drops any existing
        Access-Control-Allow-Origin / Expose-Headers so we don't
        duplicate when an inner middleware also set them."""
        kept = []
        seen_vary = None
        for name, value in headers:
            lower = name.lower()
            if lower in (b"access-control-allow-origin",
                         b"access-control-expose-headers"):
                continue
            if lower == b"vary":
                seen_vary = value
                continue
            kept.append((name, value))
        # Echo Origin when present (safer than wildcarding with
        # potentially credentialed requests). Fall back to "*" so
        # non-browser tools still see a permissive header for testing.
        acao = origin if origin else b"*"
        kept.append((b"access-control-allow-origin", acao))
        kept.append((b"access-control-expose-headers",
                     ACAO_EXPOSE_HEADERS.encode("ascii")))
        # Preserve / extend Vary so caches respect the per-Origin
        # variation we just introduced.
        vary_parts = []
        if seen_vary:
            for part in seen_vary.split(b","):
                p = part.strip()
                if p and p.lower() != b"origin":
                    vary_parts.append(p)
        vary_parts.append(b"Origin")
        kept.append((b"vary", b", ".join(vary_parts)))
        return kept

    async def _rewrite_and_send(self, state, send):
        start = state["start"] or {}
        headers = list(start.get("headers") or [])
        body_bytes = b"".join(state["body_chunks"])
        origin = state.get("origin")

        pr_value: Optional[bytes] = None
        for name, value in headers:
            if name.lower() == b"payment-required":
                pr_value = value
                break

        challenge: Optional[dict] = None
        if pr_value is not None:
            try:
                challenge = json.loads(base64.b64decode(pr_value))
            except Exception:
                log.exception("could not decode payment-required header")
                challenge = None

        # If no usable challenge in the header, also try to pull one
        # from the body — some facilitators put the JSON there only.
        if challenge is None and body_bytes:
            try:
                maybe = json.loads(body_bytes)
                if isinstance(maybe, dict) and isinstance(maybe.get("accepts"), list):
                    challenge = maybe
            except Exception:
                pass

        if challenge is None:
            # Nothing to patch in the body, but we still need CORS on
            # the 402 so browsers can read whatever IS there.
            new_headers = self._inject_cors(headers, origin)
            new_headers.append((b"x-x402-rewriter", f"{REWRITER_VERSION}-noop".encode()))
            await send({**start, "headers": new_headers})
            await send({"type": "http.response.body", "body": body_bytes, "more_body": False})
            return

        # Patch accepts entries.
        resource_url = (challenge.get("resource") or {}).get("url")
        if resource_url and isinstance(challenge.get("accepts"), list):
            for entry in challenge["accepts"]:
                if not isinstance(entry, dict):
                    continue
                entry["resource"] = resource_url
                extra = entry.get("extra")
                if not isinstance(extra, dict):
                    extra = {}
                extra["resource"] = resource_url
                entry["extra"] = extra

        new_header_value = base64.b64encode(
            json.dumps(challenge, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").encode("ascii")

        new_body = json.dumps(challenge, separators=(",", ":")).encode("utf-8")

        # Rebuild headers: drop payment-required + content-length,
        # then add the patched versions + CORS triple + tracer.
        new_headers = []
        for name, value in headers:
            lower = name.lower()
            if lower == b"payment-required" or lower == b"content-length":
                continue
            new_headers.append((name, value))
        new_headers.append((b"payment-required", new_header_value))
        new_headers.append((b"content-length", str(len(new_body)).encode("ascii")))
        new_headers = self._inject_cors(new_headers, origin)
        new_headers.append((b"x-x402-rewriter", REWRITER_VERSION.encode()))

        await send({**start, "headers": new_headers})
        await send({"type": "http.response.body", "body": new_body, "more_body": False})


# ─── Wireup ──────────────────────────────────────────────────────────
def setup_x402_meta(app: FastAPI) -> None:
    """Mount the OpenAPI factory + preflight middleware on the FastAPI
    app. Idempotent. Does NOT mount the 402 response rewriter — that
    needs to wrap `app` from the outside (see `wrap_with_rewriter` or
    just do `app = X402ResourceRewriter(app)` at the very end of api.py).
    """
    if getattr(app.state, "_x402_meta_installed", False):
        log.info("x402_meta already installed, skipping")
        return
    app.add_middleware(X402PreflightMiddleware)
    app.openapi = custom_openapi_factory(app)
    app.state._x402_meta_installed = True
    log.info(
        "x402_meta installed: %d paid endpoints, %d accepts entries (rewriter mounted separately)",
        len(PAID_ENDPOINTS),
        len(ACCEPTS_TEMPLATE),
    )


def wrap_with_rewriter(app):
    """Convenience: returns the app wrapped in `X402ResourceRewriter`.
    Equivalent to `app = X402ResourceRewriter(app)` — exists so callers
    can do `app = wrap_with_rewriter(app)` for readability."""
    return X402ResourceRewriter(app)
