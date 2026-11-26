"use client";

import { useState } from "react";
import { Badge, Meter, PassBadge } from "@/components/ui";
import { clock, pct } from "@/lib/format";
import type { Check, Evaluation } from "@/lib/types";

const KIND_HINT: Record<string, string> = {
  deterministic: "measured from the file and timeline; same input, same result",
  signal: "computed signal (ASR, colour statistics…), thresholded",
  model: "judged by a model from frames/transcript; can vary between runs",
};

/** One evaluation: summary, quality dimensions, and every check with timestamped evidence. */
export function EvaluationReport({ evaluation: ev, onSeek }: { evaluation: Evaluation; onSeek?: (t: number) => void }) {
  const [onlyFailed, setOnlyFailed] = useState(true);
  const checks = ev.report.checks ?? [];
  const shown = checks.filter((c) => !onlyFailed || c.passed === false);
  const categories = Object.entries(ev.by_category).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div>
          <div className="text-3xl font-semibold">{pct(ev.pass_rate)}</div>
          <div className="text-xs text-muted">checks passed</div>
        </div>
        <div>
          <Badge tone={ev.technical_gate_passed ? "good" : "bad"}>{ev.technical_gate_passed ? "technically valid" : "technical gate failed"}</Badge>
          <div className="mt-1 text-xs text-muted">
            {ev.evaluator_version} · judge {ev.judge_model ?? "—"} · v{ev.version}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
        {categories.map(([name, c]) => (
          <div key={name}>
            <div className="flex justify-between text-xs">
              <span className="font-medium capitalize">{name}</span>
              <span className="text-muted">
                {c.passed}/{c.total}
              </span>
            </div>
            <Meter value={c.rate} tone={c.rate === 1 ? "good" : c.rate >= 0.5 ? "warn" : "bad"} />
          </div>
        ))}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Checks</h3>
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
            only failed ({checks.filter((c) => c.passed === false).length} of {checks.length})
          </label>
        </div>
        <ul className="divide-y divide-line rounded border border-line">
          {shown.map((c) => (
            <CheckRow key={c.id} check={c} onSeek={onSeek} />
          ))}
          {!shown.length && <li className="p-3 text-sm text-muted">Nothing failed.</li>}
        </ul>
      </div>
    </div>
  );
}

function CheckRow({ check: c, onSeek }: { check: Check; onSeek?: (t: number) => void }) {
  return (
    <li className="p-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <PassBadge passed={c.passed} />
        <span className="font-mono text-xs">{c.id}</span>
        <span title={KIND_HINT[c.kind]}>
          <Badge tone="muted">{c.kind}</Badge>
        </span>
        {c.passed === false && <Badge tone={c.severity === "critical" ? "bad" : c.severity === "major" ? "warn" : "muted"}>{c.severity}</Badge>}
        {c.score !== null && <span className="text-xs text-muted">score {c.score.toFixed(2)}</span>}
      </div>
      <p className="mt-1">{c.message}</p>
      {c.explanation && <p className="mt-1 text-xs text-muted">{c.explanation}</p>}
      {!!c.evidence.length && (
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {c.evidence.map((e, i) => (
            <li key={i}>
              <button
                type="button"
                disabled={!onSeek || e.start === null}
                onClick={() => e.start !== null && onSeek?.(e.start)}
                className="rounded border border-line px-1.5 py-0.5 text-left text-xs hover:border-accent disabled:cursor-default"
                title="jump to this moment in the preview"
              >
                {e.start !== null && (
                  <span className="mr-1 font-mono text-accent">
                    {clock(e.start)}
                    {e.end !== null && e.end !== e.start ? `–${clock(e.end)}` : ""}
                  </span>
                )}
                {e.detail}
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Two evaluations side by side: which checks changed between versions. */
export function EvaluationDiff({ a, b }: { a: Evaluation; b: Evaluation }) {
  const ids = Array.from(new Set([...a.report.checks.map((c) => c.id), ...b.report.checks.map((c) => c.id)])).sort();
  const get = (ev: Evaluation, id: string) => ev.report.checks.find((c) => c.id === id);
  const rows = ids.map((id) => ({ id, a: get(a, id), b: get(b, id) }));
  const changed = rows.filter((r) => (r.a?.passed ?? null) !== (r.b?.passed ?? null));
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-6">
        <span>
          pass rate {pct(a.pass_rate)} → <b>{pct(b.pass_rate)}</b>
        </span>
        <span className="text-muted">
          {changed.length} check{changed.length === 1 ? "" : "s"} changed
        </span>
      </div>
      <table className="w-full text-left text-xs">
        <thead className="text-muted">
          <tr>
            <th className="py-1 font-medium">check</th>
            <th className="font-medium">v{a.version} ({a.id.slice(0, 6)})</th>
            <th className="font-medium">v{b.version} ({b.id.slice(0, 6)})</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => {
            const diff = (r.a?.passed ?? null) !== (r.b?.passed ?? null);
            return (
              <tr key={r.id} className={diff ? "bg-accent/5" : ""}>
                <td className="py-1 font-mono">{r.id}</td>
                <td>{r.a ? <PassBadge passed={r.a.passed} /> : "—"}</td>
                <td title={r.b?.message}>{r.b ? <PassBadge passed={r.b.passed} /> : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
