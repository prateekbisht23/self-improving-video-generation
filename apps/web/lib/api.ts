// One place that talks to the FastAPI backend. Every error becomes an ApiError with a readable message,
// so pages can show "what went wrong" instead of a blank screen.

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// FastAPI errors: {"detail": "..."} or, for validation, {"detail": [{loc, msg}, ...]}.
function detail(body: unknown): string {
  if (typeof body === "string") return body.slice(0, 300);
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d
      .map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".") || "request"}: ${e.msg}`)
      .join("; ");
  return "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const json = init.body !== undefined && !(init.body instanceof FormData);
  let r: Response;
  try {
    r = await fetch(`${API}${path}`, {
      ...init,
      headers: { ...(json ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError(0, `API unreachable at ${API}. Is it running? (uv run uvicorn services.api.main:app --port 8010)`);
  }
  const text = await r.text();
  const body = text ? parse(text) : null;
  if (!r.ok) throw new ApiError(r.status, detail(body) || `${r.status} ${r.statusText}`);
  return body as T;
}

export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const patch = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });

export const videoUrl = (renderId: string) => `${API}/renders/${renderId}/video`;

/** Upload with progress (fetch has no upload progress, XHR does). */
export function upload<T>(path: string, form: FormData, onProgress: (share: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", `${API}${path}`);
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    x.onload = () => {
      const body = x.responseText ? parse(x.responseText) : null;
      if (x.status >= 200 && x.status < 300) resolve(body as T);
      else reject(new ApiError(x.status, detail(body) || `upload failed (${x.status})`));
    };
    x.onerror = () => reject(new ApiError(0, `API unreachable at ${API}`));
    x.send(form);
  });
}
