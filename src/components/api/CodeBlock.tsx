import { cn } from "@/lib/utils";

export function CodeBlock({
  children,
  lang,
  className,
}: {
  children: string;
  lang?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-foreground/10 bg-foreground/[0.03]",
        className
      )}
    >
      {lang && (
        <div className="px-4 pt-2 pb-1 text-[10px] uppercase tracking-wide font-mono text-foreground/40">
          {lang}
        </div>
      )}
      <pre className="px-4 py-3 overflow-x-auto text-xs sm:text-[13px] leading-relaxed">
        <code className="font-mono text-foreground/85 whitespace-pre">
          {children}
        </code>
      </pre>
    </div>
  );
}
