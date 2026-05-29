#!/usr/bin/env python3
"""
Revenue double-count regression fix — chain normalization in
`indexer/merchant_feed.py`.

What this fixes
===============
The EVM indexer writes `chain='base'` rows; KR Crypto's merchant_feed
posts the same payment as `chain='eip155:8453'`. The merchant_feed
ingest function's dedupe / UPDATE / INSERT all use
`s.get("chain")` directly — so the dedupe `SELECT 1 FROM transactions
WHERE tx_hash=$1 AND chain=$2` never matches, the else-branch fires,
and a duplicate row is inserted. Every KR Crypto payment ends up
double-counted in the 36 stat-SQL sites that don't filter chain.

What this changes (indexer/merchant_feed.py ONLY)
=================================================
1. Inserts a module-level `normalize_chain(chain)` helper that maps
   CAIP-2 identifiers to readable names:
       eip155:8453  → base
       eip155:42161 → arbitrum
       eip155:137   → polygon
       solana:<…>   → solana
   Unknown chains pass through unchanged (None → None).
2. Inside the ingest function (the unique FunctionDef containing
   `s.get("chain")` Calls): inserts
       raw_chain = s.get("chain")
       norm_chain = normalize_chain(raw_chain)
   just before the first chain-using statement, then replaces every
   `s.get("chain")` Call in that function with the Name `norm_chain`.

Why structural anchors
======================
Oracle's `/home/ubuntu/x402watch/indexer/merchant_feed.py` is not in
the local git repo (SCP-operated). Verbatim string anchors would have
to guess line wrap / indent. AST matching on
`Call(func=Attribute(Name("s"), "get"), args=[Constant("chain")])`
is unambiguous and tolerant to formatting.

Idempotency
===========
- helper FunctionDef `normalize_chain` already at module level → skip
- target function already binds Name `norm_chain` → skip the inline
  insert + skip the Call replacements (re-runs would otherwise
  re-replace, since `norm_chain` was once `s.get("chain")`)
- partial state (helper present, function not yet patched, or vice
  versa) is allowed and proceeds with only the missing pieces — each
  step is independently idempotent.
- AST-parse gate on output. KST-tagged backup. Dry-run by default;
  `--apply` to write. `--self-test` runs against a synthetic
  merchant_feed fixture.

Usage
=====
  venv/bin/python scripts/normalize_chain_merchant_feed.py
  venv/bin/python scripts/normalize_chain_merchant_feed.py --apply
  venv/bin/python scripts/normalize_chain_merchant_feed.py --self-test
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
TARGET = ROOT / "indexer" / "merchant_feed.py"

HELPER_NAME = "normalize_chain"
NORM_VAR = "norm_chain"
RAW_VAR = "raw_chain"

HELPER_BLOCK = '''\

_CHAIN_NORMALIZE_MAP = {
    "eip155:8453": "base",
    "eip155:42161": "arbitrum",
    "eip155:137": "polygon",
}


def normalize_chain(chain):
    """Normalize CAIP-2 chain identifiers to readable names.

    Known mappings: ``eip155:8453`` → ``base``, ``eip155:42161`` →
    ``arbitrum``, ``eip155:137`` → ``polygon``. Any ``solana:<address>``
    → ``solana``. Unknown / unmapped chains (including ``None``) pass
    through unchanged so this fix can't regress unrelated callers."""
    if chain is None:
        return None
    mapped = _CHAIN_NORMALIZE_MAP.get(chain)
    if mapped is not None:
        return mapped
    if isinstance(chain, str) and chain.startswith("solana:"):
        return "solana"
    return chain

