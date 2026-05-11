"use client";

/**
 * LabelBadge — single source of truth for rendering a buyer label in the
 * dashboard. Reads confidence and degrades the visual:
 *   ≥ 0.85  → bold label, no qualifier
 *   0.70+   → "likely …" with a ⚠ disclaimer link
 *   < 0.70  → "unlabeled" (treated as no-decision)
 *
 * Optional `reason` is exposed via `title` for hover (desktop).
 * The "Report incorrect label" Flag button surfaces on self_test /
 * suspected_wash only. It opens the in-page ReportDialog (Layer 4
 * dispute UI talking to /api/disputes). The dialog footer keeps a
 * GitHub Issue fallback for users who prefer the public channel.
 */
import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Flag } from "lucide-react";
import { LABEL_COLOR_TW } from "@/lib/categories";
import { cn } from "@/lib/utils";
import { ReportDialog } from "@/components/common/ReportDialog";

export type BuyerLabel =
  | "organic_user"
  | "self_test"
  | "developer"
  | "suspected_wash"
  | "ai_agent"
  | "analytics_bot"
  | "exchange_user"
  | "verifier"
  | "owner_test"
  | "unlabeled";

const CONF_STRONG = 0.85;
const CONF_LIKELY = 0.70;

const PRETTY: Partial<Record<BuyerLabel, string>> = {
  owner_test: "operator self-test",
};

function prettyLabel(l: BuyerLabel): string {
  return PRETTY[l] ?? l;
}

const REPORT_BASE =
  "https://github.com/printmoneylab/x402watch/issues/new?" +
  "labels=dispute,label-review&" +
  "title=" +
  encodeURIComponent("Label dispute") +
  "&body=";

function githubReportUrl(opts: {
  label: BuyerLabel;
  buyer?: string;
  seller?: string;
  reason?: string;
}): string {
  const body = [
    "## Label dispute",
    "",
    `**Label:** \`${opts.label}\``,
    opts.buyer ? `**Buyer:** \`${opts.buyer}\`` : "",
    opts.seller ? `**Seller:** \`${opts.seller}\`` : "",
    opts.reason ? `**Reason field:** \`${opts.reason}\`` : "",
    "",
    "### Why this label is incorrect",
    "(describe the patterns / evidence)",
    "",
    "### Suggested correct label",
    "(organic_user / ai_agent / developer / verifier / etc.)",
    "",
    "### Additional context",
    "(links, on-chain evidence, etc.)",
  ]
    .filter(Boolean)
    .join("\n");
  return REPORT_BASE + encodeURIComponent(body);
}

export function LabelBadge({
  label,
  confidence,
  reason,
  size = "sm",
  showReport = true,
  buyerAddress,
  sellerAddress,
}: {
  label: BuyerLabel | string | null | undefined;
  confidence?: number | null;
  reason?: string | null;
  size?: "sm" | "md";
  showReport?: boolean;
  buyerAddress?: string;
  sellerAddress?: string;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);

  const effective: BuyerLabel =
    (label as BuyerLabel) && label !== "" ? (label as BuyerLabel) : "unlabeled";
  const conf = typeof confidence === "number" ? confidence : null;
  const swatch = LABEL_COLOR_TW[effective] ?? "bg-zinc-700";

  // Confidence band determines whether we show the literal label or
  // soften it. unlabeled / owner_test bypass softening (always literal).
  const isSoftLabel =
    effective !== "owner_test" && effective !== "exchange_user";
  let display: string;
  let qualifier: "strong" | "likely" | "unknown";
  if (!isSoftLabel || conf === null || conf >= CONF_STRONG) {
    display = prettyLabel(effective);
    qualifier = "strong";
  } else if (conf >= CONF_LIKELY) {
    display = `likely ${prettyLabel(effective)}`;
    qualifier = "likely";
  } else {
    display = "unlabeled";
    qualifier = "unknown";
  }

  const showsReport =
    showReport &&
    !!buyerAddress &&
    (effective === "self_test" || effective === "suspected_wash");

  const sizeCls =
    size === "md"
      ? "text-sm gap-2 px-2 py-1"
      : "text-xs gap-1.5";

  return (
    <span className={cn("inline-flex items-center", sizeCls)}>
      <span className={cn("inline-block size-2 rounded-full", swatch)} aria-hidden />
      <span
        title={reason ?? undefined}
        className={cn(
          qualifier === "unknown" && "text-foreground/45 italic",
          qualifier === "likely" && "text-foreground/75"
        )}
      >
        {display}
      </span>
      {qualifier === "likely" && (
        <Link
          href="/docs/methodology#confidence-bands"
          aria-label="Confidence below 0.85 — see methodology"
          className="text-amber-400 hover:text-amber-300"
        >
          <AlertTriangle className="size-3" />
        </Link>
      )}
      {showsReport && (
        <>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDialogOpen(true);
            }}
            aria-label="Report this label as incorrect"
            title="Report this label as incorrect"
            className="text-foreground/40 hover:text-rose-300 transition-colors"
          >
            <Flag className="size-3" />
          </button>
          <ReportDialog
            open={dialogOpen}
            onClose={() => setDialogOpen(false)}
            buyerAddress={buyerAddress!}
            sellerAddress={sellerAddress}
            currentLabel={effective}
            currentConfidence={conf}
            githubFallbackUrl={githubReportUrl({
              label: effective,
              buyer: buyerAddress,
              seller: sellerAddress,
              reason: reason ?? undefined,
            })}
          />
        </>
      )}
    </span>
  );
}
