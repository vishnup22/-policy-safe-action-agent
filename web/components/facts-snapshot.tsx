export function FactsSnapshot({ facts }: { facts: Record<string, unknown> }) {
  const entries = Object.entries(facts);
  if (entries.length === 0) return <p className="text-xs text-muted-foreground">No facts recorded.</p>;
  return (
    <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1 rounded-xl border border-glass-edge bg-glass-inset p-3 font-mono text-xs">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="truncate text-muted-foreground">{k}</dt>
          <dd className="break-all">{JSON.stringify(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function JsonBlock({ value, label }: { value: unknown; label?: string }) {
  return (
    <pre
      aria-label={label}
      className="max-h-96 overflow-auto rounded-xl border border-glass-edge bg-glass-inset p-3 font-mono text-xs leading-relaxed"
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
