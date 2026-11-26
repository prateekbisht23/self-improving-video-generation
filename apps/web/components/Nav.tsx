"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApi } from "@/lib/hooks";
import type { AgentVersion, Confirmation, Health } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Projects" },
  { href: "/memory", label: "Memory" },
  { href: "/improvement", label: "Improvement" },
  { href: "/improvement/compare", label: "Compare versions" },
];

export function Nav() {
  const path = usePathname();
  const health = useApi<Health>("/health", 15000);
  const versions = useApi<AgentVersion[]>("/improvement/versions");
  const pending = useApi<Confirmation[]>("/memory/confirmations", 15000);
  const active = versions.data?.find((v) => v.status === "active");
  const up = health.data?.status === "ok" && health.data?.db === "ok";

  const isOn = (href: string) =>
    href === "/" ? path === "/" || path.startsWith("/projects") || path.startsWith("/edits") : path === href || (href === "/improvement" && path.startsWith("/improvement/experiments"));

  return (
    <header className="border-b border-line bg-panel">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="font-semibold">
          Video Agent
        </Link>
        <nav className="flex flex-wrap gap-1 text-sm">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded px-2 py-1 ${isOn(l.href) ? "bg-line font-medium" : "text-muted hover:text-fg"}`}
            >
              {l.label}
              {l.href === "/memory" && !!pending.data?.length && (
                <span className="ml-1 rounded-full bg-accent px-1.5 text-xs text-white">{pending.data.length}</span>
              )}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-4 text-xs text-muted">
          {active && (
            <span title="the agent version new edits use">
              agent <span className="font-mono text-fg">{active.version}</span>
            </span>
          )}
          <span className="flex items-center gap-1.5" title={health.error ?? "API and database reachable"}>
            <span className={`h-2 w-2 rounded-full ${up ? "bg-good" : health.loading ? "bg-warn" : "bg-bad"}`} />
            {up ? "API ok" : health.loading ? "checking" : "API down"}
          </span>
        </div>
      </div>
    </header>
  );
}
