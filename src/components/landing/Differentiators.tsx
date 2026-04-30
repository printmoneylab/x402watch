import { ShieldCheck, Database, Clock, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

type Card = {
  Icon: typeof ShieldCheck;
  title: string;
  body: string;
  /** Tailwind colour class (icon stroke + top border accent) */
  accent: string;
};

const cards: Card[] = [
  {
    Icon: ShieldCheck,
    title: "Wash-Filtered",
    body:
      "Cohort-signal detection catches sophisticated sybil farms. 8 labels per buyer. Methodology open-source.",
    accent: "rose",
  },
  {
    Icon: Database,
    title: "Free Public Data",
    body:
      "Every label, category, benchmark — free. Daily snapshots committed to GitHub under CC0.",
    accent: "emerald",
  },
  {
    Icon: Clock,
    title: "Time-Series Intelligence",
    body:
      "30 days of indexed history. Daily commits. Verifiable, longitudinal data.",
    accent: "sky",
  },
  {
    Icon: Bot,
    title: "AI-Native",
    body:
      "x402 API. MCP server. llms.txt. Built for agents, not humans.",
    accent: "violet",
  },
];

const ACCENT_CLASSES: Record<string, { border: string; icon: string; ring: string }> = {
  rose:    { border: "border-t-rose-500/70",    icon: "text-rose-400",    ring: "hover:shadow-[0_0_0_1px_rgba(244,63,94,0.35)]" },
  emerald: { border: "border-t-emerald-500/70", icon: "text-emerald-400", ring: "hover:shadow-[0_0_0_1px_rgba(16,185,129,0.35)]" },
  sky:     { border: "border-t-sky-500/70",     icon: "text-sky-400",     ring: "hover:shadow-[0_0_0_1px_rgba(14,165,233,0.35)]" },
  violet:  { border: "border-t-violet-500/70",  icon: "text-violet-400",  ring: "hover:shadow-[0_0_0_1px_rgba(139,92,246,0.35)]" },
};

export function Differentiators() {
  return (
    <section className="border-y border-foreground/15 sm:border-y-0 sm:border-b sm:border-foreground/10 bg-foreground/[0.12] sm:bg-foreground/[0.08]">
      <div className="mx-auto max-w-6xl px-6 py-24 sm:py-28">
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight mb-12">
          Four axes of difference.
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {cards.map(({ Icon, title, body, accent }) => {
            const a = ACCENT_CLASSES[accent];
            return (
              <div
                key={title}
                className={cn(
                  "flex flex-col gap-4 rounded-lg border border-foreground/10 border-t-4 bg-foreground/[0.02] p-6 transition-shadow",
                  a.border,
                  a.ring
                )}
              >
                <Icon className={cn("size-6", a.icon)} strokeWidth={1.75} />
                <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
                <p className="text-sm text-foreground/70 leading-relaxed">{body}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
