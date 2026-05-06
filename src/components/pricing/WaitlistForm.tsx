"use client";

import { useState, type FormEvent } from "react";
import { Loader2, Check } from "lucide-react";
import { cn } from "@/lib/utils";

type State =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success"; duplicate: boolean }
  | { kind: "error"; message: string };

export function WaitlistForm() {
  const [email, setEmail] = useState("");
  const [useCase, setUseCase] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (state.kind === "submitting") return;
    setState({ kind: "submitting" });
    try {
      const r = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, useCase }),
      });
      const data = (await r.json().catch(() => ({}))) as {
        error?: string;
        duplicate?: boolean;
      };
      if (!r.ok) {
        setState({ kind: "error", message: data.error || `error ${r.status}` });
        return;
      }
      setState({ kind: "success", duplicate: !!data.duplicate });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "network error",
      });
    }
  }

  if (state.kind === "success") {
    return (
      <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/[0.06] p-5">
        <div className="flex items-center gap-2 text-emerald-300">
          <Check className="size-5" />
          <p className="font-semibold">
            {state.duplicate
              ? "You're already on the list."
              : "You're on the list."}
          </p>
        </div>
        <p className="mt-2 text-sm text-foreground/70">
          We&apos;ll email you when Pro is ready, with the early-access 50% off
          baked in for first-wave signups.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div>
        <label
          htmlFor="wl-email"
          className="block text-xs uppercase tracking-wide text-foreground/55 mb-1.5"
        >
          Email
        </label>
        <input
          id="wl-email"
          type="email"
          name="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="w-full h-10 px-3 rounded-md bg-foreground/5 border border-foreground/15 text-sm placeholder:text-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </div>
      <div>
        <label
          htmlFor="wl-use-case"
          className="block text-xs uppercase tracking-wide text-foreground/55 mb-1.5"
        >
          What would you use it for? (optional)
        </label>
        <input
          id="wl-use-case"
          type="text"
          name="useCase"
          maxLength={280}
          value={useCase}
          onChange={(e) => setUseCase(e.target.value)}
          placeholder="Monitoring my service / due diligence / agent integration / …"
          className="w-full h-10 px-3 rounded-md bg-foreground/5 border border-foreground/15 text-sm placeholder:text-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </div>

      <button
        type="submit"
        disabled={state.kind === "submitting" || !email}
        className={cn(
          "inline-flex items-center justify-center gap-2 h-10 px-5 rounded-md text-sm font-medium",
          "bg-accent text-background hover:opacity-90 transition-opacity",
          "disabled:opacity-40 disabled:pointer-events-none"
        )}
      >
        {state.kind === "submitting" && (
          <Loader2 className="size-4 animate-spin" />
        )}
        Join wait list
      </button>

      {state.kind === "error" && (
        <p className="text-xs text-rose-400">{state.message}</p>
      )}
      <p className="text-[11px] text-foreground/45 leading-relaxed">
        We only use this to email you when Pro launches. No marketing spam, no
        sharing.
      </p>
    </form>
  );
}
