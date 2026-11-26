"use client";

import Link from "next/link";
import { Badge, Card, Details, Empty, ErrorBox, Loading, Meter } from "@/components/ui";
import { short, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AgentVersion, Cluster, ExperimentRow, Promotion } from "@/lib/types";

export default function ImprovementPage() {
  const versions = useApi<AgentVersion[]>("/improvement/versions");
  const promotions = useApi<Promotion[]>("/improvement/promotions");
  const experiments = useApi<ExperimentRow[]>("/improvement/experiments", 15000);
  const clusters = useApi<Cluster[]>("/improvement/clusters");
  const active = versions.data?.find((v) => v.status === "active");
  const waiting = experiments.data?.filter((e) => e.status === "awaiting_approval") ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Self-improvement</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          The loop groups the agent&apos;s failures, diagnoses them, proposes a configuration change, and tests it against the
          current version on the same benchmark tasks. Only candidates that pass the regression gates and a held-out check
          reach you, and only you can promote one.
        </p>
        <p className="mt-2 font-mono text-xs text-muted">uv run python -m improvement.cli start · status · approve|decline &lt;thread&gt;</p>
      </div>

      {!!waiting.length && (
        <Card title="Needs your decision" className="border-accent/50">
          <ul className="space-y-1 text-sm">
            {waiting.map((e) => (
              <li key={e.id}>
                <Link href={`/improvement/experiments/${e.id}`} className="text-accent hover:underline">
                  {e.candidate_version}
                </Link>{" "}
                <span className="text-muted">vs {e.baseline_version}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Agent versions" actions={<Link href="/improvement/compare" className="text-xs text-accent hover:underline">compare two →</Link>}>
          <ErrorBox error={versions.error} onRetry={versions.reload} />
          {versions.data ? (
            <ul className="divide-y divide-line">
              {[...versions.data].reverse().map((v) => (
                <li key={v.version} className="py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/improvement/compare?a=${encodeURIComponent(v.parent ?? v.version)}&b=${encodeURIComponent(v.version)}`} className="font-mono text-xs hover:text-accent">
                      {v.version}
                    </Link>
                    <span className="flex gap-1">
                      <Badge tone="muted">{v.origin}</Badge>
                      <Badge>{v.status}</Badge>
                    </span>
                  </div>
                  {v.rationale && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{v.rationale}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <Loading />
          )}
        </Card>

        <Card title="Promotions">
          <ErrorBox error={promotions.error} />
          {promotions.data?.length ? (
            <ol className="space-y-3 border-l border-line pl-4">
              {[...promotions.data].reverse().map((p) => (
                <li key={p.experiment_id} className="text-sm">
                  <div className="text-xs text-muted">
                    {when(p.at)} · approved by {p.approved_by}
                  </div>
                  <div className="font-mono text-xs">
                    {p.from} → <b>{p.to}</b>
                  </div>
                  {p.note && <p className="mt-0.5 text-xs italic">“{p.note}”</p>}
                  <Link href={`/improvement/experiments/${p.experiment_id}`} className="text-xs text-accent hover:underline">
                    evidence →
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <Empty>No promotions yet{active ? `; ${active.version} is the seed version` : ""}.</Empty>
          )}
        </Card>
      </div>

      <Card title="Experiments">
        <ErrorBox error={experiments.error} />
        {experiments.data?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">experiment</th>
                  <th className="pr-3 font-medium">candidate</th>
                  <th className="pr-3 font-medium">change</th>
                  <th className="pr-3 font-medium">gates</th>
                  <th className="pr-3 font-medium">status</th>
                  <th className="font-medium">when</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line align-top">
                {experiments.data.map((e) => (
                  <tr key={e.id}>
                    <td className="py-2 pr-3">
                      <Link href={`/improvement/experiments/${e.id}`} className="font-mono text-accent hover:underline">
                        {short(e.id)}
                      </Link>
                    </td>
                    <td className="pr-3 font-mono text-xs">{e.candidate_version}</td>
                    <td className="max-w-sm pr-3 text-xs">
                      <span className="line-clamp-2">{e.change?.hypothesis ?? "—"}</span>
                      {e.change?.origin === "human" && <Badge tone="muted">human</Badge>}
                    </td>
                    <td className="pr-3">
                      {e.eligible === null ? <span className="text-xs text-muted">—</span> : <Badge tone={e.eligible ? "good" : "bad"}>{e.eligible ? "passed" : "failed"}</Badge>}
                    </td>
                    <td className="pr-3">
                      <Badge>{e.status}</Badge>
                    </td>
                    <td className="text-xs whitespace-nowrap text-muted">{when(e.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !experiments.loading && <Empty>No experiments yet. Start one with the CLI.</Empty>
        )}
      </Card>

      <Card title="Failure clusters (latest analysis)">
        <ErrorBox error={clusters.error} />
        {clusters.data?.length ? (
          <>
            <p className="mb-3 text-xs text-muted">
              From the development split only, for {clusters.data[0].agent_version}. Rate = share of renders with this failure.
            </p>
            <ul className="divide-y divide-line">
              {clusters.data.map((c) => (
                <ClusterRow key={c.id} cluster={c} />
              ))}
            </ul>
          </>
        ) : (
          !clusters.loading && <Empty>No analysis yet.</Empty>
        )}
      </Card>
    </div>
  );
}

function ClusterRow({ cluster: c }: { cluster: Cluster }) {
  return (
    <li className="py-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium">{c.label}</span>
        <Badge tone={c.severity === "critical" ? "bad" : c.severity === "major" ? "warn" : "muted"}>{c.severity}</Badge>
        <Badge tone="muted">{c.method}</Badge>
        <span className="ml-auto flex w-40 items-center gap-2 text-xs text-muted">
          <Meter value={c.rate} tone="bad" /> {Math.round(c.rate * 100)}%
        </span>
      </div>
      <p className="mt-0.5 text-xs text-muted">
        {c.size} renders · tasks {c.tasks.slice(0, 8).join(", ")}
        {c.tasks.length > 8 ? "…" : ""}
      </p>
      {(c.diagnosis || c.examples?.length) && (
        <div className="mt-1">
          <Details summary={c.diagnosis ? "diagnosis" : "examples"}>
            {c.diagnosis?.summary && <p className="text-sm">{c.diagnosis.summary}</p>}
            {c.diagnosis?.root_causes?.map((r, i) => (
              <div key={i} className="mt-2">
                <p className="text-sm">
                  <Badge tone={r.confidence === "high" ? "info" : "muted"}>{r.confidence}</Badge> {r.cause}
                </p>
                <ul className="mt-1 list-disc pl-5 text-xs text-muted">
                  {r.evidence.slice(0, 4).map((x, j) => (
                    <li key={j}>{x}</li>
                  ))}
                </ul>
              </div>
            ))}
            {!c.diagnosis && (
              <ul className="list-disc pl-5 text-xs text-muted">
                {c.examples?.slice(0, 5).map((x, i) => (
                  <li key={i}>
                    <span className="font-mono">{x.task}</span>: {x.message}
                  </li>
                ))}
              </ul>
            )}
          </Details>
        </div>
      )}
    </li>
  );
}
