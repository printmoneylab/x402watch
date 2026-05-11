import type { Metadata } from "next";
import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import { ChevronLeft, ExternalLink } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
// Dark-theme syntax highlighting for code fences. Imported only on this
// page so it doesn't bloat unrelated bundles.
import "highlight.js/styles/github-dark.css";
import { JsonLd } from "@/components/common/JsonLd";
import { articleSchema, SITE_URL } from "@/lib/jsonld";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Wash Filter Methodology — x402watch",
  description:
    "Open methodology behind x402watch's wash detection: 4-layer pipeline, 9-label taxonomy, confidence bands. Version-controlled, reproducible.",
};

function readMethodologyMarkdown(): string {
  // The markdown lives at <repo>/content/methodology.md and is part of
  // the build. fs.readFileSync at module scope would also work but we
  // keep it in a function so a missing file shows up as a runtime error
  // local to this route, not a build crash.
  const file = path.join(process.cwd(), "content", "methodology.md");
  return fs.readFileSync(file, "utf8");
}

export default function MethodologyPage() {
  const md = readMethodologyMarkdown();
  const updatedIso = new Date().toISOString();
  return (
    <main className="flex-1">
      <JsonLd
        data={articleSchema({
          headline: "x402watch Wash Filter Methodology",
          description:
            "Open methodology — four-layer pipeline, nine-label taxonomy, confidence bands, conservative defaults.",
          url: `${SITE_URL}/docs/methodology`,
          datePublished: updatedIso,
        })}
      />

      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-3xl px-6 pt-10 pb-6 sm:pt-14 sm:pb-8">
          <Link
            href="/wash-report"
            className="inline-flex items-center gap-1 text-sm text-foreground/60 hover:text-foreground mb-4"
          >
            <ChevronLeft className="size-4" /> Back to Wash Report
          </Link>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-balance">
            Wash Filter Methodology
          </h1>
          <p className="mt-3 text-foreground/60 text-sm">
            Open methodology behind x402watch&apos;s wash detection.
            Version-controlled, deterministic, reproducible from public
            on-chain data.
          </p>
          <div className="mt-4">
            <Link
              href="https://github.com/printmoneylab/x402watch/blob/main/content/methodology.md"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-foreground/55 hover:text-foreground"
            >
              View source on GitHub <ExternalLink className="size-3" />
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-3xl px-6 py-10 sm:py-12">
          <article className="prose prose-invert prose-sm sm:prose-base max-w-none prose-headings:tracking-tight prose-headings:text-foreground prose-p:text-foreground/80 prose-li:text-foreground/80 prose-strong:text-foreground prose-a:text-accent hover:prose-a:underline prose-code:text-foreground/90 prose-code:font-mono prose-code:text-[0.92em] prose-code:before:content-none prose-code:after:content-none prose-pre:bg-foreground/[0.04] prose-pre:border prose-pre:border-foreground/10 prose-pre:rounded-lg prose-table:text-sm prose-th:text-foreground/85 prose-td:text-foreground/75 prose-hr:border-foreground/10">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
            >
              {md}
            </ReactMarkdown>
          </article>
        </div>
      </section>
    </main>
  );
}
