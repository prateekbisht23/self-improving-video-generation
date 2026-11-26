"use client";

import { clock } from "@/lib/format";
import type { Evidence, Timeline } from "@/lib/types";

const PALETTE = ["#4f5bd5", "#0e9f6e", "#d97706", "#db2777", "#0891b2", "#7c3aed"];

/** Timeline start of each clip; a transition overlaps the previous clip's tail (same as Timeline.clip_starts). */
export function clipStarts(tl: Timeline) {
  const starts: number[] = [];
  let t = 0;
  tl.video.forEach((c, i) => {
    if (i > 0 && c.transition_in !== "cut") t -= c.transition_duration;
    starts.push(t);
    t += c.src_out - c.src_in;
  });
  return { starts, total: t };
}

export type Marker = Evidence & { check: string };

/**
 * Three tracks in output time: video clips (coloured by source asset), captions, and evaluation issues.
 * Clicking anywhere seeks the preview; the playhead follows the video.
 */
export function TimelineView({ timeline, time, markers = [], onSeek }: {
  timeline: Timeline;
  time: number;
  markers?: Marker[];
  onSeek: (t: number) => void;
}) {
  const { starts, total } = clipStarts(timeline);
  if (!timeline.video.length || total <= 0) return <p className="text-sm text-muted">Empty timeline.</p>;
  const assetColor = (id: string) => PALETTE[Math.max(0, timeline.assets.findIndex((a) => a.id === id)) % PALETTE.length];
  const x = (t: number) => `${(Math.max(0, Math.min(total, t)) / total) * 100}%`;
  const w = (a: number, b: number) => `${(Math.max(0, Math.min(total, b) - Math.max(0, a)) / total) * 100}%`;
  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(((e.clientX - r.left) / r.width) * total);
  };
  const { min_duration: lo, max_duration: hi } = timeline.output;
  const ticks = Array.from({ length: Math.floor(total / 5) + 1 }, (_, i) => i * 5);

  return (
    <div className="select-none">
      <div className="mb-1 flex justify-between text-xs text-muted">
        <span>
          {timeline.video.length} clips · {clock(total)} (target {lo}–{hi}s) · {timeline.captions.length} captions · look: {timeline.style.color}
        </span>
        <span className="font-mono">{clock(time)}</span>
      </div>
      <div className="relative cursor-pointer" onClick={seek}>
        <div className="relative h-4 text-[10px] text-muted">
          {ticks.map((t) => (
            <span key={t} className="absolute -translate-x-1/2" style={{ left: x(t) }}>
              {t}s
            </span>
          ))}
        </div>
        <Track label="video">
          {timeline.video.map((c, i) => (
            <div
              key={i}
              className="absolute top-0 h-full overflow-hidden rounded-sm border border-white/40 px-1 text-[10px] leading-7 text-white"
              style={{ left: x(starts[i]), width: w(starts[i], starts[i] + c.src_out - c.src_in), background: assetColor(c.asset_id) }}
              title={`clip ${i}: source ${clock(c.src_in)}–${clock(c.src_out)}${c.transition_in !== "cut" ? ` · ${c.transition_in} in` : ""}${c.purpose ? `\n${c.purpose}` : ""}`}
            >
              #{i} {clock(c.src_in)}
            </div>
          ))}
        </Track>
        <Track label="captions">
          {timeline.captions.map((c, i) => (
            <div key={i} className="absolute top-1 h-5 rounded-sm bg-fg/25" style={{ left: x(c.start), width: w(c.start, c.end) }} title={`${clock(c.start)} ${c.text}`} />
          ))}
        </Track>
        <Track label="issues">
          {markers.map((m, i) => {
            const s = m.start ?? 0;
            const e = m.end ?? s;
            const point = e - s < total * 0.01;
            return (
              <div
                key={i}
                className={`absolute top-1 h-5 rounded-sm ${point ? "w-1 bg-bad" : "bg-bad/50"}`}
                style={{ left: x(s), ...(point ? {} : { width: w(s, e) }) }}
                title={`${m.check}: ${m.detail} (${clock(s)})`}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSeek(s);
                }}
              />
            );
          })}
        </Track>
        <div className="pointer-events-none absolute top-4 bottom-0 w-0.5 bg-accent" style={{ left: x(time) }} />
      </div>
    </div>
  );
}

function Track({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="relative mt-1 h-7 rounded bg-line/60">
      <span className="pointer-events-none absolute -top-px right-1 z-10 text-[10px] text-muted">{label}</span>
      {children}
    </div>
  );
}
