import type { JobState } from "@/api/types";

export function money(n: number | null | undefined): string {
  return `$${(n ?? 0).toFixed(2)}`;
}

export function shortDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function compactNum(n?: number | null): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

const IN_PROGRESS: JobState[] = [
  "QUEUED",
  "RESEARCHING",
  "SCRIPTING",
  "GENERATING",
  "EDITING",
  "CAPTIONING",
  "POSTING",
];

export function isInProgress(s: JobState): boolean {
  return IN_PROGRESS.includes(s);
}
