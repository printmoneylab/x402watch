#!/usr/bin/env python3
"""
P3 fix — add tx_hash + network + buyer_wallet to stats.jsonl payment +
post_settle_fail events by decoding the x402 `X-Payment-Response`
header.

What it changes (app/api.py only)
=================================
1. Inserts a module-level helper `_decode_x_payment_response(header)`
   right after the last top-level import. Helper is defensive: base64
   + json decoded with try/except, success-flag checked, all fields
   default to None on any failure. Lazy imports inside the function so
   we don't touch the module's import block.
2. For the unique `_stats_write({"kind": "payment", ...})` Call:
     - Inserts a `settle_info = _decode_x_payment_response(
       response.headers.get("x-payment-response", ""))` line
       immediately before the call (matching its indent).
     - Adds three new keys to the Dict literal before its close brace:
       `tx_hash`, `network`, `buyer_wallet`, each referencing
       `settle_info["..."]`.
3. For the unique `_stats_write({"kind": "post_settle_fail", ...})`
   Call: same two edits.
4. For the unique `_notify_post_settle(...)` Call sitting in the
   same enclosing function as #3: rewrites the two hardcoded
   `tx_hash=None` and `payer_wallet=None` kwargs to reference
   `settle_info["tx_hash"]` and `settle_info["buyer_wallet"]`.

Why structural anchors instead of verbatim strings
==================================================
Oracle's `/home/ubuntu/x402watch/app/api.py` is not in the local git
repo (SCP-operated). The prior MCP-side patchers had a canonical
`apply_mcp_ctx.py` to lift verbatim anchors from; api.py has no such
local source. Verbatim anchors would either guess at indent/wrap or
ask Moa to paste 100+ lines. Structural matching via `ast.walk`
keying on `_stats_write` + `Dict["kind"] == "payment"|"post_settle_fail"`
is unambiguous (the spec confirms exactly one of each) and tolerant
to whitespace.

Idempotency
===========
- helper already defined as a module-level FunctionDef     → skip step 1
- payment Dict already has key "tx_hash"                    → skip step 2
- post_settle_fail Dict already has key "tx_hash"           → skip step 3
- _notify_post_settle kwargs already non-None for both args → skip step 4
- partial state (one of the above patched, others not)      → abort
  with a clear message rather than leaving the file mid-state

AST-parse gate on the final output. KST-tagged backup. Dry-run by
default; `--apply` to write. `--self-test` runs against a synthetic
fixture (no Oracle file needed) and prints the resulting diff.

Usage
=====
  venv/bin/python scripts/add_tx_hash_to_payment.py
  venv/bin/python scripts/add_tx_hash_to_payment.py --apply
  venv/bin/python scripts/add_tx_hash_to_payment.py --self-test
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import shutil
import sys
from pathlib import Path
from typing import Optional

ROOT = Path("/home/ubuntu/x402watch")
TARGET = ROOT / "app" / "api.py"

HELPER_NAME = "_decode_x_payment_response"

HELPER_BLOCK_WITH_LOG = '''\

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

'''

HELPER_BLOCK_WITHOUT_LOG = '''\

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
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "x-payment-response decode failed", exc_info=True
        )
    return {"tx_hash": None, "network": None, "buyer_wallet": None}

'''

SETTLE_INFO_EXPR = (
    '_decode_x_payment_response(response.headers.get("x-payment-response", ""))'
)
SETTLE_INFO_ASSIGN = f'settle_info = {SETTLE_INFO_EXPR}'


# ─── helpers ─────────────────────────────────────────────────────────
def _die(msg: str, code: int = 2) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(code)


def _kst_tag() -> str:
    now_utc = dt.datetime.utcnow()
    kst = now_utc + dt.timedelta(hours=9)
    return kst.strftime("%Y%m%d-%H%M")


def _line_offsets(source: str) -> list[int]:
    """offsets[i] = char offset where line (i+1) starts (1-indexed lines)."""
    offsets = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _pos(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def _module_has_name(tree: ast.Module, name: str) -> bool:
    """True if `name` is bound at module level by Assign / AnnAssign / Import."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound == name:
                    return True
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                if bound == name:
                    return True
    return False


def _module_has_helper(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == HELPER_NAME:
                return True
    return False


def _find_stats_write_calls(
    tree: ast.Module, kind: str
) -> list[tuple[ast.Call, ast.Dict]]:
    """All `_stats_write({"kind": kind, ...})` calls."""
    out: list[tuple[ast.Call, ast.Dict]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_stats_write"
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Dict)
        ):
            continue
        d = node.args[0]
        for k, v in zip(d.keys, d.values):
            if (
                isinstance(k, ast.Constant)
                and k.value == "kind"
                and isinstance(v, ast.Constant)
                and v.value == kind
            ):
                out.append((node, d))
                break
    return out


