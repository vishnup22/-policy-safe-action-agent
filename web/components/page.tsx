import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <GlassPanel
      role="alert"
      className="flex flex-col items-center gap-3 border-destructive/30 py-10 text-center text-sm"
    >
      <AlertTriangle aria-hidden className="size-5 text-destructive" />
      <p>{error.message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </GlassPanel>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-3xl border border-dashed border-glass-edge bg-glass-inset py-12 text-center text-sm text-muted-foreground">
      {children}
    </p>
  );
}
