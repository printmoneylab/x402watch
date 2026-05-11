"""
Step 6 — patch indexer/labeller.py to drain the recompute_queue at
the end of the daily run.

Permanent location: /home/ubuntu/x402watch/migrations/labeller_queue_patch.py

What it does:
  - After Layer 4 finishes, pulls up to 500 unprocessed recompute_queue rows.
  - For each queued buyer, reads the *new* label (latest buyer_labels row)
    and compares it to the dispute snapshot (label_disputes.current_label).
  - If different → status='resolved', resolution_note='label_changed:OLD->NEW'.
  - If same     → status='reviewed', resolution_note='no_change'.
  - Marks the queue row processed_at = NOW().

Usage:
    cd /home/ubuntu/x402watch
    cp indexer/labeller.py indexer/labeller.py.bak.pre_step6
    venv/bin/python migrations/labeller_queue_patch.py

Idempotent — re-running prints `PATCH_ALREADY_APPLIED` and exits 0.

Rollback:
    cp indexer/labeller.py.bak.pre_step6 indexer/labeller.py
"""
import sys

LABELLER = "/home/ubuntu/x402watch/indexer/labeller.py"

NEW_HELPER = '''
# ─── Step 6: dispute recompute queue drain ───────────────────────────
async def process_recompute_queue(pool) -> dict:
    """Resolve disputes for buyers whose labels were just recomputed."""
    summary = {"queued": 0, "resolved": 0, "reviewed": 0}
    async with pool.acquire() as c:
        rows = await c.fetch("""
            SELECT q.buyer_address, q.triggered_by, q.pending_count
            FROM recompute_queue q
            WHERE q.processed_at IS NULL
            ORDER BY q.added_at
            LIMIT 500
        """)
        if not rows:
            return summary
        summary["queued"] = len(rows)
        log.info("recompute queue: draining %d buyers", len(rows))

        for r in rows:
            buyer = r["buyer_address"]
            new_label_row = await c.fetchrow("""
                SELECT label, confidence FROM buyer_labels
                WHERE buyer_address = $1
                ORDER BY time DESC LIMIT 1
            """, buyer)
            new_label = new_label_row["label"] if new_label_row else None

            disputes = await c.fetch("""
                SELECT id, current_label FROM label_disputes
                WHERE buyer_address = $1 AND status = 'pending'
            """, buyer)

            async with c.transaction():
                for d in disputes:
                    if new_label and d["current_label"] != new_label:
                        await c.execute("""
                            UPDATE label_disputes
                            SET status = 'resolved',
                                resolved_at = NOW(),
                                resolution_note = $1
                            WHERE id = $2
                        """, f"label_changed:{d['current_label']}->{new_label}", d["id"])
                        summary["resolved"] += 1
                    else:
                        await c.execute("""
                            UPDATE label_disputes
                            SET status = 'reviewed',
                                resolved_at = NOW(),
                                resolution_note = 'no_change'
                            WHERE id = $1
                        """, d["id"])
                        summary["reviewed"] += 1
                await c.execute("""
                    UPDATE recompute_queue
                    SET processed_at = NOW()
                    WHERE buyer_address = $1
                """, buyer)
    log.info("recompute queue drained: %s", summary)
    return summary

'''


# The patch splices the new helper *before* the run() function and adds
# a guarded call to it after derive_global completes but before the
# finally: close_pool. Anchors match the v2.0 labeller exactly.

INSERT_BEFORE = "# ─── Main (Layer 4 — 4-stage pipeline) ──────────────────────────────"
CALL_ANCHOR = '        summary["derive_global"] = dg_out\n    finally:'
CALL_REPLACEMENT = (
    '        summary["derive_global"] = dg_out\n'
    '\n'
    '        # Step 6: drain dispute recompute_queue → mark resolved/reviewed.\n'
    '        try:\n'
    '            q_out = await process_recompute_queue(pool)\n'
    '            summary["recompute_queue"] = q_out\n'
    '        except Exception:\n'
    '            log.exception("process_recompute_queue failed (continuing)")\n'
    '            summary["recompute_queue"] = {"error": True}\n'
    '    finally:'
)


def main() -> int:
    try:
        src = open(LABELLER).read()
    except FileNotFoundError:
        print(f"ERR: {LABELLER} not found", file=sys.stderr)
        return 2

    if "process_recompute_queue" in src:
        print("PATCH_ALREADY_APPLIED")
        return 0

    if INSERT_BEFORE not in src:
        print(f"ERR: helper anchor not found in {LABELLER}", file=sys.stderr)
        print(f"     expected: {INSERT_BEFORE!r}", file=sys.stderr)
        return 1
    src = src.replace(INSERT_BEFORE, NEW_HELPER + INSERT_BEFORE, 1)

    if CALL_ANCHOR not in src:
        print(f"ERR: call-site anchor not found in {LABELLER}", file=sys.stderr)
        print(f"     expected: {CALL_ANCHOR!r}", file=sys.stderr)
        return 1
    src = src.replace(CALL_ANCHOR, CALL_REPLACEMENT, 1)

    import ast
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"ERR: post-patch syntax check failed: {e}", file=sys.stderr)
        return 3

    open(LABELLER, "w").write(src)
    print(f"PATCH_OK lines={src.count(chr(10)) + 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
