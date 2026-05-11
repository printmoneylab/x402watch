"use client";

/**
 * ReportDialog — native <dialog> wrapper that submits a label dispute
 * to /api/disputes. Designed to be opened from a LabelBadge Flag button
 * on `self_test` / `suspected_wash` rows.
 *
 * Native <dialog> is intentional:
 *   - zero added dependencies (no Radix)
 *   - built-in focus trap + ESC handling
 *   - ::backdrop styling for free
 *   - works on mobile Safari ≥ 15.4 (CF Pages baseline)
 *
 * On success the dialog flips into a confirmation state showing the
 * Oracle-issued dispute_id; users can close or open a GitHub Issue as
 * a secondary report channel.
 */
import { useEffect, useRef, useState } from "react";
import { X, Loader2, CheckCircle2, AlertCircle, ExternalLink } from "lucide-react";
import { REASON_MIN, REASON_MAX } from "@/lib/disputes";

type Props = {
  open: boolean;
  onClose: () => void;
  buyerAddress: string;
  sellerAddress?: string;
  currentLabel: string;
  currentConfidence?: number | null;
  githubFallbackUrl?: string;
};

type Phase =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "ok"; disputeId?: number; message?: string }
  | { kind: "error"; error: string };

const ERROR_COPY: Record<string, string> = {
  invalid_buyer: "Buyer address looks malformed.",
  invalid_seller: "Seller address looks malformed.",
  invalid_reporter: "Your wallet address looks malformed.",
  invalid_label: "That label isn't part of our taxonomy.",
  reason_too_short: `Tell us a little more — at least ${REASON_MIN} characters.`,
  reason_too_long: `Keep it under ${REASON_MAX} characters.`,
  invalid_json: "Request was malformed. Try again.",
  rate_limit_exceeded: "Too many reports from your network this hour. Try again later.",
  duplicate: "You've already reported this buyer recently.",
  ip_banned: "This network is temporarily blocked from submitting reports.",
  kv_unavailable: "Storage backend is unavailable. Try again shortly.",
  upstream_unavailable: "Our review service is briefly down. Try again shortly.",
  internal_unavailable: "Dispute service isn't configured yet.",
};

function errorMessage(code: string): string {
  return ERROR_COPY[code] || `Submission failed (${code}).`;
}