_POST_SETTLE_CALL_NAMES = ("_notify_post_settle", "notify_post_settle_failure")


def _find_notify_post_settle_calls(tree: ast.Module) -> list[ast.Call]:
    """All post-settle-failure notifier Calls.

    api.py may call the function by its local alias (`_notify_post_settle`)
    or by the canonical name exported from telegram_notify
    (`notify_post_settle_failure`). Match either, by Name *or* by
    Attribute access (e.g. `telegram_notify.notify_post_settle_failure`).
    Calls inside the helper-insertion target file's own def (i.e. inside
    a FunctionDef whose name matches) are excluded so the patcher only
    sees call-sites, not the definition itself."""
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name: Optional[str] = None
        if isinstance(f, ast.Name):
            name = f.id
        elif isinstance(f, ast.Attribute):
            name = f.attr
        if name in _POST_SETTLE_CALL_NAMES:
            # Must have BOTH tx_hash and payer_wallet kwargs — that's
            # what makes it the call we want to rewrite. Filters out
            # any unrelated call that happens to share the name.
            kw_names = {kw.arg for kw in node.keywords if kw.arg}
            if "tx_hash" in kw_names and "payer_wallet" in kw_names:
                out.append(node)
    return out


def _enclosing_func(tree: ast.Module, node: ast.AST):
    """Return the innermost FunctionDef/AsyncFunctionDef enclosing `node`,
    via line-range containment. Falls back to None for module-level."""
    candidates: list = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                n.lineno <= node.lineno
                and (n.end_lineno or n.lineno) >= (node.end_lineno or node.lineno)
            ):
                candidates.append(n)
    if not candidates:
        return None
    # innermost = largest lineno (deepest start)
    return max(candidates, key=lambda n: n.lineno)


def _dict_has_key(d: ast.Dict, key_name: str) -> bool:
    for k in d.keys:
        if isinstance(k, ast.Constant) and k.value == key_name:
            return True
    return False


def _last_import_end_offset(tree: ast.Module, offsets: list[int]) -> int:
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            end = _pos(offsets, node.end_lineno, node.end_col_offset)
            if end > last:
                last = end
    return last


def _line_indent(source: str, line_start: int) -> str:
    indent = ""
    i = line_start
    while i < len(source) and source[i] in " \t":
        indent += source[i]
        i += 1
    return indent


# ─── per-step edits ──────────────────────────────────────────────────
class Edit:
    """A single insertion/replacement. Applied in reverse offset order."""

    __slots__ = ("start", "end", "text", "label")

    def __init__(self, start: int, end: int, text: str, label: str):
        self.start = start
        self.end = end
        self.text = text
        self.label = label


def _build_dict_extension(indent_spaces: str) -> str:
    return (
        f'{indent_spaces}"tx_hash": settle_info["tx_hash"],\n'
        f'{indent_spaces}"network": settle_info["network"],\n'
        f'{indent_spaces}"buyer_wallet": settle_info["buyer_wallet"],\n'
    )


