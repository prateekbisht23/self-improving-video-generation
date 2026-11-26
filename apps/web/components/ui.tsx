import Link from "next/link";
import type { ReactNode } from "react";

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-line bg-panel p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold tracking-wide uppercase text-muted">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const TONES: Record<string, string> = {
  good: "bg-good/15 text-good",
  bad: "bg-bad/15 text-bad",
  warn: "bg-warn/15 text-warn",
  info: "bg-accent/15 text-accent",
  muted: "bg-line text-muted",
};

const STATUS_TONE: Record<string, string> = {
  ready: "good", rendered: "good", done: "good", active: "good", promoted: "good", pass: "good", confirmed: "good",
  failed: "bad", rejected: "bad", fail: "bad", declined: "bad",
  queued: "warn", running: "warn", processing: "warn", uploaded: "warn", pending: "warn",
  awaiting_approval: "info", awaiting_confirmation: "info", candidate: "info", running_experiment: "warn",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const t = tone ?? STATUS_TONE[String(children)] ?? "muted";
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${TONES[t] ?? TONES.muted}`}>
      {String(children).replaceAll("_", " ")}
    </span>
  );
}

export function PassBadge({ passed }: { passed: boolean | null }) {
  if (passed === null) return <Badge tone="muted">n/a</Badge>;
  return <Badge tone={passed ? "good" : "bad"}>{passed ? "pass" : "fail"}</Badge>;
}

export function ErrorBox({ error, onRetry }: { error: string | null | undefined; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
      {error}
      {onRetry && (
        <button onClick={onRetry} className="ml-2 underline">
          retry
        </button>
      )}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="animate-pulse text-sm text-muted">{what}…</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

export function Button({ children, variant = "primary", className = "", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
}) {
  const v = {
    primary: "bg-accent text-white hover:opacity-90",
    ghost: "border border-line hover:bg-line/60",
    danger: "bg-bad text-white hover:opacity-90",
  }[variant];
  return (
    <button
      {...rest}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${v} ${className}`}
    >
      {children}
    </button>
  );
}

export const inputCls =
  "w-full rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm outline-none focus:border-accent focus:ring-1 focus:ring-accent";

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

/** Horizontal bar 0..1, used for pass rates and confidence. */
export function Meter({ value, tone = "accent" }: { value: number; tone?: "accent" | "good" | "bad" | "warn" }) {
  const c = { accent: "bg-accent", good: "bg-good", bad: "bg-bad", warn: "bg-warn" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded bg-line" aria-hidden>
      <div className={`h-full ${c}`} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

export function Crumbs({ items }: { items: { href?: string; label: string }[] }) {
  return (
    <nav className="mb-3 text-sm text-muted">
      {items.map((it, i) => (
        <span key={i}>
          {i > 0 && <span className="mx-1.5">/</span>}
          {it.href ? (
            <Link href={it.href} className="hover:text-fg hover:underline">
              {it.label}
            </Link>
          ) : (
            <span className="text-fg">{it.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function Details({ summary, children, open = false }: { summary: ReactNode; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="group">
      <summary className="cursor-pointer text-sm text-muted select-none hover:text-fg">{summary}</summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

export function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded bg-bg p-2 font-mono text-xs leading-relaxed">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
