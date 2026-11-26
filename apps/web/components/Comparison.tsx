"use client";

import { useState } from "react";
import { Badge } from "@/components/ui";
import { pct, signed } from "@/lib/format";
import type { Comparison, Delta, Paired } from "@/lib/types";

const METRIC_LABEL: Record<string, string> = {
  mean_pass_rate: "mean pass rate",
  completion_rate: "rendered (completion)",
  technical_valid_rate: "technically valid",
  mean_actions: "actions per task",
  repairs_per_task: "repairs per task",
};
const RATE = new Set(["mean_pass_rate", "completion_rate", "technical_valid_rate"]);
const LOWER_IS_BETTER = new Set(["mean_actions", "repairs_per_task"]);

function tone(delta: number | null, lowerBetter = false) {
  if (delta === null || Math.abs(delta) < 1e-9) return "";
  return (delta > 0) !== lowerBetter ? "text-good" : "text-bad";
}

export function MetricsTable({ metrics, afterRerun }: { metrics: Record<string, Delta>; afterRerun?: Record<string, Delta> }) {
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-xs text-muted">
        <tr>
          <th className="py-1 font-medium">metric</th>
          <th className="font-medium">baseline</th>
          <th className="font-medium">candidate</th>
          <th className="font-medium">Δ</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {Object.entries(metrics)
          .filter(([, m]) => m.baseline !== null || m.candidate !== null)
          .map(([k, m]) => {
          const fmt = (x: number | null) => (RATE.has(k) ? pct(x, 1) : x?.toFixed(2) ?? "—");
          const rr = afterRerun?.[k];
          return (
            <tr key={k}>
              <td className="py-1">{METRIC_LABEL[k] ?? k}</td>
              <td>{fmt(m.baseline)}</td>
              <td>
                {fmt(m.candidate)}
                {rr && rr.candidate !== m.candidate && <span className="ml-1 text-xs text-muted" title="after confirmation re-runs of flaky tasks">({fmt(rr.candidate)} after re-run)</span>}
              </td>
              <td className={tone(m.delta, LOWER_IS_BETTER.has(k))}>{RATE.has(k) ? signed(m.delta === null ? null : m.delta * 100, 1) + " pp" : signed(m.delta, 2)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Per-check pass rates, with the A/A control's flip count next to each when the experiment was scoped. */
export function ChecksTable({ checks, control, targets = [] }: {
  checks: Record<string, Delta>;
  control?: Record<string, { n: number; flips: number }>;
  targets?: string[];
}) {
  const [all, setAll] = useState(false);
  const rows = Object.entries(checks)
    .filter(([, d]) => d.n !== 0)
    .sort(([, a], [, b]) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0));
  const shown = all ? rows : rows.filter(([k, d]) => (d.delta ?? 0) !== 0 || targets.includes(k));
  return (
    <div>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>
            <th className="py-1 font-medium">check</th>
            <th className="pr-3 font-medium">n</th>
            <th className="font-medium">baseline</th>
            <th className="font-medium">candidate</th>
            <th className="font-medium">Δ</th>
            {control && (
              <th className="font-medium" title="identical code on out-of-scope tasks: how often this check flips by chance">
                A/A flips
              </th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {shown.map(([k, d]) => (
            <tr key={k}>
              <td className="py-1 pr-3 font-mono text-xs">
                {k} {targets.includes(k) && <Badge tone="info">target</Badge>}
              </td>
              <td className="pr-3 text-xs text-muted">{d.n}</td>
              <td>{pct(d.baseline)}</td>
              <td>{pct(d.candidate)}</td>
              <td className={tone(d.delta)}>{d.delta === null ? "—" : `${signed(d.delta * 100, 0)} pp`}</td>
              {control && <td className="text-xs text-muted">{control[k] ? `${control[k].flips}/${control[k].n}` : "—"}</td>}
            </tr>
          ))}
          {!shown.length && (
            <tr>
              <td colSpan={6} className="py-2 text-xs text-muted">
                No check changed.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <label className="mt-2 flex items-center gap-1.5 text-xs text-muted">
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> show unchanged checks ({rows.length} total)
      </label>
    </div>
  );
}

/** Per-task paired differences (candidate − baseline pass rate) with the bootstrap CI of the mean. */
export function PairedChart({ paired, highlight = [] }: { paired: Paired; highlight?: string[] }) {
  const rows = Object.entries(paired.per_task).sort(([, a], [, b]) => b - a);
  const max = Math.max(0.1, ...rows.map(([, v]) => Math.abs(v)));
  return (
    <div className="text-xs">
      <p className="mb-2">
        mean <b className={tone(paired.mean_diff)}>{signed(paired.mean_diff)}</b> · 95% CI [{signed(paired.ci95[0])}, {signed(paired.ci95[1])}] ·{" "}
        {paired.wins} better / {paired.losses} worse / {paired.ties} same
        {paired.ci95[0] <= 0 && paired.ci95[1] >= 0 && <span className="text-muted"> — CI includes 0: no overall difference shown</span>}
      </p>
      <ul className="space-y-0.5">
        {rows.map(([task, v]) => (
          <li key={task} className="grid grid-cols-[4rem_1fr_1fr_3.5rem] items-center gap-1">
            <span className={`font-mono ${highlight.includes(task) ? "font-semibold text-accent" : "text-muted"}`}>{task}</span>
            <span className="flex justify-end">{v < 0 && <span className="h-2.5 rounded-l bg-bad" style={{ width: `${(-v / max) * 100}%` }} />}</span>
            <span>{v > 0 && <span className="block h-2.5 rounded-r bg-good" style={{ width: `${(v / max) * 100}%` }} />}</span>
            <span className={`text-right ${tone(v)}`}>{signed(v, 2)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SplitBlock({ c }: { c: Comparison }) {
  return (
    <ul className="flex flex-wrap gap-4 text-xs">
      {Object.entries(c.by_split ?? {}).map(([s, d]) => (
        <li key={s}>
          <span className="text-muted">{s}</span> (n={d.n}) {pct(d.baseline, 1)} → {pct(d.candidate, 1)}
        </li>
      ))}
    </ul>
  );
}
