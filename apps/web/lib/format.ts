export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;

export const signed = (x: number | null | undefined, digits = 3) =>
  x === null || x === undefined ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(digits)}`;

/** 83.4 -> "1:23.4" */
export function clock(sec: number | null | undefined) {
  if (sec === null || sec === undefined) return "—";
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1)}`;
}

export const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

export const short = (id: string) => id.slice(0, 8);

export function bytes(n: number) {
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

/** Flatten nested config into dotted keys so two versions can be diffed row by row. */
export function flatten(obj: unknown, prefix = ""): Record<string, unknown> {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return { [prefix]: obj };
  return Object.entries(obj as Record<string, unknown>).reduce(
    (acc, [k, v]) => ({ ...acc, ...flatten(v, prefix ? `${prefix}.${k}` : k) }),
    {} as Record<string, unknown>,
  );
}
