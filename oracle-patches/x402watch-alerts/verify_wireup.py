#!/usr/bin/env python3
"""
Post-apply verification — run on Oracle after every wireup step.

Permanent location: /home/ubuntu/x402watch/scripts/verify_wireup.py
(create scripts/ if it doesn't exist)

Usage:
    venv/bin/python scripts/verify_wireup.py
    # exit 0 = all checks pass, exit 1 = at least one failure

Designed to be cheap: no network calls, no service interaction, just
static file inspection + a few Python imports. Run after every edit so
mistakes are caught immediately instead of at restart-time.

Checks (each prints PASS / FAIL):

  1. app/api.py syntactically valid
  2. app/api.py final non-blank statement IS `app = X402ResourceRewriter(app)`
  3. app/x402_meta.py is unmodified vs the version this repo shipped
     (warning-only — Moa may legitimately have local edits)
  4. app/mcp_server.py syntactically valid
  5. All new modules importable: client_classifier, telegram_notify,
     daily_summary, mcp_payment_hint, _stats, paid_tools_catalog
  6. PAID_ENDPOINTS catalogue contains the expected five entries with
     the expected prices

Exit code 1 if any of checks 1, 2, 4, 5, 6 fail. Check 3 is advisory.
"""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/x402watch")
APP = ROOT / "app"

WRAPPER_TAIL = "app = X402ResourceRewriter(app)"

EXPECTED_PAID = [
    ("/api/v1/services/{id}/wash-detail",       "GET",  0.005),
    ("/api/v1/services/{id}/transactions",      "GET",  0.010),
    ("/api/v1/categories/{cat}/full-history",   "GET",  0.020),
    ("/api/v1/wash/check",                      "POST", 0.050),
    ("/api/v1/buyers/{address}/profile",        "GET",  0.005),
]


_results: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({detail})" if detail else ""))


# ─── 1, 4: syntax ────────────────────────────────────────────────────
def check_python_syntax(name: str, path: Path) -> None:
    try:
        ast.parse(path.read_text())
        report(name, True)
    except SyntaxError as e:
        report(name, False, f"{e.__class__.__name__}: {e}")
    except FileNotFoundError:
        report(name, False, f"missing: {path}")


# ─── 2: wrapper invariant ────────────────────────────────────────────
def check_wrapper_last() -> None:
    path = APP / "api.py"
    try:
        lines = [l.rstrip() for l in path.read_text().splitlines()]
    except FileNotFoundError:
        report("api.py wrapper-last", False, "api.py missing")
        return
    # Skip trailing blank / comment lines so a stray comment underneath
    # doesn't fail this check.
    for ln in reversed(lines):
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped == WRAPPER_TAIL:
            report("api.py last code line == X402ResourceRewriter(app)", True)
        else:
            report(
                "api.py last code line == X402ResourceRewriter(app)",
                False,
                f"got: {stripped!r}",
            )
        return
    report("api.py last code line == X402ResourceRewriter(app)", False, "no code lines")


# ─── 3: x402_meta untouched (advisory) ───────────────────────────────
def check_x402_meta_untouched() -> None:
    path = APP / "x402_meta.py"
    canonical = ROOT / "oracle-patches" / "pr36-openapi" / "x402_meta.py"
    if not path.exists() or not canonical.exists():
        report("x402_meta.py vs canonical (advisory)", False, "file(s) missing")
        return
    same = path.read_bytes() == canonical.read_bytes()
    detail = "identical" if same else "DIFFERS — verify intentional"
    # Always print PASS for this advisory check (we don't fail the run
    # on intentional local edits), but make the difference visible.
    print(f"[INFO] x402_meta.py vs canonical: {detail}")


# ─── 5: imports ──────────────────────────────────────────────────────
def check_imports() -> None:
    mods = [
        "app.client_classifier",
        "app.telegram_notify",
        "app.daily_summary",
        "app.mcp_payment_hint",
        "app._stats",
        "app.paid_tools_catalog",
    ]
    sys.path.insert(0, str(ROOT))
    for m in mods:
        try:
            importlib.import_module(m)
            report(f"import {m}", True)
        except Exception as e:
            report(f"import {m}", False, f"{e.__class__.__name__}: {e}")


# ─── 6: paid catalogue parity ────────────────────────────────────────
def check_paid_catalog() -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from app.paid_tools_catalog import PAID_ENDPOINTS  # noqa: E402
    except Exception as e:
        report("paid_tools_catalog import", False, str(e))
        return
    got = sorted((e.path, e.method, e.price_usd) for e in PAID_ENDPOINTS)
    want = sorted(EXPECTED_PAID)
    if got == want:
        report(f"paid catalogue has {len(want)} expected entries", True)
    else:
        missing = set(want) - set(got)
        extra = set(got) - set(want)
        report(
            "paid catalogue parity",
            False,
            f"missing={missing} extra={extra}",
        )


# ─── Driver ──────────────────────────────────────────────────────────
def main() -> int:
    print("== x402watch wireup verification ==")
    print(f"   ROOT = {ROOT}")
    print()
    check_python_syntax("app/api.py syntax", APP / "api.py")
    check_wrapper_last()
    check_x402_meta_untouched()
    check_python_syntax("app/mcp_server.py syntax", APP / "mcp_server.py")
    check_imports()
    check_paid_catalog()
    print()
    failed = [r for r in _results if not r[1]]
    if failed:
        print(f"FAIL — {len(failed)} check(s) failed:")
        for name, _, detail in failed:
            print(f"  - {name}  {detail}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
