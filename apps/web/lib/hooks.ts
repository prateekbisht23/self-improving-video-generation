"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/**
 * Fetch `path` (null = don't fetch yet). `poll` is a delay in ms, or a function of the latest data that
 * returns a delay or null; polling stops when it returns null (e.g. once a job has finished).
 */
export function useApi<T>(path: string | null, poll?: number | ((data: T) => number | null)) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const pollRef = useRef(poll);
  pollRef.current = poll;
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (path === null) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async () => {
      try {
        const d = await api<T>(path);
        if (!alive) return;
        setData(d);
        setError(null);
        const p = pollRef.current;
        const delay = typeof p === "function" ? p(d) : p ?? null;
        if (delay) timer = setTimeout(run, delay);
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message);
        if (pollRef.current) timer = setTimeout(run, 5000); // keep trying while the page is open
      } finally {
        if (alive) setLoading(false);
      }
    };
    setLoading(true);
    run();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [path, tick]);

  return { data, error, loading, reload, setData };
}
