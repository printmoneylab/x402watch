import {
  prettyPatternType,
  patternTone,
  type WashCaseStudy,
} from "@/lib/wash";
import { cn } from "@/lib/utils";

const PATTERN_BADGE: Record<string, string> = {
  rose:    "border-rose-500/40 bg-rose-500/10 text-rose-300",
  amber:   "border-amber-500/40 bg-amber-500/10 text-amber-300",
  orange:  "border-orange-500/40 bg-orange-500/10 text-orange-300",
  emerald: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  slate:   "border-slate-500/40 bg-slate-500/10 text-slate-300",
};

export function CaseStudyCard({ study }: { study: WashCaseStudy }) {
  const tone = patternTone(study.pattern_type);
  const isClean = study.pattern_type === "clean_organic";

  return (
    <article className="flex flex-col gap-3 rounded-lg border border-foreground/10 bg-foreground/[0.02] p-5">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide",
            PATTERN_BADGE[tone]
          )}
        >
          {prettyPatternType(study.pattern_type)}
        </span>
        {isClean ? (
          <span className="ml-auto inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/5 px-2 py-0.5 text-[10px] font-mono text-emerald-300/80">
            no wash flag
          </span>
        ) : (
          <span className="ml-auto font-mono text-[11px] text-foreground/45">
            confidence {study.confidence.toFixed(2)}
          </span>
        )}
      </div>

      <h3 className="text-base font-semibold tracking-tight text-foreground">
        Service {study.anonymous_id} — {prettyPatternType(study.pattern_type)}
      </h3>

      <div>
        <p className="text-xs font-medium text-foreground/55 mb-1.5">
          Pattern observed
        </p>
        <ul className="space-y-1 text-sm text-foreground/80">
          {study.details.map((d, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-foreground/30 select-none">·</span>
              <span>{d}</span>
            </li>
          ))}
        </ul>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-xs pt-2 border-t border-foreground/5">
        <div>
          <dt className="text-foreground/45">Buyers in cluster</dt>
          <dd className="font-mono text-foreground/85">
            {study.buyer_count.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt className="text-foreground/45">Wash classification</dt>
          <dd
            className={cn(
              "font-mono",
              study.wash_pct >= 50
                ? "text-rose-400"
                : study.wash_pct > 0
                ? "text-rose-300/70"
                : "text-emerald-300/80"
            )}
          >
            {study.wash_pct.toFixed(1)}%
          </dd>
        </div>
      </dl>

      {study.signals.length > 0 && (
        <div className="pt-2 border-t border-foreground/5">
          <p className="text-xs text-foreground/45 mb-1.5">
            Signals matched
          </p>
          <div className="flex flex-wrap gap-1.5">
            {study.signals.map((s) => (
              <span
                key={s}
                className="inline-flex items-center rounded border border-foreground/10 bg-foreground/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-foreground/70"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
