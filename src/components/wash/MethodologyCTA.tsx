import Link from "next/link";
import { ArrowRight, ExternalLink } from "lucide-react";

const METHODOLOGY_URL = "/docs/methodology";
const DISPUTE_URL =
  "https://github.com/printmoneylab/x402watch/issues/new";

export function MethodologyCTA() {
  return (
    <div className="rounded-lg border border-foreground/15 bg-gradient-to-br from-foreground/[0.04] to-foreground/[0.01] p-6 sm:p-8">
      <h3 className="text-lg sm:text-xl font-semibold tracking-tight">
        How wash detection works on x402watch
      </h3>
      <p className="mt-2 max-w-2xl text-sm text-foreground/70 leading-relaxed">
        Open methodology, version-controlled in our repo. The pipeline runs
        the same five steps for every buyer, every day:
      </p>
      <ol className="mt-4 grid gap-2 sm:grid-cols-2 text-sm text-foreground/75">
        <li className="flex gap-2">
          <span className="font-mono text-foreground/40">1.</span>
          8-label classification in priority order (organic_user → verifier).
        </li>
        <li className="flex gap-2">
          <span className="font-mono text-foreground/40">2.</span>
          Cohort signals (uniform_amount, coordinated_start, uniform_tx_count).
        </li>
        <li className="flex gap-2">
          <span className="font-mono text-foreground/40">3.</span>
          Vanity clustering (strict + broad address-pattern matching).
        </li>
        <li className="flex gap-2">
          <span className="font-mono text-foreground/40">4.</span>
          Conservative developer label — only with strong recurrence evidence.
        </li>
        <li className="flex gap-2 sm:col-span-2">
          <span className="font-mono text-foreground/40">5.</span>
          Real volume reporting excludes self_test, suspected_wash, and
          developer traffic.
        </li>
      </ol>
      <div className="mt-6 flex flex-col sm:flex-row gap-3">
        <Link
          href={METHODOLOGY_URL}
          className="inline-flex items-center gap-1.5 h-10 px-4 rounded-md border border-foreground/20 bg-foreground/[0.06] text-sm font-medium text-foreground hover:bg-foreground/10 transition-colors"
        >
          Read full methodology
          <ArrowRight className="size-4" />
        </Link>
        <Link
          href="https://github.com/printmoneylab/x402watch"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 h-10 px-4 rounded-md text-sm text-foreground/70 hover:text-foreground transition-colors"
        >
          GitHub repo
          <ExternalLink className="size-3.5" />
        </Link>
      </div>
    </div>
  );
}

export function OperatorBox() {
  return (
    <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-5 text-sm">
      <p className="text-foreground/85">
        Are you the operator of a service classified here?
      </p>
      <p className="mt-1 text-foreground/60 leading-relaxed">
        Labels are deterministic and reproducible from public on-chain data.
        Open a{" "}
        <Link
          href={DISPUTE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-foreground/90 hover:text-foreground underline underline-offset-2"
        >
          GitHub issue
        </Link>{" "}
        with the seller address and we will walk through the signals that
        triggered the label.
      </p>
    </div>
  );
}