def _edits_for_stats_write(
    source: str, offsets: list[int], call: ast.Call, d: ast.Dict, label: str
) -> list[Edit]:
    """Return edits for ONE _stats_write call:
      - insert `settle_info = …` line before the call
      - insert 3 keys before the dict's `}`
    Aborts if the dict is single-line."""
    edits: list[Edit] = []

    # 1) settle_info assign before the call line
    call_pos = _pos(offsets, call.lineno, call.col_offset)
    line_start = source.rfind("\n", 0, call_pos) + 1
    call_indent = source[line_start:call_pos]
    if any(ch not in " \t" for ch in call_indent):
        raise RuntimeError(
            f"{label}: _stats_write call is not at line start — abort"
        )
    edits.append(
        Edit(
            line_start,
            line_start,
            f"{call_indent}{SETTLE_INFO_ASSIGN}\n",
            f"{label}: insert settle_info assign",
        )
    )

    # 2) three keys before the dict's `}`
    # Locate the `}` precisely from AST end position.
    dict_end = _pos(offsets, d.end_lineno, d.end_col_offset)
    brace_pos = dict_end - 1
    while brace_pos >= 0 and source[brace_pos] != "}":
        brace_pos -= 1
    if brace_pos < 0:
        raise RuntimeError(f"{label}: could not locate dict close brace")

    # Last value end
    if not d.values:
        raise RuntimeError(f"{label}: empty dict — refuse to patch")
    last_val = d.values[-1]
    if last_val is None:
        raise RuntimeError(f"{label}: dict has ** unpack at end — abort")
    last_val_end = _pos(offsets, last_val.end_lineno, last_val.end_col_offset)

    # Single-line vs multi-line detection
    brace_line_start = source.rfind("\n", 0, brace_pos) + 1
    last_val_line_start = source.rfind("\n", 0, last_val_end) + 1
    if brace_line_start <= last_val_line_start:
        raise RuntimeError(
            f"{label}: single-line dict literal — patcher does not handle "
            "this case. Reformat to multi-line or paste the snippet."
        )

    # Indent for new keys = column of the LAST existing key
    last_key = d.keys[-1]
    if last_key is None:
        raise RuntimeError(f"{label}: dict has ** unpack at end — abort")
    key_indent = " " * last_key.col_offset

    # Trailing comma after last value?
    between = source[last_val_end:brace_pos]
    has_trailing_comma = "," in between

    if not has_trailing_comma:
        edits.append(
            Edit(
                last_val_end,
                last_val_end,
                ",",
                f"{label}: trailing comma on last existing key",
            )
        )

    edits.append(
        Edit(
            brace_line_start,
            brace_line_start,
            _build_dict_extension(key_indent),
            f"{label}: insert 3 new keys before }}",
        )
    )
    return edits


def _edits_for_notify_post_settle(
    source: str, offsets: list[int], call: ast.Call
) -> list[Edit]:
    """Rewrite `tx_hash=None` → `tx_hash=settle_info["tx_hash"]` and
    `payer_wallet=None` → `payer_wallet=settle_info["buyer_wallet"]`."""
    mapping = {
        "tx_hash": 'settle_info["tx_hash"]',
        "payer_wallet": 'settle_info["buyer_wallet"]',
    }
    edits: list[Edit] = []
    seen: set[str] = set()
    for kw in call.keywords:
        if kw.arg not in mapping:
            continue
        seen.add(kw.arg)
        v = kw.value
        if isinstance(v, ast.Constant) and v.value is None:
            start = _pos(offsets, v.lineno, v.col_offset)
            end = _pos(offsets, v.end_lineno, v.end_col_offset)
            edits.append(
                Edit(start, end, mapping[kw.arg], f"_notify_post_settle: {kw.arg}=…")
            )
        elif isinstance(v, ast.Subscript):
            # already patched — skip silently (handled by global idempotency)
            continue
        else:
            raise RuntimeError(
                f"_notify_post_settle.{kw.arg} has unexpected value type "
                f"{type(v).__name__} — abort"
            )
    missing = set(mapping) - seen
    if missing:
        raise RuntimeError(
            f"_notify_post_settle is missing expected kwargs: {sorted(missing)}"
        )
    return edits


