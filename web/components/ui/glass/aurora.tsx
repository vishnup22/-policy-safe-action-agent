import { cn } from "@/lib/utils";

const BLOB =
  "aurora-blob absolute rounded-full will-change-transform motion-reduce:animate-none motion-reduce:will-change-auto";

/**
 * Ambient mesh behind all content. Soft radial gradients moved by CSS transforms
 * only (compositor-friendly): no filter blur, no per-frame JavaScript.
 */
export function Aurora({ className }: { className?: string }) {
  return (
    <div aria-hidden data-slot="aurora" className={cn("pointer-events-none fixed inset-0 -z-10 overflow-hidden", className)}>
      <div
        className={cn(BLOB, "animate-aurora-a -top-[28vmax] -left-[18vmax] size-[72vmax]")}
        style={{ background: "radial-gradient(closest-side, var(--aurora-1), transparent)" }}
      />
      <div
        className={cn(BLOB, "animate-aurora-b top-[8vh] -right-[24vmax] size-[62vmax]")}
        style={{ background: "radial-gradient(closest-side, var(--aurora-2), transparent)" }}
      />
      <div
        className={cn(BLOB, "animate-aurora-c -bottom-[34vmax] left-[12vw] size-[66vmax]")}
        style={{ background: "radial-gradient(closest-side, var(--aurora-3), transparent)" }}
      />
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse at 50% 0%, transparent 0%, var(--background) 80%)", opacity: 0.55 }}
      />
    </div>
  );
}
