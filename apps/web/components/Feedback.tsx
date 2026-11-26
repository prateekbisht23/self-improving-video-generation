"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, ErrorBox, Field, inputCls } from "@/components/ui";
import { post } from "@/lib/api";
import type { MemoryResult, Render } from "@/lib/types";

type Kind = "accept" | "reject" | "comment" | "timestamp_issue" | "correction" | "choose";

const KINDS: { value: Kind; label: string; hint: string }[] = [
  { value: "accept", label: "👍 Accept", hint: "This edit is good." },
  { value: "reject", label: "👎 Reject", hint: "Not usable; say why if you can." },
  { value: "timestamp_issue", label: "Issue at a moment", hint: "Pause the preview where it goes wrong." },
  { value: "correction", label: "Correction", hint: "e.g. “captions should be at the top”, “cut faster”." },
  { value: "comment", label: "Comment", hint: "Anything else." },
  { value: "choose", label: "Prefer one render", hint: "Pick between two renders of this session." },
];

/**
 * Feedback goes to the memory graph: it extracts preferences, updates confidence, and may stop to ask the
 * creator to confirm a new preference (a LangGraph interrupt). Questions are answered right here.
 */
export function FeedbackForm({ sessionId, version, time, renders }: {
  sessionId: string;
  version: number;
  time: number;
  renders: (Render & { version: number })[];
}) {
  const [kind, setKind] = useState<Kind>("accept");
  const [text, setText] = useState("");
  const [start, setStart] = useState<number | null>(null);
  const [end, setEnd] = useState<number | null>(null);
  const [chosen, setChosen] = useState("");
  const [other, setOther] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MemoryResult | null>(null);
  const done = renders.filter((r) => r.status === "done");

  const needsText = kind === "comment" || kind === "correction" || kind === "timestamp_issue";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body: Record<string, unknown> = { kind, version, text: text.trim() || null };
      if (kind === "timestamp_issue") Object.assign(body, { start: start ?? time, end });
      if (kind === "choose") Object.assign(body, { chosen_render_id: chosen, other_render_id: other });
      const r = await post<{ feedback_id: string; memory: MemoryResult }>(`/edits/${sessionId}/feedback`, body);
      setResult(r.memory);
      setText("");
      setStart(null);
      setEnd(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {KINDS.filter((k) => k.value !== "choose" || done.length > 1).map((k) => (
            <button
              key={k.value}
              type="button"
              onClick={() => setKind(k.value)}
              className={`rounded-md border px-2 py-1 text-xs ${kind === k.value ? "border-accent bg-accent/10 text-accent" : "border-line hover:bg-line/60"}`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted">{KINDS.find((k) => k.value === kind)?.hint} Feedback applies to version v{version}.</p>

        {kind === "timestamp_issue" && (
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <Field label="From">
              <div className="flex gap-1">
                <input className={`${inputCls} w-24`} type="number" step="0.1" min={0} value={start ?? +time.toFixed(1)} onChange={(e) => setStart(+e.target.value)} />
                <Button type="button" variant="ghost" onClick={() => setStart(+time.toFixed(2))} title="use the preview's current time">
                  now
                </Button>
              </div>
            </Field>
            <Field label="To (optional)">
              <div className="flex gap-1">
                <input className={`${inputCls} w-24`} type="number" step="0.1" min={0} value={end ?? ""} onChange={(e) => setEnd(e.target.value === "" ? null : +e.target.value)} />
                <Button type="button" variant="ghost" onClick={() => setEnd(+time.toFixed(2))}>
                  now
                </Button>
              </div>
            </Field>
          </div>
        )}

        {kind === "choose" && (
          <div className="grid grid-cols-2 gap-2">
            <Field label="Better render">
              <select className={inputCls} value={chosen} onChange={(e) => setChosen(e.target.value)} required>
                <option value="">pick…</option>
                {done.map((r) => (
                  <option key={r.id} value={r.id}>
                    v{r.version} · {r.id.slice(0, 6)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Worse render">
              <select className={inputCls} value={other} onChange={(e) => setOther(e.target.value)} required>
                <option value="">pick…</option>
                {done.filter((r) => r.id !== chosen).map((r) => (
                  <option key={r.id} value={r.id}>
                    v{r.version} · {r.id.slice(0, 6)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}

        {kind !== "choose" && (
          <textarea
            className={inputCls}
            rows={2}
            maxLength={4000}
            required={needsText}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={needsText ? "What should change?" : "Optional: why?"}
          />
        )}
        <ErrorBox error={error} />
        <Button type="submit" disabled={busy || (needsText && !text.trim()) || (kind === "choose" && !(chosen && other))}>
          {busy ? "Sending… (the memory graph reads it)" : "Send feedback"}
        </Button>
      </form>
      {result && <MemoryOutcome result={result} />}
    </div>
  );
}

export function MemoryOutcome({ result }: { result: MemoryResult }) {
  const [answered, setAnswered] = useState<MemoryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const r = answered ?? result;

  async function answer(pid: string, a: "confirm" | "reject") {
    setError(null);
    try {
      setAnswered(await post<MemoryResult>(`/memory/confirmations/${r.thread_id}`, { answers: { [pid]: a } }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const { status, thread_id, questions, ...summary } = r;
  void thread_id;
  return (
    <div className="rounded-md border border-line bg-bg p-3 text-sm">
      <div className="mb-1 flex items-center gap-2">
        <span className="font-medium">Memory</span>
        <Badge>{status}</Badge>
      </div>
      {status === "awaiting_confirmation" && questions?.length ? (
        <ul className="space-y-2">
          {questions.map((q) => (
            <li key={q.preference_id}>
              <p>{q.question}</p>
              <div className="mt-1 flex gap-2">
                <Button onClick={() => answer(q.preference_id, "confirm")}>Remember it</Button>
                <Button variant="ghost" onClick={() => answer(q.preference_id, "reject")}>
                  No
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <SummaryLines summary={summary} />
      )}
      <ErrorBox error={error} />
      <Link href="/memory" className="mt-2 inline-block text-xs text-accent hover:underline">
        all remembered preferences →
      </Link>
    </div>
  );
}

// finish() in agent/graphs/memory_graph.py: {candidates, decisions: [{preference, action, id}], asked, answers}
function SummaryLines({ summary }: { summary: Record<string, unknown> }) {
  const decisions = (summary.decisions as { preference: string; action: string }[] | undefined) ?? [];
  const candidates = Number(summary.candidates ?? 0);
  if (!decisions.length)
    return <p className="text-muted">Recorded. {candidates ? `${candidates} candidate preference(s), none changed.` : "No preference read from this one."}</p>;
  return (
    <ul className="space-y-1 text-xs">
      {decisions.map((d, i) => (
        <li key={i}>
          <Badge tone="info">{d.action.replaceAll("_", " ")}</Badge> {d.preference}
        </li>
      ))}
    </ul>
  );
}

