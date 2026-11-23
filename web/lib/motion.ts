import type { Transition, Variants } from "framer-motion";

/** The one spring used across the UI. */
export const SPRING = { type: "spring", stiffness: 300, damping: 30 } as const satisfies Transition;

/** What springs degrade to under `prefers-reduced-motion`. */
export const FADE = { type: "tween", duration: 0.2, ease: "easeOut" } as const satisfies Transition;

export const REVEAL_HIDDEN = { opacity: 0, y: 20, filter: "blur(8px)" } as const;
/**
 * Any `filter` on an ancestor (even blur(0px)) turns it into a backdrop root and
 * flattens glass descendants, so the filter is removed once the reveal settles.
 */
export const REVEAL_VISIBLE = { opacity: 1, y: 0, filter: "blur(0px)", transitionEnd: { filter: "none" } } as const;

export const revealVariants: Variants = { hidden: REVEAL_HIDDEN, visible: REVEAL_VISIBLE };

/**
 * Scroll blur-fade. Hidden/visible states are identical in both modes so server and
 * client render the same markup; reduced motion only changes how the values move:
 * position and blur snap, opacity fades.
 */
export function revealTransition(reduced: boolean, delay = 0): Transition {
  if (reduced) return { default: { duration: 0 }, opacity: { ...FADE, delay } };
  return {
    ...SPRING,
    delay,
    opacity: { type: "tween", duration: 0.45, ease: "easeOut", delay },
    filter: { type: "tween", duration: 0.45, ease: "easeOut", delay },
  };
}

/** Shared-layout moves (active nav pill, tab indicator). */
export function layoutTransition(reduced: boolean): Transition {
  return reduced ? { duration: 0 } : SPRING;
}

/** Route-level enter animation for console pages. */
export function pageMotion(reduced: boolean) {
  return {
    initial: reduced ? { opacity: 0 } : { opacity: 0, y: 12 },
    animate: reduced ? { opacity: 1 } : { opacity: 1, y: 0 },
    transition: reduced ? FADE : { ...SPRING, opacity: { type: "tween", duration: 0.25 } },
  } as const;
}

/** Resolves once the page has loaded and the main thread is idle, so deferred work stays out of first paint. */
export function whenIdle(timeout = 1500): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  return new Promise((resolve) => {
    const schedule = () => {
      if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(() => resolve(), { timeout });
      else setTimeout(resolve, 50);
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
  });
}

/**
 * Loaded lazily by <LazyMotion> so motion features stay out of the first-load bundle. Until they
 * arrive, `m` components render their `initial` styles; nothing above the fold animates on entry.
 */
export const loadMotionFeatures = () =>
  whenIdle().then(() => import("framer-motion").then((mod) => mod.domMax));
