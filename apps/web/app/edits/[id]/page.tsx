"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { EvaluationDiff, EvaluationReport } from "@/components/EvaluationReport";
import { FeedbackForm } from "@/components/Feedback";
import { type Marker, TimelineView } from "@/components/TimelineView";
import { Badge, Button, Card, Crumbs, Details, Empty, ErrorBox, inputCls, Json, Loading } from "@/components/ui";
import { api, post, videoUrl } from "@/lib/api";
import { clock, pct, short, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { EditDetail, Evaluation, EvaluationSummary, ProjectDetail, Timeline } from "@/lib/types";

const WORKING = new Set(["queued", "running"]);

export default function EditPage() {
  const { id } = useParams<{ id: string }>();
  const edit = useApi<EditDetail>(`/edits/${id}`, (e) => (WORKING.has(e.status) ? 3000 : null));
  const e = edit.data;

  // Renders, newest first, with the version they belong to.
  const renders = useMemo(
    () => (e?.versions ?? []).flatMap((v) => v.renders.map((r) => ({ ...r, version: v.version }))).reverse(),
    [e?.versions],
  );
  const latestDone = renders.find((r) => r.status === "done");

  // Evaluations run in the background after a render: poll until the latest render has one.
  const evals = useApi<EvaluationSummary[]>(e ? `/edits/${id}/evaluations` : null, (list) =>
    latestDone && !list.some((x) => x.render_id === latestDone.id) ? 5000 : null,
  );

  const [version, setVersion] = useState<number | null>(null);
  const [renderId, setRenderId] = useState<string | null>(null);
  const [evalId, setEvalId] = useState<string | null>(null);
  const shownVersion = version ?? e?.versions.at(-1)?.version ?? null;
  const shownRender = renderId ? renders.find((r) => r.id === renderId) : renders.find((r) => r.version === shownVersion && r.status === "done");
  const evalForRender = evals.data?.filter((x) => x.render_id === shownRender?.id).at(-1);
  const shownEvalId = evalId ?? evalForRender?.id ?? null;

  const timeline = useApi<Timeline>(e?.versions.length && shownVersion !== null ? `/edits/${id}/timeline?version=${shownVersion}` : null);
  const evaluation = useApi<Evaluation>(shownEvalId ? `/evaluations/${shownEvalId}` : null);
  const project = useApi<ProjectDetail>(e ? `/projects/${e.project_id}` : null);

  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(0);
  const seek = (t: number) => {
    if (video.current) {
      video.current.currentTime = t;
      video.current.play().catch(() => {});
    }
    setTime(t);
  };

  const markers: Marker[] = useMemo(() => {
    const ev = evaluation.data;
    if (!ev || ev.version !== shownVersion) return [];
    return ev.report.checks
      .filter((c) => c.passed === false)
      .flatMap((c) => c.evidence.filter((x) => x.start !== null).map((x) => ({ ...x, check: c.id })));
  }, [evaluation.data, shownVersion]);

  if (edit.error && !e) return <ErrorBox error={edit.error} onRetry={edit.reload} />;
  if (!e) return <Loading what="Loading edit" />;

  const pickVersion = (n: number) => {
    setVersion(n);
    setRenderId(null);
    setEvalId(null);
  };

  return (
    <div className="space-y-6">
      <div>
        <Crumbs items={[{ href: "/", label: "Projects" }, { href: `/projects/${e.project_id}`, label: project.data?.title ?? "Project" }, { label: `Edit ${short(e.id)}` }]} />
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="max-w-3xl text-lg">{e.instructions}</p>
          <Badge>{e.status}</Badge>
        </div>
        <p className="mt-1 text-xs text-muted">
          agent <span className="font-mono">{e.agent_version ?? "—"}</span>
          {e.constraints && ` · target ${e.constraints.min_duration}–${e.constraints.max_duration}s`}
          {e.trace_id && ` · trace ${short(e.trace_id)}`} · {when(e.created_at)}
        </p>
        <ErrorBox error={e.error} />
      </div>

      {WORKING.has(e.status) && <Progress edit={e} />}

      {!!e.versions.length && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
          <div className="space-y-4">
            <Card title="Preview">
              {shownRender?.status === "done" ? (
                <video
                  key={shownRender.id}
                  ref={video}
                  src={videoUrl(shownRender.id)}
                  controls
                  playsInline
                  onTimeUpdate={(ev) => setTime(ev.currentTarget.currentTime)}
                  className="aspect-[9/16] w-full rounded bg-black"
                />
              ) : (
                <div className="flex aspect-[9/16] w-full items-center justify-center rounded bg-line/50 p-4 text-center text-sm text-muted">
                  {WORKING.has(e.status) ? "Rendering…" : shownRender?.error ?? `v${shownVersion} has not been rendered.`}
                </div>
              )}
              {shownRender && (
                <p className="mt-2 text-xs text-muted">
                  render {short(shownRender.id)} · v{shownRender.version} · {clock(shownRender.duration)}
                </p>
              )}
            </Card>
            <Versions
              edit={e}
              shown={shownVersion}
              onPick={pickVersion}
              evals={evals.data ?? []}
              onRendered={edit.reload}
            />
          </div>

          <div className="min-w-0 space-y-4">
            <Card title={`Timeline · v${shownVersion}`}>
              <ErrorBox error={timeline.error} />
              {timeline.data ? <TimelineView timeline={timeline.data} time={time} markers={markers} onSeek={seek} /> : <Loading />}
            </Card>

            <Card
              title="Evaluation"
              actions={
                !!evals.data?.length && (
                  <select
                    className={`${inputCls} !w-auto text-xs`}
                    value={shownEvalId ?? ""}
                    onChange={(ev) => {
                      const x = evals.data!.find((y) => y.id === ev.target.value)!;
                      setEvalId(x.id);
                      setVersion(x.version);
                      setRenderId(x.render_id);
                    }}
                  >
                    {!shownEvalId && <option value="">pick an evaluation</option>}
                    {evals.data.map((x) => (
                      <option key={x.id} value={x.id}>
                        v{x.version} · {pct(x.pass_rate)} · {when(x.created_at)}
                      </option>
                    ))}
                  </select>
                )
              }
            >
              <ErrorBox error={evals.error ?? evaluation.error} />
              {evaluation.data ? (
                <EvaluationReport evaluation={evaluation.data} onSeek={evaluation.data.render_id === shownRender?.id ? seek : undefined} />
              ) : shownRender?.status === "done" && !evalForRender ? (
                <EvaluateNow renderId={shownRender.id} onQueued={evals.reload} waiting={shownRender.id === latestDone?.id} />
              ) : (
                <Empty>{WORKING.has(e.status) ? "The evaluation runs after the render." : "No evaluation for this version."}</Empty>
              )}
            </Card>

            {(evals.data?.length ?? 0) > 1 && <CompareEvaluations evals={evals.data!} />}

            <Card title="Feedback">
              {shownVersion !== null && <FeedbackForm sessionId={e.id} version={shownVersion} time={time} renders={renders} />}
            </Card>
          </div>
        </div>
      )}

      {!e.versions.length && !WORKING.has(e.status) && <Empty>The agent produced no timeline.</Empty>}

      <AgentLog edit={e} onChanged={edit.reload} />
    </div>
  );
}