# ─── orchestrator ────────────────────────────────────────────────────
def plan_edits(source: str, *, verbose: bool = True) -> tuple[list[Edit], list[str]]:
    """Returns (edits, notes). Notes are printed in dry-run / apply."""
    tree = ast.parse(source)
    offsets = _line_offsets(source)
    notes: list[str] = []
    edits: list[Edit] = []

    # ── Step 1: helper ────────────────────────────────────────────────
    helper_present = _module_has_helper(tree)
    if helper_present:
        notes.append(f"◌ helper {HELPER_NAME} already present — keep")
    else:
        has_log = _module_has_name(tree, "log")
        block = HELPER_BLOCK_WITH_LOG if has_log else HELPER_BLOCK_WITHOUT_LOG
        last_imp_end = _last_import_end_offset(tree, offsets)
        if last_imp_end == 0:
            _die("no module-level imports found — refuse (file shape unexpected)")
        # Insert at the start of the next line after last import line
        nl = source.find("\n", last_imp_end)
        insertion_point = (nl + 1) if nl >= 0 else len(source)
        edits.append(
            Edit(insertion_point, insertion_point, block,
                 f"insert helper {HELPER_NAME} (log {'available' if has_log else 'fallback'})")
        )
        notes.append(
            f"✓ insert helper {HELPER_NAME} "
            f"({'with log.warning' if has_log else 'with logging.getLogger fallback'})"
        )

    # ── Step 2 / 3: _stats_write payment / post_settle_fail ──────────
    pay_calls = _find_stats_write_calls(tree, "payment")
    pof_calls = _find_stats_write_calls(tree, "post_settle_fail")

    if len(pay_calls) != 1:
        _die(
            f"_stats_write({{'kind': 'payment'}}): expected exactly 1 site, "
            f"found {len(pay_calls)} — abort"
        )
    if len(pof_calls) != 1:
        _die(
            f"_stats_write({{'kind': 'post_settle_fail'}}): expected exactly 1 "
            f"site, found {len(pof_calls)} — abort"
        )

    pay_call, pay_dict = pay_calls[0]
    pof_call, pof_dict = pof_calls[0]

    pay_patched = _dict_has_key(pay_dict, "tx_hash")
    pof_patched = _dict_has_key(pof_dict, "tx_hash")

    if pay_patched:
        notes.append(f'◌ payment _stats_write at line {pay_call.lineno} '
                     'already has tx_hash — keep')
    else:
        edits.extend(
            _edits_for_stats_write(source, offsets, pay_call, pay_dict, "payment")
        )
        notes.append(
            f'✓ payment _stats_write at line {pay_call.lineno}: '
            "insert settle_info + tx_hash/network/buyer_wallet keys"
        )

    if pof_patched:
        notes.append(f'◌ post_settle_fail _stats_write at line {pof_call.lineno} '
                     'already has tx_hash — keep')
    else:
        edits.extend(
            _edits_for_stats_write(
                source, offsets, pof_call, pof_dict, "post_settle_fail"
            )
        )
        notes.append(
            f'✓ post_settle_fail _stats_write at line {pof_call.lineno}: '
            "insert settle_info + tx_hash/network/buyer_wallet keys"
        )

    # ── Step 4: _notify_post_settle ──────────────────────────────────
    nps_calls = _find_notify_post_settle_calls(tree)
    if len(nps_calls) != 1:
        _die(
            f"_notify_post_settle: expected exactly 1 site, "
            f"found {len(nps_calls)} — abort"
        )
    nps_call = nps_calls[0]

    # Must sit inside the same enclosing function as the post_settle_fail
    # _stats_write — otherwise our `settle_info` won't be in scope.
    pof_fn = _enclosing_func(tree, pof_call)
    nps_fn = _enclosing_func(tree, nps_call)
    if pof_fn is None or nps_fn is None or pof_fn is not nps_fn:
        _die(
            "_notify_post_settle is not in the same enclosing function as the "
            "post_settle_fail _stats_write — refuse (settle_info scope unsafe)"
        )

    # Idempotency for nps: both kwargs already non-None?
    nps_state = {}
    for kw in nps_call.keywords:
        if kw.arg in ("tx_hash", "payer_wallet"):
            nps_state[kw.arg] = isinstance(kw.value, ast.Constant) and kw.value.value is None

    if nps_state.get("tx_hash") is False and nps_state.get("payer_wallet") is False:
        notes.append(
            f"◌ _notify_post_settle at line {nps_call.lineno} kwargs already "
            "non-None — keep"
        )
    elif nps_state.get("tx_hash") is True and nps_state.get("payer_wallet") is True:
        edits.extend(_edits_for_notify_post_settle(source, offsets, nps_call))
        notes.append(
            f"✓ _notify_post_settle at line {nps_call.lineno}: "
            "tx_hash + payer_wallet rewritten to settle_info[…]"
        )
    else:
        _die(
            "_notify_post_settle is in mid-state (one kwarg patched, one not). "
            "Inspect manually and restore from backup if needed."
        )

    # Global mid-state guard: if helper exists but neither dict patched,
    # OR helper missing but one dict patched, it's a botched prior run.
    half = sum([helper_present, pay_patched, pof_patched])
    if 0 < half < 3 and not (pay_patched == pof_patched and helper_present):
        # Only fully-applied (all 3) or fully-unapplied is consistent.
        # Anything else: warn but proceed (each step is idempotent).
        notes.append(
            "⚠ partial-state detected (some steps patched, some not). "
            "Each remaining step is idempotent; proceeding with what's missing."
        )

    return edits, notes


def apply_edits(source: str, edits: list[Edit]) -> str:
    # Sort by start descending so earlier offsets stay valid as we splice.
    # Ties (same start) — apply by larger end first (drives replace-then-insert
    # order so insertions land cleanly).
    ordered = sorted(edits, key=lambda e: (-e.start, -e.end))
    out = source
    for e in ordered:
        if e.start > len(out) or e.end > len(out) or e.start > e.end:
            raise RuntimeError(f"edit out of bounds: {e.label}")
        out = out[: e.start] + e.text + out[e.end:]
    return out


