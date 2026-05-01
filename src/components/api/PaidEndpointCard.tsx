import { CodeBlock } from "./CodeBlock";

export type PaidEndpoint = {
  method: "GET" | "POST";
  path: string;
  priceUsd: number;
  useCase: string;
  description: string;
  request: string;
  responseShape: string;
  sample: string;
};

const fmtPrice = (p: number) => `$${p.toFixed(p < 0.01 ? 3 : 2)}`;

export function PaidEndpointCard({ ep }: { ep: PaidEndpoint }) {
  return (
    <details className="group rounded-lg border border-foreground/10 bg-foreground/[0.02] overflow-hidden">
      <summary className="cursor-pointer list-none flex items-center gap-3 p-4 hover:bg-foreground/[0.02] transition-colors">
        <span
          className={
            ep.method === "GET"
              ? "inline-flex items-center justify-center min-w-12 h-6 rounded text-[10px] font-mono uppercase tracking-wide border border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "inline-flex items-center justify-center min-w-12 h-6 rounded text-[10px] font-mono uppercase tracking-wide border border-amber-500/40 bg-amber-500/10 text-amber-300"
          }
        >
          {ep.method}
        </span>
        <code className="font-mono text-sm text-foreground/90 truncate flex-1">
          {ep.path}
        </code>
        <span className="font-mono text-sm text-foreground/85 shrink-0">
          {fmtPrice(ep.priceUsd)}
        </span>
        <span className="text-foreground/40 text-xs hidden sm:inline group-open:hidden">
          ▼
        </span>
        <span className="text-foreground/40 text-xs hidden sm:inline group-open:inline group-open:rotate-180">
          ▲
        </span>
      </summary>
      <div className="px-4 pb-5 pt-1 border-t border-foreground/5 space-y-4">
        <p className="text-sm text-foreground/70 leading-relaxed">
          {ep.description}
        </p>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
            Request
          </p>
          <CodeBlock lang="bash">{ep.request}</CodeBlock>
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
            Response shape
          </p>
          <CodeBlock lang="typescript">{ep.responseShape}</CodeBlock>
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
            Sample response
          </p>
          <CodeBlock lang="json">{ep.sample}</CodeBlock>
        </div>

        <p className="text-xs text-foreground/45">
          <span className="font-mono">Use case:</span> {ep.useCase}
        </p>
      </div>
    </details>
  );
}
