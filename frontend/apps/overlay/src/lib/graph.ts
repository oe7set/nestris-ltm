// Difference series of two score histories ([t_ms, score] samples).

/**
 * A score never decreases within a game, so a value that is later followed
 * by a lower one was a misread: replace every sample by the minimum of
 * itself and all later samples (suffix minimum).
 */
export function monotonic(series: [number, number][]): [number, number][] {
  const out = series.map((p) => [p[0], p[1]] as [number, number]);
  for (let i = out.length - 2; i >= 0; i--) {
    out[i]![1] = Math.min(out[i]![1], out[i + 1]![1]);
  }
  return out;
}

/** Step-interpolated A - B at every sample time of either series. */
export function diffSeries(rawA: [number, number][], rawB: [number, number][]): [number, number][] {
  const a = monotonic(rawA);
  const b = monotonic(rawB);
  if (!a.length && !b.length) return [];
  const times = [...new Set([...a.map((p) => p[0]), ...b.map((p) => p[0])])].sort((x, y) => x - y);
  const at = (series: [number, number][], t: number): number => {
    let value = 0;
    for (const [ts, v] of series) {
      if (ts > t) break;
      value = v;
    }
    return value;
  };
  return times.map((t) => [t, at(a, t) - at(b, t)]);
}