'''


# ─── small helpers ────────────────────────────────────────────────────
def _die(msg: str, code: int = 2) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(code)


def _kst_tag() -> str:
    now_utc = dt.datetime.utcnow()
    kst = now_utc + dt.timedelta(hours=9)
    return kst.strftime("%Y%m%d-%H%M")


def _line_offsets(source: str) -> list[int]:
    out = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            out.append(i + 1)
    return out


def _pos(offsets: list[int], lineno: int, col: int) -> int:
    return offsets[lineno - 1] + col


def _module_has_helper(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == HELPER_NAME:
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


def _is_s_get_chain(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "s"
        and node.func.attr == "get"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "chain"
    )


def _find_target_function(tree: ast.Module):
    """The unique top-level def (or top-level async def) that contains at
    least one `s.get("chain")` Call. Abort if 0 or >1."""
    matches = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if _is_s_get_chain(sub):
                matches.append(node)
                break
    if len(matches) == 0:
        _die(
            'no FunctionDef in merchant_feed.py contains `s.get("chain")` — '
            "abort. Verify the ingest function name / `s` is the row dict."
        )
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches)
        _die(
            f'multiple FunctionDefs contain `s.get("chain")` ({names}) — '
            "abort. Rename one or pass --target-fn."
        )
    return matches[0]


def _function_binds_name(fn: ast.AST, name: str) -> bool:
    """True if Name(`name`) appears as an Assign target / AugAssign / for-loop
    target / function arg / etc. within `fn`."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return True
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return True
        elif isinstance(node, ast.For):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return True
    return False


def _first_chain_stmt(fn: ast.AST):
    """The first top-level stmt in fn.body whose subtree contains
    `s.get("chain")`. Returns the stmt node (so we can insert before it)."""
    for stmt in fn.body:
        for sub in ast.walk(stmt):
            if _is_s_get_chain(sub):
                return stmt
    return None  # unreachable per _find_target_function postcondition


def _find_chain_calls_in_fn(fn: ast.AST) -> list[ast.Call]:
    out: list[ast.Call] = []
    for node in ast.walk(fn):
        if _is_s_get_chain(node):
            out.append(node)
    return out


# ─── edit primitive ──────────────────────────────────────────────────
class Edit:
    __slots__ = ("start", "end", "text", "label")

    def __init__(self, start: int, end: int, text: str, label: str):
        self.start = start
        self.end = end
        self.text = text
        self.label = label


def _build_norm_assign(indent: str) -> str:
    return (
        f'{indent}{RAW_VAR} = s.get("chain")\n'
        f'{indent}{NORM_VAR} = {HELPER_NAME}({RAW_VAR})\n'
    )


def plan_edits(source: str) -> tuple[list[Edit], list[str]]:
    tree = ast.parse(source)
    offsets = _line_offsets(source)
    notes: list[str] = []
    edits: list[Edit] = []

    # ── Step 1: helper insertion ─────────────────────────────────────
    if _module_has_helper(tree):
        notes.append(f"◌ helper {HELPER_NAME} already present — keep")
        helper_now_present = True
    else:
        last_imp_end = _last_import_end_offset(tree, offsets)
        if last_imp_end == 0:
            _die("no module-level imports in merchant_feed.py — refuse")
        nl = source.find("\n", last_imp_end)
        insertion_point = (nl + 1) if nl >= 0 else len(source)
        edits.append(
            Edit(insertion_point, insertion_point, HELPER_BLOCK,
                 f"insert helper {HELPER_NAME}")
        )
        notes.append(f"✓ insert helper {HELPER_NAME} (+ _CHAIN_NORMALIZE_MAP)")
        helper_now_present = False

    # ── Steps 2 + 3: function body insert + Call replacements ────────
    fn = _find_target_function(tree)
    notes.append(f"  target function: {fn.name} (line {fn.lineno})")

    if _function_binds_name(fn, NORM_VAR):
        notes.append(
            f"◌ {fn.name} already binds `{NORM_VAR}` — function body "
            "considered already patched, no Call replacements emitted"
        )
        if helper_now_present:
            notes.append("(nothing to do — already fully patched)")
        return edits, notes

    # Insert `raw_chain = s.get("chain"); norm_chain = normalize_chain(raw_chain)`
    # immediately before the first stmt that uses `s.get("chain")`.
    first_stmt = _first_chain_stmt(fn)
    if first_stmt is None:
        _die(f"internal: {fn.name} has no chain stmt despite earlier match")
    stmt_pos = _pos(offsets, first_stmt.lineno, first_stmt.col_offset)
    line_start = source.rfind("\n", 0, stmt_pos) + 1
    stmt_indent = source[line_start:stmt_pos]
    if any(ch not in " \t" for ch in stmt_indent):
        _die(f"first chain stmt in {fn.name} is not at line start — abort")

    edits.append(
        Edit(
            line_start, line_start,
            _build_norm_assign(stmt_indent),
            f"{fn.name}: insert {RAW_VAR}/{NORM_VAR} assigns before chain stmt",
        )
    )
    notes.append(
        f"✓ {fn.name}: insert {RAW_VAR} + {NORM_VAR} assigns "
        f"(before stmt at line {first_stmt.lineno})"
    )

    # Replace every s.get("chain") Call in the function with `norm_chain`.
    # NOTE: this includes the call inside the assignment we just inserted —
    # but that insertion is text we're adding, not AST we walked. AST walk
    # was done before the edit, so only ORIGINAL s.get("chain") calls are
    # in `chain_calls`.
    chain_calls = _find_chain_calls_in_fn(fn)
    for call in chain_calls:
        call_start = _pos(offsets, call.lineno, call.col_offset)
        call_end = _pos(offsets, call.end_lineno, call.end_col_offset)
        edits.append(
            Edit(call_start, call_end, NORM_VAR,
                 f"{fn.name}: s.get(\"chain\") @ L{call.lineno} → {NORM_VAR}")
        )
    notes.append(
        f"✓ {fn.name}: replace {len(chain_calls)} `s.get(\"chain\")` Calls "
        f"with `{NORM_VAR}`"
    )

    return edits, notes


def apply_edits(source: str, edits: list[Edit]) -> str:
    # Sort by start descending; ties by end descending. Replacements (end>start)
    # ordered before pure insertions (end==start) at the same offset so
    # insertion text lands at the original position.
    ordered = sorted(edits, key=lambda e: (-e.start, -e.end))
    out = source
    for e in ordered:
        if e.start > len(out) or e.end > len(out) or e.start > e.end:
            raise RuntimeError(f"edit out of bounds: {e.label}")
        out = out[: e.start] + e.text + out[e.end:]
    return out


# ─── self-test fixture ──────────────────────────────────────────────
SELF_TEST_FIXTURE = '''\
"""Synthetic merchant_feed.py fixture for normalize_chain patcher self-test."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("merchant_feed")


async def ingest_settlement(c, s: dict) -> None:
    """Ingest one merchant-signed settlement row `s` via asyncpg conn `c`."""
    existing = await c.fetchrow(
        "SELECT 1 FROM transactions WHERE tx_hash = $1 AND chain = $2",
        s.get("tx_hash"), s.get("chain"),
    )
    if existing:
        await c.execute(
            """
            UPDATE transactions
               SET service_id = $3,
                   attribution_source = 'merchant_feed_signed',
                   feed_merchant_id = $4
             WHERE tx_hash = $1 AND chain = $2
            """,
            s.get("tx_hash"), s.get("chain"),
            s.get("service_id"), s.get("merchant_id"),
        )
    else:
        await c.execute(
            """
            INSERT INTO transactions (
                tx_hash, chain, service_id, amount_usd,
                attribution_source, feed_merchant_id, is_x402_payment
            ) VALUES ($1, $2, $3, $4, 'merchant_feed_signed', $5, TRUE)
            """,
            s.get("tx_hash"), s.get("chain"),
            s.get("service_id"), s.get("amount_usd"),
            s.get("merchant_id"),
        )


def _other_helper(s: dict) -> str:
    # No chain access — should NOT be touched.
    return s.get("merchant_id", "")
'''


def run_self_test() -> int:
    print("── self-test: patching synthetic merchant_feed fixture ──")
    src = SELF_TEST_FIXTURE
    edits, notes = plan_edits(src)
    for n in notes:
        print(f"  {n}")
    if not edits:
        print("  (no edits — already patched)")
        return 0
    new = apply_edits(src, edits)
    try:
        ast.parse(new)
    except SyntaxError as e:
        print(f"✗ patched fixture failed ast.parse: {e}", file=sys.stderr)
        return 2
    print("✓ ast.parse OK on patched fixture")

    # Runtime self-test: does normalize_chain actually map correctly?
    print("── runtime: normalize_chain mapping ──")
    ns: dict = {}
    exec(compile(new, "<patched>", "exec"), ns)
    nc = ns["normalize_chain"]
    cases = [
        ("eip155:8453", "base"),
        ("eip155:42161", "arbitrum"),
        ("eip155:137", "polygon"),
        ("solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", "solana"),
        ("base", "base"),                # already normalized — pass through
        ("polygon", "polygon"),
        ("arbitrum", "arbitrum"),
        ("solana", "solana"),
        ("unknown-future-chain", "unknown-future-chain"),  # unknown → passthrough
        (None, None),
    ]
    all_ok = True
    for inp, expect in cases:
        got = nc(inp)
        ok = got == expect
        all_ok &= ok
        print(("  OK   " if ok else "  FAIL ")
              + f"normalize_chain({inp!r}) = {got!r} (expected {expect!r})")

    # Idempotency
    print("── self-test: re-run on already-patched fixture ──")
    edits2, notes2 = plan_edits(new)
    for n in notes2:
        print(f"  {n}")
    if edits2:
        print(f"✗ second run produced {len(edits2)} edits — not idempotent",
              file=sys.stderr)
        return 2
    print("✓ idempotent")

    # Sanity: norm_chain is referenced at >= 1 callsite. Count = total
    # `norm_chain` occurrences minus 1 for the assign target (the LHS of
    # `norm_chain = normalize_chain(raw_chain)`).
    n_callsites = new.count(NORM_VAR) - 1
    print(f"  norm_chain referenced in {n_callsites} callsite positions "
          f"(synthetic fixture has 3 chain accesses; real merchant_feed.py "
          f"is documented at 4)")
    if n_callsites < 1:
        print("✗ no callsite replacement happened", file=sys.stderr)
        return 2

    if not all_ok:
        return 2
    return 0


# ─── main ────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--target", default=str(TARGET))
    ap.add_argument("--self-test", action="store_true")
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

    backup = target.with_suffix(target.suffix + f".bak.chain-norm-{_kst_tag()}")
    shutil.copy2(target, backup)
    print(f"✓ backup: {backup.name}")
    target.write_text(new, encoding="utf-8")
    print(f"✓ wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
