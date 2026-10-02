// Display formatting (locale-aware, Austrian German by default).

export function localeTag(locale: string): string {
  return locale === "en" ? "en-GB" : "de-AT";
}

export function num(value: number | null | undefined, locale = "de"): string {
  if (value === null || value === undefined) return "–";
  return value.toLocaleString(localeTag(locale));
}

export function pct(value: number | null | undefined, locale = "de"): string {
  if (value === null || value === undefined) return "–";
  return (value * 100).toLocaleString(localeTag(locale), { maximumFractionDigits: 1 }) + " %";
}

export function dateTime(value: string | null | undefined, locale = "de"): string {
  if (!value) return "–";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(localeTag(locale), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "–";
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/** Value for <input type="datetime-local"> from an ISO timestamp (local time). */
export function toLocalInput(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** ISO timestamp with offset from an <input type="datetime-local"> value. */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