function Progress({ edit }: { edit: EditDetail }) {
  const last = edit.actions.at(-1);
  return (
    <Card>
      <div className="flex items-center gap-3 text-sm">
        <span className="h-2 w-2 animate-ping rounded-full bg-accent" />
        <span>
          {edit.status === "queued" ? "Waiting for a worker…" : "The agent is editing"}
          {last && (
            <span className="text-muted">
              {" "}
              · step {last.step}: <span className="font-mono">{last.name}</span> {last.stage && `(${last.stage})`}
            </span>
          )}
        </span>
      </div>
      {edit.status === "queued" && (
        <p className="mt-2 text-xs text-muted">If this doesn&apos;t move, start a worker: uv run python -m services.worker.worker</p>
      )}
    </Card>
  );
}

function Versions({ edit, shown, onPick, evals, onRendered }: {
  edit: EditDetail;
  shown: number | null;
  onPick: (n: number) => void;
  evals: EvaluationSummary[];
  onRendered: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState<number[]>([]);
  // Re-renders run in the worker: refresh until every queued version has a render (done or failed).
  const waiting = queued.filter((n) => !edit.versions.find((v) => v.version === n)?.renders.length);
  useEffect(() => {
    if (!waiting.length) return;
    const t = setInterval(onRendered, 3000);
    return () => clearInterval(t);
  }, [waiting.length, onRendered]);
  async function render(n: number) {
    setError(null);
    try {
      await post(`/edits/${edit.id}/render?version=${n}`);
      setQueued((q) => [...q, n]);
    } catch (e) {
      setError(`v${n}: ${(e as Error).message}`);
    }
  }
  return (
    <Card title="Version history">
      <ErrorBox error={error} />
      <ul className="space-y-1">
        {[...edit.versions].reverse().map((v) => {
          const done = v.renders.filter((r) => r.status === "done");
          const ev = evals.filter((x) => x.version === v.version).at(-1);
          return (
            <li key={v.version}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => onPick(v.version)}
                onKeyDown={(k) => k.key === "Enter" && onPick(v.version)}
                className={`flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 text-sm ${shown === v.version ? "bg-accent/10" : "hover:bg-line/50"}`}
              >
                <span>
                  <span className="font-medium">v{v.version}</span>
                  <span className="ml-2 text-xs text-muted">by {v.created_by}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  {ev && <span className="text-xs text-muted">{pct(ev.pass_rate)}</span>}
                  {done.length ? (
                    <Badge tone="good">rendered</Badge>
                  ) : v.renders.length ? (
                    <Badge tone="bad">render failed</Badge>
                  ) : queued.includes(v.version) ? (
                    <Badge tone="warn">rendering</Badge>
                  ) : (
                    <button
                      className="text-xs text-accent hover:underline"
                      onClick={(k) => {
                        k.stopPropagation();
                        render(v.version);
                      }}
                    >
                      render
                    </button>
                  )}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-muted">The agent saves a version after each change; you can render or give feedback on any of them.</p>
    </Card>
  );
}

function EvaluateNow({ renderId, onQueued, waiting }: { renderId: string; onQueued: () => void; waiting: boolean }) {
  const [state, setState] = useState<"idle" | "queued" | string>("idle");
  async function go() {
    try {
      await post(`/renders/${renderId}/evaluate`);
      setState("queued");
      onQueued();
    } catch (e) {
      setState((e as Error).message);
    }
  }
  return (
    <div className="space-y-2 text-sm">
      <p className="text-muted">
        {waiting ? "Evaluating in the background (about a minute: deterministic checks, then the model judge)…" : "This render hasn't been evaluated."}
      </p>
      {state === "idle" && !waiting && <Button onClick={go}>Evaluate this render</Button>}
      {state === "queued" && <p className="text-muted">Queued.</p>}
      {state !== "idle" && state !== "queued" && <ErrorBox error={state} />}
    </div>
  );
}

function CompareEvaluations({ evals }: { evals: EvaluationSummary[] }) {
  const [a, setA] = useState(evals.at(-2)!.id);
  const [b, setB] = useState(evals.at(-1)!.id);
  const [pair, setPair] = useState<[Evaluation, Evaluation] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([api<Evaluation>(`/evaluations/${a}`), api<Evaluation>(`/evaluations/${b}`)])
      .then((p) => alive && setPair(p))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [a, b]);
  const opt = (x: EvaluationSummary) => (
    <option key={x.id} value={x.id}>
      v{x.version} · {pct(x.pass_rate)} · {when(x.created_at)}
    </option>
  );
  return (
    <Card title="Compare versions">
      <Details summary="Which checks changed between two evaluated versions">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <select className={`${inputCls} !w-auto`} value={a} onChange={(e) => setA(e.target.value)}>
            {evals.map(opt)}
          </select>
          →
          <select className={`${inputCls} !w-auto`} value={b} onChange={(e) => setB(e.target.value)}>
            {evals.map(opt)}
          </select>
        </div>
        <ErrorBox error={error} />
        {pair && <EvaluationDiff a={pair[0]} b={pair[1]} />}
      </Details>
    </Card>
  );
}

function AgentLog({ edit, onChanged }: { edit: EditDetail; onChanged: () => void }) {
  return (
    <Card title="What the agent did">
      <div className="space-y-3">
        {!!edit.memory_used?.length && (
          <div className="text-sm">
            <span className="text-muted">Preferences it applied: </span>
            {edit.memory_used.map((m, i) => (
              <Badge key={i} tone="info">
                {m.statement ?? JSON.stringify(m)}
              </Badge>
            ))}
          </div>
        )}
        <Details summary={`Action log (${edit.actions.length} steps)`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 pr-2 font-medium">#</th>
                  <th className="pr-2 font-medium">stage</th>
                  <th className="pr-2 font-medium">operation</th>
                  <th className="pr-2 font-medium">args</th>
                  <th className="pr-2 font-medium">version</th>
                  <th className="font-medium">result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line align-top">
                {edit.actions.map((a) => (
                  <tr key={a.step}>
                    <td className="py-1 pr-2">{a.step}</td>
                    <td className="pr-2 text-muted">{a.stage ?? a.source}</td>
                    <td className="pr-2 font-mono">{a.name}</td>
                    <td className="max-w-md truncate pr-2 font-mono text-muted" title={JSON.stringify(a.args)}>
                      {JSON.stringify(a.args)}
                    </td>
                    <td className="pr-2 whitespace-nowrap">
                      {a.version_before ?? "—"}→{a.version_after ?? "—"}
                    </td>
                    <td>{a.ok ? <Badge tone="good">ok</Badge> : <span className="text-bad">{a.error}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Details>
        {edit.plan && (
          <Details summary="Plan">
            <Json value={edit.plan} />
          </Details>
        )}
        {edit.agent_config && (
          <Details summary="Agent configuration used">
            <Json value={edit.agent_config} />
          </Details>
        )}
        {!WORKING.has(edit.status) && !!edit.versions.length && <ManualAction sessionId={edit.id} onDone={onChanged} />}
      </div>
    </Card>
  );
}

function ManualAction({ sessionId, onDone }: { sessionId: string; onDone: () => void }) {
  const [name, setName] = useState("");
  const [args, setArgs] = useState("{}");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function apply(ev: React.FormEvent) {
    ev.preventDefault();
    setMsg(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(args);
    } catch {
      setMsg({ ok: false, text: "args must be valid JSON" });
      return;
    }
    try {
      const v = await post<{ version: number }>(`/edits/${sessionId}/actions`, { name: name.trim(), args: parsed });
      setMsg({ ok: true, text: `created v${v.version}; render it from the version list` });
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  }
  return (
    <Details summary="Apply an operation by hand (same validation as the agent)">
      <form onSubmit={apply} className="flex flex-wrap items-start gap-2">
        <input className={`${inputCls} !w-48 font-mono`} placeholder="trim_clip" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={`${inputCls} !w-96 max-w-full font-mono`} value={args} onChange={(e) => setArgs(e.target.value)} />
        <Button type="submit" variant="ghost" disabled={!name.trim()}>
          Apply
        </Button>
      </form>
      <p className="mt-1 text-xs text-muted">Operation names and argument shapes match the agent&apos;s tools (see the action log above). An unknown name lists the valid ones.</p>
      {msg && <p className={`mt-1 text-xs ${msg.ok ? "text-good" : "text-bad"}`}>{msg.text}</p>}
    </Details>
  );
}
