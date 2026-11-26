"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { Badge, Button, Card, Crumbs, Details, Empty, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { api, post, upload } from "@/lib/api";
import { bytes, clock, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Asset, Edit, ProjectDetail } from "@/lib/types";

const BUSY_ASSET = new Set(["uploaded", "queued", "processing"]);

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const project = useApi<ProjectDetail>(`/projects/${id}`, (p) => (p.assets.some((a) => BUSY_ASSET.has(a.status)) ? 3000 : null));
  const edits = useApi<Edit[]>(`/projects/${id}/edits`, (es) => (es.some((e) => e.status === "queued" || e.status === "running") ? 4000 : null));

  if (project.error && !project.data) return <ErrorBox error={project.error} onRetry={project.reload} />;
  if (!project.data) return <Loading what="Loading project" />;
  const p = project.data;

  return (
    <div className="space-y-6">
      <div>
        <Crumbs items={[{ href: "/", label: "Projects" }, { label: p.title }]} />
        <h1 className="text-2xl font-semibold">{p.title}</h1>
        {p.description && <p className="mt-1 text-sm text-muted">{p.description}</p>}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Assets project={p} onChange={project.reload} />
        <NewEdit project={p} />
      </div>

      <Card title="Edits">
        <ErrorBox error={edits.error} onRetry={edits.reload} />
        {edits.data?.length ? (
          <ul className="divide-y divide-line">
            {edits.data.map((e) => (
              <li key={e.id}>
                <Link href={`/edits/${e.id}`} className="flex items-start justify-between gap-4 py-2.5 hover:text-accent">
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-sm">{e.instructions}</span>
                    <span className="mt-0.5 block font-mono text-xs text-muted">{e.agent_version ?? "—"}</span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <Badge>{e.status}</Badge>
                    <span className="text-xs text-muted">{when(e.created_at)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          !edits.loading && <Empty>No edits yet. Upload footage, wait until it is ready, then describe an edit.</Empty>
        )}
      </Card>

      <SceneSearch projectId={p.id} disabled={!p.assets.some((a) => a.status === "ready")} />
    </div>
  );
}

function Assets({ project, onChange }: { project: ProjectDetail; onChange: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<"source" | "reference">("source");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    try {
      for (const f of Array.from(files)) {
        const form = new FormData();
        form.append("file", f);
        form.append("kind", kind);
        setProgress(0);
        await upload<Asset>(`/projects/${project.id}/assets`, form, setProgress);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProgress(null);
      if (fileRef.current) fileRef.current.value = "";
      onChange();
    }
  }

  async function retry(a: Asset) {
    try {
      await post(`/assets/${a.id}/process`);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Card title="Footage">
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="Upload as">
          <select className={inputCls} value={kind} onChange={(e) => setKind(e.target.value as "source" | "reference")}>
            <option value="source">source footage</option>
            <option value="reference">reference (style to match)</option>
          </select>
        </Field>
        <input ref={fileRef} type="file" accept="video/*,.mkv" multiple hidden onChange={(e) => send(e.target.files)} />
        <Button onClick={() => fileRef.current?.click()} disabled={progress !== null}>
          {progress === null ? "Upload video…" : `Uploading ${Math.round(progress * 100)}%`}
        </Button>
      </div>
      <p className="mb-3 text-xs text-muted">mp4, mov, m4v, webm or mkv, 1 s to 10 min. Processing (scenes, transcript, audio) runs in the background.</p>
      <ErrorBox error={error} />
      {project.assets.length ? (
        <ul className="mt-2 divide-y divide-line">
          {project.assets.map((a) => (
            <AssetRow key={a.id} asset={a} onRetry={() => retry(a)} />
          ))}
        </ul>
      ) : (
        <Empty>No footage yet.</Empty>
      )}
    </Card>
  );
}

function AssetRow({ asset: a, onRetry }: { asset: Asset; onRetry: () => void }) {
  const detail = useApi<Asset>(BUSY_ASSET.has(a.status) || a.status === "failed" ? `/assets/${a.id}` : null, BUSY_ASSET.has(a.status) ? 3000 : undefined);
  const stages = detail.data?.stages;
  return (
    <li className="py-2.5 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate">
          <span className="font-medium">{a.original_filename}</span>
          <span className="ml-2 text-xs text-muted">
            {a.kind} · {bytes(a.size_bytes)}
            {a.duration ? ` · ${clock(a.duration)}` : ""}
            {a.width ? ` · ${a.width}×${a.height}` : ""}
            {a.has_audio === false ? " · no audio" : ""}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <Badge>{a.status}</Badge>
          {a.status === "failed" && (
            <Button variant="ghost" onClick={onRetry} className="!px-2 !py-0.5 text-xs">
              retry
            </Button>
          )}
        </span>
      </div>
      {a.last_error && <p className="mt-1 text-xs text-bad">{a.last_error}</p>}
      {stages && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {stages.map((s) => (
            <span key={s.name} title={s.error ?? ""}>
              <Badge tone={s.status === "done" ? "good" : s.status === "failed" ? "bad" : s.status === "running" ? "warn" : "muted"}>
                {s.name}
              </Badge>
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function NewEdit({ project }: { project: ProjectDetail }) {
  const router = useRouter();
  const ready = project.assets.filter((a) => a.status === "ready");
  const sources = ready.filter((a) => a.kind === "source");
  const references = ready.filter((a) => a.kind === "reference");
  const [instructions, setInstructions] = useState("");
  const [picked, setPicked] = useState<string[] | null>(null); // null = all ready sources
  const [reference, setReference] = useState("");
  const [minD, setMinD] = useState(15);
  const [maxD, setMaxD] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chosen = useMemo(() => picked ?? sources.map((a) => a.id), [picked, sources]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ed = await post<Edit>(`/projects/${project.id}/edits`, {
        instructions: instructions.trim(),
        source_asset_ids: chosen,
        reference_asset_id: reference || null,
        min_duration: minD,
        max_duration: maxD,
      });
      router.push(`/edits/${ed.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <Card title="New edit">
      {!sources.length ? (
        <Empty>Upload source footage and wait until it shows “ready”.</Empty>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <Field label="Instructions" hint="What should the short be about? Pacing, captions, look, what to include.">
            <textarea
              className={inputCls}
              rows={4}
              minLength={5}
              maxLength={4000}
              required
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="A 20-second teaser about the launch: open on the most dramatic shot, keep the countdown audio, captions on."
            />
          </Field>
          {sources.length > 1 && (
            <fieldset className="text-sm">
              <legend className="mb-1 font-medium">Source footage</legend>
              {sources.map((a) => (
                <label key={a.id} className="mr-4 inline-flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={chosen.includes(a.id)}
                    onChange={(e) => setPicked(e.target.checked ? [...chosen, a.id] : chosen.filter((x) => x !== a.id))}
                  />
                  {a.original_filename}
                </label>
              ))}
            </fieldset>
          )}
          <Field label="Reference video" hint="The agent matches its pacing, captions and colour.">
            <select className={inputCls} value={reference} onChange={(e) => setReference(e.target.value)}>
              <option value="">none</option>
              {references.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.original_filename}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Min length (s)">
              <input className={inputCls} type="number" min={3} max={180} value={minD} onChange={(e) => setMinD(+e.target.value)} />
            </Field>
            <Field label="Max length (s)">
              <input className={inputCls} type="number" min={3} max={180} value={maxD} onChange={(e) => setMaxD(+e.target.value)} />
            </Field>
          </div>
          <ErrorBox error={error} />
          <Button type="submit" disabled={busy || instructions.trim().length < 5 || !chosen.length || minD > maxD}>
            {busy ? "Starting…" : "Generate edit"}
          </Button>
        </form>
      )}
    </Card>
  );
}

type Hit = { scene: { id: string; asset_id: string; index: number; start: number; end: number; description: string | null; tags: string[]; transcript_text: string | null }; score: number; matched_by: string[] };

function SceneSearch({ projectId, disabled }: { projectId: string; disabled: boolean }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setHits(await api<Hit[]>(`/projects/${projectId}/search?q=${encodeURIComponent(q)}&k=8`));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Card title="What the agent sees">
      <Details summary="Search the analysed scenes (text and meaning) — the same index the planner uses">
        <form onSubmit={search} className="flex gap-2">
          <input className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} placeholder="rocket on the launch pad" disabled={disabled} />
          <Button type="submit" disabled={disabled || !q.trim()}>
            Search
          </Button>
        </form>
        <ErrorBox error={error} />
        {hits && (
          <ul className="mt-3 space-y-2 text-sm">
            {!hits.length && <Empty>No matching scenes.</Empty>}
            {hits.map((h) => (
              <li key={h.scene.id} className="rounded border border-line p-2">
                <div className="flex justify-between text-xs text-muted">
                  <span>
                    scene {h.scene.index} · {clock(h.scene.start)}–{clock(h.scene.end)}
                  </span>
                  <span>
                    {h.matched_by.join(" + ")} · {h.score.toFixed(3)}
                  </span>
                </div>
                <p className="mt-1">{h.scene.description}</p>
                {h.scene.transcript_text && <p className="mt-1 text-xs text-muted italic">“{h.scene.transcript_text}”</p>}
              </li>
            ))}
          </ul>
        )}
      </Details>
    </Card>
  );
}
