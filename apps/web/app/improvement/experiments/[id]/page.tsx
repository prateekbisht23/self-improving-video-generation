"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ChecksTable, MetricsTable, PairedChart, SplitBlock } from "@/components/Comparison";
import { Markdown } from "@/components/Markdown";
import { Badge, Button, Card, Crumbs, Details, ErrorBox, Field, inputCls, Json, Loading } from "@/components/ui";
import { post } from "@/lib/api";
import { short, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Comparison, Experiment } from "@/lib/types";

export default function ExperimentPage() {
  const { id } = useParams<{ id: string }>();
  const exp = useApi<Experiment>(`/improvement/experiments/${id}`, (e) => (e.status === "running" ? 10000 : null));
  const [view, setView] = useState<"scope" | "all">("scope");

  if (exp.error && !exp.data) return <ErrorBox error={exp.error} onRetry={exp.reload} />;
  if (!exp.data) return <Loading what="Loading experiment" />;
  const e = exp.data;
  const c = e.comparison;
  const g = e.gates;
  const ch = e.change ?? {};
  const scoped = !!c?.scope;
  const useScope = scoped && view === "scope";

  return (
    <div className="space-y-6">
      <div>
        <Crumbs items={[{ href: "/improvement", label: "Improvement" }, { label: `Experiment ${short(e.id)}` }]} />
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg">
            {e.baseline_version} <span className="text-muted">vs</span> {e.candidate_version}
          </h1>
          <Badge>{e.status}</Badge>
        </div>
        <p className="mt-1 text-xs text-muted">
          dataset {e.dataset_version} · evaluator {e.evaluator_version} · splits {e.splits.join(" + ")} · {e.n_runs} run(s) per version · {when(e.created_at)} ·{" "}
          <Link className="text-accent hover:underline" href={`/improvement/compare?a=${encodeURIComponent(e.baseline_version)}&b=${encodeURIComponent(e.candidate_version)}`}>
            config diff
          </Link>
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card title="Candidate strategy">
          <p className="text-sm">{ch.hypothesis ?? "—"}</p>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-muted">origin</dt>
            <dd>{ch.origin === "human" ? `human (${ch.submitted_by})` : "improvement loop"}</dd>
            <dt className="text-muted">targets</dt>
            <dd className="font-mono text-xs">{ch.targets?.join(", ") ?? "—"}</dd>
            <dt className="text-muted">policy changes</dt>
            <dd className="font-mono text-xs">
              {Object.entries(ch.policy_changes ?? {}).map(([k, v]) => (
                <div key={k}>
                  {k} = {JSON.stringify(v)}
                </div>
              ))}
            </dd>
            {ch.planner_addendum && (
              <>
                <dt className="text-muted">planner prompt +</dt>
                <dd className="text-xs">{ch.planner_addendum}</dd>
              </>
            )}
            <dt className="text-muted">expected</dt>
            <dd>{ch.expected_effect ?? "—"}</dd>
            <dt className="text-muted">risks</dt>
            <dd>{ch.risks ?? "—"}</dd>
          </dl>
        </Card>
        <Decision exp={e} onDone={exp.reload} />
      </div>

      {g && (
        <Card title="Regression gates" actions={<Badge tone={g.eligible ? "good" : "bad"}>{g.eligible ? "eligible for a decision" : "rejected by gates"}</Badge>}>
          <div className="grid gap-4 md:grid-cols-3">
            <GateList title="Critical (must be empty)" items={g.critical} bad />
            <GateList title="Regressions beyond noise" items={g.regressions} bad />
            <GateList title="Improvements" items={g.improvements} />
          </div>
          {!!g.notes.length && (
            <div className="mt-4">
              <Details summary={`Notes (${g.notes.length}): what was looked at and why it didn't gate`}>
                <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
                  {g.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </Details>
            </div>
          )}
          <div className="mt-2">
            <Details summary="Thresholds">
              <Json value={g.thresholds} />
            </Details>
          </div>
        </Card>
      )}

      {c && (
        <Card
          title="Baseline vs candidate · development + validation"
          actions={
            scoped && (
              <div className="flex rounded-md border border-line text-xs">
                {(["scope", "all"] as const).map((v) => (
                  <button key={v} onClick={() => setView(v)} className={`px-2 py-1 ${view === v ? "bg-line font-medium" : "text-muted"}`}>
                    {v === "scope" ? `in scope (${c.scope!.name}, ${c.scope!.task_ids?.length ?? c.scope!.tasks} tasks)` : `all ${c.tasks} tasks`}
                  </button>
                ))}
              </div>
            )
          }
        >
          {scoped && (
            <p className="mb-3 text-xs text-muted">
              This change can only affect “{c.scope!.name}” tasks. The other tasks ran the baseline&apos;s code, so any change there is
              chance; that A/A control measures how noisy each check is.
            </p>
          )}
          <ComparisonBody c={c} useScope={useScope} targets={ch.targets ?? []} />
        </Card>
      )}

      {e.holdout && (
        <Card title="Held-out tasks (never seen by diagnosis or gates)">
          <ComparisonBody c={e.holdout} useScope={useScope && !!e.holdout.scope} targets={ch.targets ?? []} />
        </Card>
      )}

      {e.report && (
        <Card title="Full report">
          <Details summary="The markdown report written for the reviewer">
            <Markdown>{e.report}</Markdown>
          </Details>
        </Card>
      )}
    </div>
  );
}

function ComparisonBody({ c, useScope, targets }: { c: Comparison; useScope: boolean; targets: string[] }) {
  const s = useScope ? c.scope : undefined;
  const metrics = s?.metrics ?? c.metrics;
  const checks = s?.checks ?? c.checks;
  const paired = s?.paired ?? c.paired;
  const failed = s?.newly_failed ?? c.newly_failed;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <MetricsTable metrics={metrics} afterRerun={useScope ? undefined : c.after_rerun} />
        {!!failed?.length && (
          <p className="text-xs text-bad">
            newly failed to render: {failed.join(", ")}
            {!useScope && c.flaky?.length ? ` · flaky on re-run: ${c.flaky.join(", ")}` : ""}
          </p>
        )}
        {!useScope && <SplitBlock c={c} />}
        <ChecksTable checks={checks} control={c.control?.checks} targets={targets} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold">Per task: candidate − baseline pass rate</h3>
        {paired && <PairedChart paired={paired} highlight={c.scope?.task_ids ?? []} />}
      </div>
    </div>
  );
}

