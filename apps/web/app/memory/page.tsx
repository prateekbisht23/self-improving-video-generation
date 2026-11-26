"use client";

import { useState } from "react";
import { MemoryOutcome } from "@/components/Feedback";
import { Badge, Button, Card, Details, Empty, ErrorBox, Field, inputCls, Loading, Meter } from "@/components/ui";
import { api, patch, post } from "@/lib/api";
import { when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Confirmation, Preference } from "@/lib/types";

export default function MemoryPage() {
  const [status, setStatus] = useState("");
  const prefs = useApi<Preference[]>(`/creators/me/preferences${status ? `?status=${status}` : ""}`);
  const pending = useApi<Confirmation[]>("/memory/confirmations");
  const reload = () => {
    prefs.reload();
    pending.reload();
  };

  const threads = Object.entries(
    (pending.data ?? []).reduce<Record<string, Confirmation[]>>((acc, c) => ({ ...acc, [c.thread_id]: [...(acc[c.thread_id] ?? []), c] }), {}),
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Creator memory</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Preferences learned from your feedback and edits. Each has a confidence that grows with supporting evidence, shrinks
          with contradictions and fades with time. New ones are only used once confident enough, or once you confirm them.
        </p>
      </div>

      {!!threads.length && (
        <Card title="Waiting for you">
          <ul className="space-y-3">
            {threads.map(([thread, qs]) => (
              <li key={thread}>
                <MemoryOutcome
                  result={{ status: "awaiting_confirmation", thread_id: thread, questions: qs.map((q) => ({ preference_id: q.preference_id, question: q.question })) }}
                />
              </li>
            ))}
          </ul>
          <Button variant="ghost" className="mt-3" onClick={reload}>
            Refresh
          </Button>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card
          title="Preferences"
          actions={
            <select className={`${inputCls} !w-auto text-xs`} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">all</option>
              <option value="active">active</option>
              <option value="candidate">candidate (not used yet)</option>
              <option value="session">this session only</option>
              <option value="stale">stale (contradicted)</option>
              <option value="rejected">rejected</option>
            </select>
          }
        >
          <ErrorBox error={prefs.error} onRetry={prefs.reload} />
          {prefs.loading && !prefs.data ? (
            <Loading />
          ) : prefs.data?.length ? (
            <ul className="divide-y divide-line">
              {prefs.data.map((p) => (
                <PreferenceRow key={p.id} pref={p} onChange={reload} />
              ))}
            </ul>
          ) : (
            <Empty>Nothing remembered yet. Give feedback on an edit, or add a preference.</Empty>
          )}
        </Card>
        <AddPreference onAdded={reload} />
      </div>
    </div>
  );
}

function PreferenceRow({ pref: p, onChange }: { pref: Preference; onChange: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<{ kind: string; detail: unknown; confidence_before: number | null; confidence_after: number | null; at: string }[] | null>(null);
  async function set(status: "active" | "rejected") {
    try {
      await patch(`/creators/me/preferences/${p.id}`, { status });
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{p.statement}</p>
          <p className="mt-0.5 font-mono text-xs text-muted">
            {p.category}.{p.attribute} = {p.value}
            {!!p.context.length && ` · when ${p.context.join(", ")}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge>{p.status}</Badge>
          {p.status !== "active" && (
            <Button variant="ghost" className="!px-2 !py-0.5 text-xs" onClick={() => set("active")}>
              confirm
            </Button>
          )}
          {p.status !== "rejected" && (
            <Button variant="ghost" className="!px-2 !py-0.5 text-xs" onClick={() => set("rejected")}>
              forget
            </Button>
          )}
        </div>
      </div>
      <div className="mt-2 flex items-center gap-3 text-xs text-muted">
        <span className="w-32">
          <Meter value={p.confidence} tone={p.confidence >= 0.7 ? "good" : "warn"} />
        </span>
        <span>confidence {p.confidence.toFixed(2)}</span>
        <span>
          +{p.support_count} / −{p.contradict_count}
        </span>
        <span>from {p.source}</span>
        <span>last seen {when(p.last_seen_at)}</span>
      </div>
      <ErrorBox error={error} />
      <div className="mt-1">
        <Details summary="history">
          {events === null ? (
            <Button
              variant="ghost"
              className="!px-2 !py-0.5 text-xs"
              onClick={() => api<typeof events>(`/creators/me/preferences/${p.id}/events`).then(setEvents).catch((e) => setError(e.message))}
            >
              load history
            </Button>
          ) : (
            <ul className="space-y-0.5 text-xs">
              {events.map((ev, i) => (
                <li key={i}>
                  <span className="text-muted">{when(ev.at)}</span> <span className="font-medium">{ev.kind}</span>{" "}
                  {ev.confidence_before !== null && ev.confidence_after !== null && (
                    <span className="text-muted">
                      {ev.confidence_before.toFixed(2)} → {ev.confidence_after.toFixed(2)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Details>
      </div>
    </li>
  );
}

function AddPreference({ onAdded }: { onAdded: () => void }) {
  const [statement, setStatement] = useState("");
  const [context, setContext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/creators/me/preferences", {
        statement: statement.trim(),
        context: context.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setStatement("");
      setContext("");
      onAdded();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title="Tell it directly">
      <form onSubmit={add} className="space-y-3">
        <Field label="Preference" hint="Read into category / attribute / value by a model, active immediately.">
          <input className={inputCls} value={statement} onChange={(e) => setStatement(e.target.value)} placeholder="Captions at the top" minLength={3} maxLength={300} required />
        </Field>
        <Field label="Only when" hint="optional, comma-separated context tags (e.g. tutorial, interview)">
          <input className={inputCls} value={context} onChange={(e) => setContext(e.target.value)} />
        </Field>
        <ErrorBox error={error} />
        <Button type="submit" disabled={busy || statement.trim().length < 3}>
          {busy ? "Adding…" : "Remember"}
        </Button>
      </form>
    </Card>
  );
}
