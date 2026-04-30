import Link from "next/link";
import { ExternalLink } from "lucide-react";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-foreground/5">
      <div className="mx-auto max-w-6xl px-6 py-10 flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1 text-sm text-foreground/60">
          <p>
            <span className="font-medium text-foreground/80">x402watch</span> · made by{" "}
            <Link
              href="https://printmoneylab.com"
              className="hover:text-foreground"
              target="_blank"
              rel="noopener noreferrer"
            >
              PrintMoneyLab
            </Link>
          </p>
          <p className="text-xs text-foreground/45">
            Open source: <span className="font-mono">Apache 2.0</span> (code) ·{" "}
            <span className="font-mono">CC0</span> (data)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <Link
            href="https://github.com/printmoneylab/x402watch/blob/main/docs/wash-filter-methodology.md"
            className="text-foreground/65 hover:text-foreground"
            target="_blank"
            rel="noopener noreferrer"
          >
            Methodology
          </Link>
          <Link
            href="https://github.com/printmoneylab/x402watch-data"
            className="text-foreground/65 hover:text-foreground"
            target="_blank"
            rel="noopener noreferrer"
          >
            Data
          </Link>
          <Link
            href="https://github.com/printmoneylab/x402watch"
            className="text-foreground/65 hover:text-foreground inline-flex items-center gap-1.5"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub"
          >
            GitHub <ExternalLink className="size-3.5" />
          </Link>
          <Link
            href="https://twitter.com/printmoneylab"
            className="text-foreground/65 hover:text-foreground inline-flex items-center gap-1.5"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Twitter"
          >
            @printmoneylab <ExternalLink className="size-3.5" />
          </Link>
        </div>
      </div>
    </footer>
  );
}
