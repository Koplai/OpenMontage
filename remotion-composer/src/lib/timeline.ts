/** Canonical cuts use source trims; only explicit timeline fields position them. */
export interface TimelineCut {
  in_seconds: number;
  out_seconds: number;
  speed?: number;
  timeline_start_seconds?: number;
  timeline_duration_seconds?: number;
  source_in_seconds?: number;
}

export function normalizeCuts<T extends TimelineCut>(
  cuts: T[],
  mode: "sequential" | "legacy" = "sequential",
) {
  let cursor = 0;
  return cuts.map((cut) => {
    const speed = cut.speed ?? 1;
    const sourceIn = mode === "legacy" ? (cut.source_in_seconds ?? 0) : cut.in_seconds;
    const sourceOut = mode === "legacy"
      ? sourceIn + (cut.out_seconds - cut.in_seconds) * speed
      : cut.out_seconds;
    const duration = (sourceOut - sourceIn) / speed;
    const start = cut.timeline_start_seconds ?? (mode === "legacy" ? cut.in_seconds : cursor);
    if (![sourceIn, sourceOut, speed, start, duration].every(Number.isFinite)
      || sourceIn < 0 || speed <= 0 || duration <= 0 || start < 0
      || (cut.timeline_duration_seconds !== undefined
        && Math.abs(cut.timeline_duration_seconds - duration) > 1e-6)) {
      throw new Error("Invalid cut trim, speed, or timeline duration");
    }
    cursor = Math.max(cursor, start + duration);
    return {
      ...cut,
      in_seconds: sourceIn,
      out_seconds: sourceOut,
      source_in_seconds: sourceIn,
      speed,
      timeline_start_seconds: start,
      timeline_duration_seconds: duration,
    };
  });
}

export function timelineFrames(cuts: TimelineCut[], fps: number, mode: "sequential" | "legacy" = "sequential") {
  const normalized = normalizeCuts(cuts, mode);
  return Math.max(1, Math.ceil(Math.max(0, ...normalized.map(
    (cut) => cut.timeline_start_seconds + cut.timeline_duration_seconds,
  )) * fps));
}