# ─── self-test fixture ──────────────────────────────────────────────
SELF_TEST_FIXTURE = '''\
"""Synthetic api.py fixture for add_tx_hash_to_payment.py self-test."""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, Request

log = logging.getLogger("api")
app = FastAPI()


def _stats_write(rec: dict) -> None:
    """Stub — real version appends to stats.jsonl."""
    pass


async def _notify_post_settle(*, endpoint, status, ip, payer_wallet, tx_hash, amount_usd):
    """Stub — real version posts to Telegram."""
    pass


class _AsyncioTG:
    @staticmethod
    def create_task(coro):
        return coro


_asyncio_tg = _AsyncioTG()


@app.middleware("http")
async def payment_notify_middleware(request: Request, call_next):
    response = await call_next(request)
    _endpoint_label = request.url.path
    _ip = request.client.host if request.client else ""
    _amount = 0.0

    if response.status_code >= 500 and request.headers.get("x-payment"):
        # post-settle-failure path
        _stats_write({
            "kind": "post_settle_fail",
            "endpoint": _endpoint_label,
            "status": response.status_code,
            "ip": _ip,
            "amount_usd": _amount,
        })
        _asyncio_tg.create_task(_notify_post_settle(
            endpoint=_endpoint_label,
            status=response.status_code,
            ip=_ip,
            payer_wallet=None,
            tx_hash=None,
            amount_usd=_amount,
        ))
        return response

    if response.status_code == 200 and request.headers.get("x-payment"):
        await _enrich_and_notify(request, response, _endpoint_label, _amount, _ip)
    return response


async def _enrich_and_notify(request, response, endpoint_label, amount, ip):
    ipinfo = {"city": "?", "country": "?"}
    stats = {"total_count": 1, "daily_count": 1}
    _stats_write({
        "kind": "payment",
        "endpoint": endpoint_label,
        "amount_usd": amount,
        "ip": ip,
        "ipinfo": ipinfo,
        "total_count": stats.get("total_count"),
        "daily_count": stats.get("daily_count"),
    })
'''


def run_self_test() -> int:
    """Apply patcher to the synthetic fixture, validate, print result."""
    print("── self-test: patching synthetic fixture ──")
    src = SELF_TEST_FIXTURE
    edits, notes = plan_edits(src)
    for n in notes:
        print(f"  {n}")
    if not edits:
        print("  (no edits — nothing to patch)")
        return 0
    new = apply_edits(src, edits)
    try:
        ast.parse(new)
    except SyntaxError as e:
        print(f"✗ patched fixture failed ast.parse: {e}", file=sys.stderr)
        return 2
    print("✓ ast.parse OK on patched fixture")

    # Re-run on patched to confirm idempotency
    print("── self-test: re-run on already-patched fixture ──")
    edits2, notes2 = plan_edits(new)
    for n in notes2:
        print(f"  {n}")
    if edits2:
        print(f"✗ second run produced {len(edits2)} edits — not idempotent",
              file=sys.stderr)
        return 2
    print("✓ idempotent")

    # Verbose: print resulting fixture so user can eyeball
    print("\n── patched fixture (head) ──")
    for i, line in enumerate(new.splitlines()[:80], 1):
        print(f"  {i:>3}  {line}")
    print("…")
    return 0


# ─── main ────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the patch (default is dry-run)")
    ap.add_argument("--target", default=str(TARGET),
                    help=f"override target path (default {TARGET})")
    ap.add_argument("--self-test", action="store_true",
                    help="run against a synthetic fixture instead of TARGET")
    args = ap.parse_args()

    if args.self_test:
        return run_self_test()

    target = Path(args.target)
    if not target.exists():
        _die(f"target not found: {target}")
    src = target.read_text(encoding="utf-8")

    try:
        edits, notes = plan_edits(src)
    except SystemExit:
        raise
    except Exception as e:
        _die(f"plan failed: {type(e).__name__}: {e}")

    for n in notes:
        print(n)

    if not edits:
        print("(nothing to do — already fully patched)")
        return 0

    new = apply_edits(src, edits)
    try:
        ast.parse(new)
    except SyntaxError as e:
        _die(f"ast.parse failed on patched output: {e}")
    print("✓ ast.parse OK")

    if not args.apply:
        print("(dry-run — re-run with --apply to write)")
        return 0

    backup = target.with_suffix(target.suffix + f".bak.tx-hash-fix-{_kst_tag()}")
    shutil.copy2(target, backup)
    print(f"✓ backup: {backup.name}")
    target.write_text(new, encoding="utf-8")
    print(f"✓ wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
