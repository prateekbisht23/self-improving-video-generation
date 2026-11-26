"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, Empty, ErrorBox, Field, inputCls, Loading } from "@/components/ui";
import { post } from "@/lib/api";
import { when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Project } from "@/lib/types";

const STEPS = [
  "Create a project",
  "Upload footage (and optionally a reference video)",
  "Describe the edit you want",
  "Watch the agent plan, render and evaluate",
  "Inspect the evaluation and give feedback",
  "See how the agent improves under Improvement",
];

export default function Home() {
  const router = useRouter();
  const projects = useApi<Project[]>("/projects");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await post<Project>("/projects", { title: title.trim(), description: description.trim() || null });
      router.push(`/projects/${p.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="mt-1 text-sm text-muted">
            An agent that turns raw footage into a 9:16 short, checks its own work, remembers your preferences and
            improves through controlled experiments.
          </p>
        </div>

        <Card title="All projects">
          <ErrorBox error={projects.error} onRetry={projects.reload} />
          {projects.loading && !projects.data ? (
            <Loading />
          ) : projects.data?.length ? (
            <ul className="divide-y divide-line">
              {projects.data.map((p) => (
                <li key={p.id}>
                  <Link href={`/projects/${p.id}`} className="flex items-baseline justify-between gap-4 py-2.5 hover:text-accent">
                    <span>
                      <span className="font-medium">{p.title}</span>
                      {p.description && <span className="ml-2 text-sm text-muted">{p.description}</span>}
                    </span>
                    <span className="shrink-0 text-xs text-muted">{when(p.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            !projects.error && <Empty>No projects yet. Create one to start.</Empty>
          )}
        </Card>
      </div>

      <div className="space-y-6">
        <Card title="New project">
          <form onSubmit={create} className="space-y-3">
            <Field label="Title">
              <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} placeholder="Launch recap" />
            </Field>
            <Field label="Description" hint="optional">
              <textarea className={inputCls} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={5000} />
            </Field>
            <ErrorBox error={error} />
            <Button type="submit" disabled={busy || !title.trim()}>
              {busy ? "Creating…" : "Create project"}
            </Button>
          </form>
        </Card>

        <Card title="How it works">
          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
            {STEPS.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
