import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowRight, ExternalLink } from "lucide-react";

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden border-b border-foreground/5">
      <div className="mx-auto max-w-6xl px-6 pt-28 pb-24 sm:pt-36 sm:pb-32">
        <div className="flex flex-col items-start gap-8 max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-foreground/10 bg-foreground/[0.03] px-3 py-1 text-xs font-medium text-foreground/70">
            <span className="size-2 rounded-full bg-accent animate-pulse" />
            Live · indexing every hour
          </span>
          <h1 className="text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl text-balance max-w-[18ch] sm:max-w-[22ch]">
            See what <span className="text-accent">x402</span> actually looks like.
          </h1>
          <p className="max-w-2xl text-base text-foreground/70 leading-relaxed sm:text-lg text-pretty">
            Wash-filtered intelligence for the agentic web. Real-time dashboard, open
            methodology, AI-native API.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <Button asChild size="lg">
              <Link href="#data">
                Explore data <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link
                href="https://github.com/printmoneylab/x402watch"
                target="_blank"
                rel="noopener noreferrer"
              >
                View on GitHub <ExternalLink className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </div>
      {/* subtle radial gradient backdrop */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-40"
        style={{
          background:
            "radial-gradient(60% 60% at 25% 35%, rgba(62,224,163,0.08) 0%, transparent 60%)",
        }}
      />
    </section>
  );
}
