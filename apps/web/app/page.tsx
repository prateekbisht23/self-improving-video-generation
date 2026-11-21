"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

type Health = { status: string; db: string };

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <main className="mx-auto max-w-2xl p-8 font-sans">
      <h1 className="text-2xl font-semibold">Self-Improving Video Editing Agent</h1>
      <p className="mt-2 text-sm text-neutral-500">Phase 0 — foundation</p>
      <section className="mt-6 rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
        <h2 className="font-medium">API status</h2>
        <p className="mt-1 font-mono text-sm">{API}/health</p>
        <p className="mt-3">
          {error ? (
            <span className="text-red-600">unreachable — {error}</span>
          ) : health ? (
            <span>
              api: <b>{health.status}</b> · db: <b>{health.db}</b>
            </span>
          ) : (
            "checking…"
          )}
        </p>
      </section>
    </main>
  );
}