export function ReportDialog({
  open,
  onClose,
  buyerAddress,
  sellerAddress,
  currentLabel,
  currentConfidence,
  githubFallbackUrl,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [reporter, setReporter] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });

  // Sync controlled open prop with the imperative dialog element.
  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);

  // Reset internal state when the dialog closes.
  useEffect(() => {
    if (!open) {
      // Brief delay so reset isn't visible during the close animation.
      const t = setTimeout(() => {
        setReason("");
        setReporter("");
        setPhase({ kind: "idle" });
      }, 200);
      return () => clearTimeout(t);
    }
  }, [open]);

  const reasonOk = reason.trim().length >= REASON_MIN && reason.trim().length <= REASON_MAX;
  const submitting = phase.kind === "submitting";
  const ok = phase.kind === "ok";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!reasonOk || submitting) return;
    setPhase({ kind: "submitting" });
    try {
      const res = await fetch("/api/disputes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          buyer_address: buyerAddress,
          seller_address: sellerAddress,
          reporter_address: reporter.trim() || undefined,
          reason: reason.trim(),
          current_label: currentLabel,
          current_confidence: currentConfidence ?? undefined,
        }),
      });
      const data = (await res.json().catch(() => null)) as {
        ok?: boolean;
        error?: string;
        dispute_id?: number;
        message?: string;
      } | null;
      if (res.ok && data?.ok) {
        setPhase({
          kind: "ok",
          disputeId: data.dispute_id,
          message: data.message,
        });
      } else {
        setPhase({ kind: "error", error: data?.error || `http_${res.status}` });
      }
    } catch {
      setPhase({ kind: "error", error: "network_error" });
    }
  }

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onClick={(e) => {
        // Click on backdrop (the dialog element itself, not its contents) closes.
        if (e.target === dialogRef.current) onClose();
      }}
      className="rounded-xl bg-background text-foreground border border-foreground/15 p-0 w-[min(92vw,520px)] backdrop:bg-black/60"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-5 sm:p-6">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold tracking-tight">
              Report incorrect label
            </h2>
            <p className="mt-1 text-xs text-foreground/55">
              We review reports daily and reconcile against the algorithm.
              Labels never change silently — every adjustment lands in the
              public buyer_labels log.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="-mr-1 -mt-1 rounded-md p-1 text-foreground/50 hover:bg-foreground/[0.06] hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </header>

        <dl className="grid grid-cols-3 gap-x-3 gap-y-1.5 rounded-md border border-foreground/10 bg-foreground/[0.03] p-3 text-xs">
          <dt className="text-foreground/55">Buyer</dt>
          <dd className="col-span-2 font-mono text-foreground/85 break-all">
            {buyerAddress}
          </dd>
          {sellerAddress && (
            <>
              <dt className="text-foreground/55">Seller</dt>
              <dd className="col-span-2 font-mono text-foreground/85 break-all">
                {sellerAddress}
              </dd>
            </>
          )}
          <dt className="text-foreground/55">Current label</dt>
          <dd className="col-span-2 font-mono text-foreground/85">
            {currentLabel}
            {currentConfidence != null && (
              <span className="ml-2 text-foreground/55">
                ({currentConfidence.toFixed(2)})
              </span>
            )}
          </dd>
        </dl>

        {ok ? (
          <div className="flex items-start gap-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            <CheckCircle2 className="size-4 mt-0.5 text-emerald-400 shrink-0" />
            <div className="flex flex-col gap-1">
              <p className="text-foreground">
                Report submitted
                {phase.kind === "ok" && phase.disputeId != null && (
                  <>
                    {" "}
                    <span className="font-mono text-foreground/70">
                      #{phase.disputeId}
                    </span>
                  </>
                )}
                .
              </p>
              <p className="text-xs text-foreground/65">
                {phase.kind === "ok" && phase.message
                  ? phase.message
                  : "We'll review on the next daily run."}
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="dispute-reason"
                className="text-xs text-foreground/65"
              >
                Why is this label wrong?{" "}
                <span className="text-foreground/45">
                  ({REASON_MIN}-{REASON_MAX} chars)
                </span>
              </label>
              <textarea
                id="dispute-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value.slice(0, REASON_MAX))}
                rows={5}
                placeholder="On-chain evidence, links, prior behaviour patterns — anything that helps us reproduce."
                required
                minLength={REASON_MIN}
                maxLength={REASON_MAX}
                className="w-full resize-none rounded-md border border-foreground/15 bg-foreground/[0.03] p-2.5 text-sm text-foreground placeholder:text-foreground/35 focus:border-foreground/40 focus:outline-none"
              />
              <div className="flex items-center justify-between text-[11px] text-foreground/45">
                <span>
                  {reason.trim().length < REASON_MIN
                    ? `${REASON_MIN - reason.trim().length} more characters needed`
                    : "Looks good"}
                </span>
                <span className="font-mono">
                  {reason.length}/{REASON_MAX}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="dispute-reporter"
                className="text-xs text-foreground/65"
              >
                Your wallet address{" "}
                <span className="text-foreground/45">(optional)</span>
              </label>
              <input
                id="dispute-reporter"
                value={reporter}
                onChange={(e) => setReporter(e.target.value)}
                placeholder="0x… or Solana base58"
                spellCheck={false}
                className="w-full rounded-md border border-foreground/15 bg-foreground/[0.03] px-2.5 py-1.5 text-sm font-mono text-foreground placeholder:text-foreground/35 focus:border-foreground/40 focus:outline-none"
              />
              <p className="text-[11px] text-foreground/45">
                If supplied, we&apos;ll surface the wallet in the audit log.
                Leave blank to report anonymously.
              </p>
            </div>

            {phase.kind === "error" && (
              <div className="flex items-start gap-2 rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm">
                <AlertCircle className="size-4 mt-0.5 text-rose-400 shrink-0" />
                <span className="text-foreground/85">
                  {errorMessage(phase.error)}
                </span>
              </div>
            )}
          </>
        )}

        <footer className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between sm:items-center">
          {githubFallbackUrl ? (
            <a
              href={githubFallbackUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-foreground/55 hover:text-foreground"
            >
              Or open a GitHub Issue <ExternalLink className="size-3" />
            </a>
          ) : (
            <span />
          )}
          {ok ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background hover:opacity-90"
            >
              Done
            </button>
          ) : (
            <button
              type="submit"
              disabled={!reasonOk || submitting}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting && <Loader2 className="size-3.5 animate-spin" />}
              {submitting ? "Submitting…" : "Submit report"}
            </button>
          )}
        </footer>
      </form>
    </dialog>
  );
}
