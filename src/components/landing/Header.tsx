"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, X, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/categories", label: "Categories" },
  { href: "/services", label: "Services" },
  { href: "/trends", label: "Trends" },
  { href: "/wash-report", label: "Wash Report" },
];

export function Header() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-foreground/10 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto max-w-6xl px-6 h-14 flex items-center justify-between">
        <Link href="/" className="font-semibold tracking-tight text-base">
          x402watch
        </Link>
        <nav className="hidden sm:flex items-center gap-6 text-sm">
          {NAV.map((n) => {
            const active =
              n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "transition-colors",
                  active ? "text-foreground" : "text-foreground/60 hover:text-foreground"
                )}
              >
                {n.label}
              </Link>
            );
          })}
          <Link
            href="https://github.com/printmoneylab/x402watch"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-foreground/60 hover:text-foreground transition-colors"
          >
            GitHub <ExternalLink className="size-3.5" />
          </Link>
        </nav>
        <button
          type="button"
          aria-label="Toggle navigation"
          onClick={() => setOpen((o) => !o)}
          className="sm:hidden h-9 w-9 inline-flex items-center justify-center rounded-md hover:bg-foreground/10"
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <nav className="sm:hidden border-t border-foreground/10 bg-background">
          <ul className="flex flex-col px-6 py-3 gap-1 text-sm">
            {NAV.map((n) => (
              <li key={n.href}>
                <Link
                  href={n.href}
                  className="block py-2 text-foreground/80 hover:text-foreground"
                  onClick={() => setOpen(false)}
                >
                  {n.label}
                </Link>
              </li>
            ))}
            <li>
              <Link
                href="https://github.com/printmoneylab/x402watch"
                target="_blank"
                rel="noopener noreferrer"
                className="block py-2 text-foreground/80 hover:text-foreground inline-flex items-center gap-1.5"
                onClick={() => setOpen(false)}
              >
                GitHub <ExternalLink className="size-3.5" />
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  );
}
