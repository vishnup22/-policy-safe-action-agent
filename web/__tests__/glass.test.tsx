import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MessageSquare } from "lucide-react";
import { PageTransition } from "@/components/page-transition";
import { Aurora, Dock, GlassPanel, glassVariants, PillNav, SegmentedTabs } from "@/components/ui/glass";
import { FADE, layoutTransition, pageMotion, revealTransition, revealVariants, SPRING } from "@/lib/motion";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: ComponentProps<"a"> & { href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/chat" }));

describe("motion presets", () => {
  it("uses one spring: stiffness 300, damping 30", () => {
    expect(SPRING).toEqual({ type: "spring", stiffness: 300, damping: 30 });
    expect(layoutTransition(false)).toBe(SPRING);
  });

  it("blur-fades from opacity 0 / y 20 / blur 8 and drops the filter once settled", () => {
    expect(revealVariants.hidden).toEqual({ opacity: 0, y: 20, filter: "blur(8px)" });
    expect(revealVariants.visible).toMatchObject({ opacity: 1, y: 0, filter: "blur(0px)", transitionEnd: { filter: "none" } });
  });

  it("springs the reveal when motion is allowed", () => {
    expect(revealTransition(false, 0.1)).toMatchObject({ type: "spring", stiffness: 300, damping: 30, delay: 0.1 });
  });

  it("degrades springs to fades under reduced motion", () => {
    const t = revealTransition(true, 0.1) as Record<string, unknown>;
    expect(t.type).toBeUndefined();
    expect(t.default).toEqual({ duration: 0 });
    expect(t.opacity).toEqual({ ...FADE, delay: 0.1 });
    expect(layoutTransition(true)).toEqual({ duration: 0 });
    expect(pageMotion(true)).toEqual({ initial: { opacity: 0 }, animate: { opacity: 1 }, transition: FADE });
  });
});

describe("GlassPanel", () => {
  it("renders the requested element with the glass surface", () => {
    render(
      <GlassPanel as="section" aria-label="Panel">
        content
      </GlassPanel>,
    );
    const panel = screen.getByRole("region", { name: "Panel" });
    expect(panel.tagName).toBe("SECTION");
    expect(panel.className).toMatch(/backdrop-blur-2xl/);
    expect(panel.className).toMatch(/backdrop-saturate-150/);
    expect(panel.className).toMatch(/shadow-glass/);
    expect(panel.className).toMatch(/rounded-3xl/);
  });

  it("inset surfaces never add a backdrop blur layer (safe to nest)", () => {
    expect(glassVariants({ variant: "inset" })).not.toMatch(/backdrop-/);
    expect(glassVariants({ variant: "default" })).toMatch(/backdrop-blur/);
    expect(glassVariants({ variant: "strong" })).toMatch(/backdrop-blur/);
  });

  it("spotlight follows the cursor through CSS variables and brightens the edge on hover", () => {
    const { container } = render(<GlassPanel spotlight>content</GlassPanel>);
    const panel = container.firstElementChild as HTMLElement;
    panel.getBoundingClientRect = () => ({ left: 10, top: 20, width: 200, height: 100 }) as DOMRect;
    expect(panel.className).toMatch(/hover:border-glass-edge-hover/);
    expect(panel.querySelector('[data-slot="glass-spotlight"]')).toHaveAttribute("aria-hidden");
    fireEvent.pointerMove(panel, { clientX: 60, clientY: 45 });
    expect(panel.style.getPropertyValue("--spot-x")).toBe("50px");
    expect(panel.style.getPropertyValue("--spot-y")).toBe("25px");
  });

  it("has no spotlight overlay unless asked", () => {
    const { container } = render(<GlassPanel>content</GlassPanel>);
    expect(container.querySelector('[data-slot="glass-spotlight"]')).toBeNull();
  });
});

describe("Aurora", () => {
  it("is decorative and animates with CSS only", () => {
    const { container } = render(<Aurora />);
    const root = container.firstElementChild as HTMLElement;
    expect(root).toHaveAttribute("aria-hidden");
    const blobs = root.querySelectorAll(".aurora-blob");
    expect(blobs).toHaveLength(3);
    for (const blob of blobs) {
      expect(blob.className).toMatch(/animate-aurora-/);
      expect(blob.className).toMatch(/motion-reduce:animate-none/);
      expect(blob.className).not.toMatch(/blur/);
    }
  });
});

describe("PillNav", () => {
  const items = [
    { href: "/chat", label: "Chat", icon: MessageSquare },
    { href: "/evals", label: "Evals" },
  ];

  it("marks only the active item and gives it the shared pill", () => {
    const { container } = render(<PillNav items={items} activeHref="/chat" layoutId="t" label="Main" />);
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Evals" })).not.toHaveAttribute("aria-current");
    expect(container.querySelectorAll('[data-slot="pill-indicator"]')).toHaveLength(1);
  });

  it("uses aria-current=location for in-page anchors", () => {
    render(<PillNav items={[{ href: "#top", label: "Overview" }]} activeHref="#top" layoutId="t" label="Sections" current="location" />);
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "location");
  });
});

describe("SegmentedTabs", () => {
  it("switches tabs and moves the indicator", async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    const items = [
      { value: "a", label: "Alpha" },
      { value: "b", label: "Beta" },
    ] as const;
    const { container, rerender } = render(
      <SegmentedTabs value="a" onValueChange={onValueChange} items={items} layoutId="seg" />,
    );
    expect(screen.getByRole("tab", { name: "Alpha" }).querySelector('[data-slot="tab-indicator"]')).not.toBeNull();
    await user.click(screen.getByRole("tab", { name: "Beta" }));
    expect(onValueChange).toHaveBeenCalledWith("b");
    rerender(<SegmentedTabs value="b" onValueChange={onValueChange} items={items} layoutId="seg" />);
    expect(screen.getByRole("tab", { name: "Beta" }).querySelector('[data-slot="tab-indicator"]')).not.toBeNull();
    expect(container.querySelectorAll('[data-slot="tab-indicator"]')).toHaveLength(1);
  });
});

describe("Dock", () => {
  it("renders labelled icon links; external ones open safely in a new tab", () => {
    render(
      <Dock
        label="Footer"
        items={[
          { href: "/chat", label: "Chat console", icon: MessageSquare },
          { href: "https://example.com/repo", label: "Source", icon: MessageSquare, external: true },
        ]}
      />,
    );
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat console" })).toHaveAttribute("href", "/chat");
    const ext = screen.getByRole("link", { name: /Source/ });
    expect(ext).toHaveAttribute("target", "_blank");
    expect(ext).toHaveAttribute("rel", "noreferrer");
    expect(ext).toHaveAccessibleName("Source (opens in a new tab)");
  });
});

describe("PageTransition", () => {
  it("enters with a spring slide when motion is allowed", () => {
    const { container } = render(<PageTransition>page</PageTransition>);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.opacity).toBe("0");
    expect(el.style.transform).toMatch(/translateY\(12px\)/);
  });
});
