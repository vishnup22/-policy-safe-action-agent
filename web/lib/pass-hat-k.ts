import type { SystemMetrics } from "@/lib/api/types";

export interface PassHatKRow {
  k: string;
  baseline: number | null;
  guarded: number | null;
}

/** One row per k present in either system, ascending. */
export function passHatKRows(baseline: SystemMetrics, guarded: SystemMetrics): PassHatKRow[] {
  const ks = [...new Set([...Object.keys(baseline.pass_hat_k), ...Object.keys(guarded.pass_hat_k)])]
    .map(Number)
    .sort((a, b) => a - b);
  return ks.map((k) => ({
    k: String(k),
    baseline: baseline.pass_hat_k[String(k)] ?? null,
    guarded: guarded.pass_hat_k[String(k)] ?? null,
  }));
}
