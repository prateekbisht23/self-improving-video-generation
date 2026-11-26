"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Badge, Card, Crumbs, Empty, ErrorBox, inputCls, Loading } from "@/components/ui";
import { flatten, short, signed, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AgentVersion, ExperimentRow } from "@/lib/types";

export default function ComparePage() {
  return (
    <Suspense fallback={<Loading />}>
      <Compare />
    </Suspense>
  );
}

function Compare() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const versions = useApi<AgentVersion[]>("/improvement/versions");
  const experiments = useApi<ExperimentRow[]>("/improvement/experiments");
  const list = versions.data ?? [];
  const active = list.find((v) => v.status === "active");
  const a = params.get("a") ?? active?.parent ?? list[0]?.version ?? "";
  const b = params.get("b") ?? active?.version ?? list.at(-1)?.version ?? "";
  const va = list.find((v) => v.version === a);
  const vb = list.find((v) => v.version === b);

  const set = (key: "a" | "b", value: string) => {
    const q = new URLSearchParams(params.toString());
    q.set("a", a);
    q.set("b", b);
    q.set(key, value);
    router.replace(`${pathname}?${q}`);
  };

  if (versions.error) return <ErrorBox error={versions.error} onRetry={versions.reload} />;
  if (!versions.data) return <Loading />;

  const fa = flatten(va?.config ?? {});
  const fb = flatten(vb?.config ?? {});
  const keys = Array.from(new Set([...Object.keys(fa), ...Object.keys(fb)])).sort();
  const changed = keys.filter((k) => JSON.stringify(fa[k]) !== JSON.stringify(fb[k]));
  const between = (experiments.data ?? []).filter(
    (e) => (e.baseline_version === a && e.candidate_version === b) || (e.baseline_version === b && e.candidate_version === a),
  );

  return (
    <div className="space-y-6">
      <div>
        <Crumbs items={[{ href: "/improvement", label: "Improvement" }, { label: "Compare versions" }]} />
        <h1 className="text-2xl font-semibold">Compare agent versions</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          A version is a configuration of the same code: policy knobs and prompt additions. What changed, and the experiments
          that measured it.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {(["a", "b"] as const).map((key) => {
          const v = key === "a" ? va : vb;
          return (
            <Card key={key} title={key === "a" ? "Version A" : "Version B"}>
              <select className={`${inputCls} font-mono text-xs`} value={key === "a" ? a : b} onChange={(e) => set(key, e.target.value)}>
                {list.map((x) => (
                  <option key={x.version} value={x.version}>
                    {x.version} ({x.status})
                  </option>
                ))}
              </select>
              {v && (
                <div className="mt-2 space-y-1 text-xs">
                  <div className="flex gap-1">
                    <Badge>{v.status}</Badge>
                    <Badge tone="muted">{v.origin}</Badge>
                    <span className="text-muted">created {when(v.created_at)}</span>
                  </div>
                  {v.parent && <p className="text-muted">parent {v.parent}</p>}
                  {v.rationale && <p>{v.rationale}</p>}
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <Card title={`Configuration (${changed.length} difference${changed.length === 1 ? "" : "s"})`}>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="py-1 font-medium">setting</th>
              <th className="font-medium">A</th>
              <th className="font-medium">B</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line font-mono text-xs">
            {keys.map((k) => {
              const diff = changed.includes(k);
              return (
                <tr key={k} className={diff ? "bg-accent/10" : ""}>
                  <td className="py-1 pr-3">{k}</td>
                  <td className="pr-3">{show(fa[k])}</td>
                  <td className={diff ? "font-semibold" : ""}>{show(fb[k])}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card title="Experiments between these versions">
        {between.length ? (
          <ul className="divide-y divide-line text-sm">
            {between.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-3 py-2">
                <Link href={`/improvement/experiments/${e.id}`} className="font-mono text-accent hover:underline">
                  {short(e.id)}
                </Link>
                <Badge>{e.status}</Badge>
                {e.eligible !== null && <Badge tone={e.eligible ? "good" : "bad"}>{e.eligible ? "gates passed" : "gates failed"}</Badge>}
                <span className="text-xs text-muted">
                  {e.baseline_version === a ? "A → B" : "B → A"} · {when(e.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No experiment compared these two directly. Pick a version and its parent to see the evidence for it.</Empty>
        )}
      </Card>
    </div>
  );
}

function show(v: unknown) {
  if (v === undefined) return <span className="text-muted">—</span>;
  if (typeof v === "string") return v === "" ? <span className="text-muted">“”</span> : v;
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : signed(v, 2).replace("+", "");
  return JSON.stringify(v);
}
