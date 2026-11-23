import type { EvalRunSummary, PolicySummary } from "@/lib/api/types";

export type LineChange = "same" | "changed" | "added" | "removed";

/** One line of a rule rendered as block YAML; `path` identifies the field (e.g. `when.value`). */
export interface RuleLine {
  path: string;
  depth: number;
  /** `- ` prefix for the first key of a list item. */
  bullet: boolean;
  key: string | null;
  value: string | null;
  change: LineChange;
}

export interface FieldChange {
  path: string;
  before: unknown;
  after: unknown;
}

const MISSING = Symbol("missing");

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isScalarList(v: unknown): v is unknown[] {
  return Array.isArray(v) && v.every((x) => !isPlainObject(x) && !Array.isArray(x));
}

export function formatScalar(v: unknown): string {
  if (v === MISSING || v === undefined) return "—";
  if (v === null) return "null";
  if (isScalarList(v)) return `[${v.map(formatScalar).join(", ")}]`;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Leaf paths of a rule body. Scalar lists count as one leaf, like a flow sequence in YAML. */
function leaves(value: unknown, path = ""): Map<string, unknown> {
  const out = new Map<string, unknown>();
  if (isPlainObject(value)) {
    for (const [k, v] of Object.entries(value)) {
      for (const [p, leaf] of leaves(v, path ? `${path}.${k}` : k)) out.set(p, leaf);
    }
  } else if (Array.isArray(value) && !isScalarList(value)) {
    value.forEach((v, i) => {
      for (const [p, leaf] of leaves(v, `${path}[${i}]`)) out.set(p, leaf);
    });
  } else {
    out.set(path, value);
  }
  return out;
}

/** Every field whose value differs between two versions of a rule, in `after` order then removed fields. */
export function fieldChanges(before: Record<string, unknown>, after: Record<string, unknown>): FieldChange[] {
  const a = leaves(before);
  const b = leaves(after);
  const out: FieldChange[] = [];
  for (const [path, value] of b) {
    const old = a.has(path) ? a.get(path) : MISSING;
    if (old === MISSING || formatScalar(old) !== formatScalar(value)) out.push({ path, before: old, after: value });
  }
  for (const [path, value] of a) if (!b.has(path)) out.push({ path, before: value, after: MISSING });
  return out;
}

export function isMissing(v: unknown): boolean {
  return v === MISSING;
}

/**
 * A rule as block-YAML lines, each tagged with how it changed relative to `other`
 * (`changed` when the other side has a different value, `added`/`removed` when it has none).
 */
export function ruleLines(
  rule: Record<string, unknown>,
  side: "before" | "after",
  other?: Record<string, unknown>,
): RuleLine[] {
  const otherLeaves = other ? leaves(other) : null;
  const lines: RuleLine[] = [];

  function changeOf(path: string, value: unknown): LineChange {
    if (!otherLeaves) return side === "after" ? "added" : "removed";
    if (!otherLeaves.has(path)) return side === "after" ? "added" : "removed";
    return formatScalar(otherLeaves.get(path)) === formatScalar(value) ? "same" : "changed";
  }

  function containerChange(path: string, value: unknown): LineChange {
    const kids = [...leaves(value, path)];
    if (kids.length && kids.every(([p, v]) => changeOf(p, v) === (side === "after" ? "added" : "removed"))) {
      return side === "after" ? "added" : "removed";
    }
    return "same";
  }

  function walk(value: Record<string, unknown>, path: string, depth: number, bulletFirst: boolean) {
    Object.entries(value).forEach(([key, v], i) => {
      const p = path ? `${path}.${key}` : key;
      const bullet = bulletFirst && i === 0;
      if (isPlainObject(v)) {
        lines.push({ path: p, depth, bullet, key, value: null, change: containerChange(p, v) });
        walk(v, p, depth + 1, false);
      } else if (Array.isArray(v) && !isScalarList(v)) {
        lines.push({ path: p, depth, bullet, key, value: null, change: containerChange(p, v) });
        v.forEach((item, j) => {
          const ip = `${p}[${j}]`;
          if (isPlainObject(item)) walk(item, ip, depth + 1, true);
          else lines.push({ path: ip, depth: depth + 1, bullet: true, key: null, value: formatScalar(item), change: changeOf(ip, item) });
        });
      } else {
        lines.push({ path: p, depth, bullet, key, value: formatScalar(v), change: changeOf(p, v) });
      }
    });
  }

  walk(rule, "", 0, false);
  return lines;
}

const versionCompare = new Intl.Collator("en", { numeric: true }).compare;

/** Versions of one policy set, oldest first. */
export function versionsOf(policies: PolicySummary[], policySet: string): string[] {
  return policies
    .filter((p) => p.policy_set === policySet)
    .map((p) => p.version)
    .sort(versionCompare);
}

/**
 * Resolves the versions to compare: `to` defaults to the newest version, `from` to the one just
 * before `to` (or `to` itself when there is only one).
 */
export function resolveVersions(versions: string[], from: string | null, to: string | null): { from: string; to: string } | null {
  if (versions.length === 0) return null;
  const target = to ?? versions[versions.length - 1];
  const idx = versions.indexOf(target);
  const source = from ?? versions[Math.max(0, (idx === -1 ? versions.length : idx) - 1)] ?? target;
  return { from: source, to: target };
}

export function policyDiffHref(policySet: string, params: { from?: string; to?: string; rule?: string } = {}): string {
  const q = new URLSearchParams();
  if (params.from) q.set("from", params.from);
  if (params.to) q.set("to", params.to);
  if (params.rule) q.set("rule", params.rule);
  const query = q.toString();
  return `/policies/${encodeURIComponent(policySet)}/diff${query ? `?${query}` : ""}`;
}

export interface RunsByVersion {
  from: EvalRunSummary | null;
  to: EvalRunSummary | null;
  /** Both runs use the same suite, so their numbers are comparable. */
  sameSuite: boolean;
}

function newest(runs: EvalRunSummary[]): EvalRunSummary | null {
  return runs.reduce<EvalRunSummary | null>((best, r) => (!best || r.started_at > best.started_at ? r : best), null);
}

/**
 * The eval runs to compare two policy versions with: the newest pair from a suite that was run
 * on both versions, otherwise the newest run on each version.
 */
export function runsForVersions(runs: EvalRunSummary[], from: string, to: string): RunsByVersion {
  let best: RunsByVersion | null = null;
  let bestTime = "";
  for (const suite of new Set(runs.map((r) => r.suite))) {
    const a = newest(runs.filter((r) => r.suite === suite && r.policy_version === from));
    const b = newest(runs.filter((r) => r.suite === suite && r.policy_version === to));
    if (!a || !b) continue;
    const pairTime = a.started_at > b.started_at ? a.started_at : b.started_at;
    if (pairTime > bestTime) {
      best = { from: a, to: b, sameSuite: true };
      bestTime = pairTime;
    }
  }
  return (
    best ?? {
      from: newest(runs.filter((r) => r.policy_version === from)),
      to: newest(runs.filter((r) => r.policy_version === to)),
      sameSuite: false,
    }
  );
}