function GateList({ title, items, bad }: { title: string; items: string[]; bad?: boolean }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-medium text-muted">{title}</h3>
      {items.length ? (
        <ul className={`space-y-1 text-sm ${bad ? "text-bad" : "text-good"}`}>
          {items.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">none</p>
      )}
    </div>
  );
}

function Decision({ exp: e, onDone }: { exp: Experiment; onDone: () => void }) {
  const [by, setBy] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approve" | "decline") {
    const verb = decision === "approve" ? `Promote ${e.candidate_version}? New edits will use it.` : "Decline this candidate?";
    if (!window.confirm(verb)) return;
    setBusy(true);
    setError(null);
    try {
      await post(`/improvement/experiments/${e.id}/decision`, { decision, by: by.trim(), note: note.trim() });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (e.status !== "awaiting_approval")
    return (
      <Card title="Decision">
        {e.decision_by ? (
          <div className="space-y-1 text-sm">
            <p>
              <Badge>{e.status}</Badge> by <b>{e.decision_by}</b>
            </p>
            <p className="text-xs text-muted">{when(e.decided_at)}</p>
            {e.decision_note && <p className="text-sm italic">“{e.decision_note}”</p>}
          </div>
        ) : (
          <p className="text-sm text-muted">
            {e.status === "rejected" ? "The gates rejected this candidate; it never reached a human." : `Status: ${e.status.replaceAll("_", " ")}.`}
          </p>
        )}
      </Card>
    );

  return (
    <Card title="Your decision" className="border-accent/60">
      <p className="mb-3 text-sm text-muted">The gates passed and the holdout ran. Promote only if the evidence convinces you.</p>
      <div className="space-y-3">
        <Field label="Your name">
          <input className={inputCls} value={by} onChange={(x) => setBy(x.target.value)} maxLength={64} />
        </Field>
        <Field label="Note" hint="Recorded with the decision.">
          <textarea className={inputCls} rows={3} value={note} onChange={(x) => setNote(x.target.value)} maxLength={2000} />
        </Field>
        <ErrorBox error={error} />
        <div className="flex gap-2">
          <Button disabled={busy || !by.trim()} onClick={() => decide("approve")}>
            Approve &amp; promote
          </Button>
          <Button variant="danger" disabled={busy || !by.trim()} onClick={() => decide("decline")}>
            Decline
          </Button>
        </div>
      </div>
    </Card>
  );
}
