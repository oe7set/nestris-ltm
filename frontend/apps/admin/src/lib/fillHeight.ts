// Svelte action: let a scrolling side panel reach down to the bottom of the
// window, whatever sits above it. Sets ``--fill-h`` on the element; the CSS
// decides whether to use it (``max-height: var(--fill-h)``), so a media query
// can still switch it off on narrow screens.

export function fillHeight(node: HTMLElement, gap = 12): { destroy(): void } {
  let frame = 0;
  const update = (): void => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const top = Math.max(node.getBoundingClientRect().top, 0);
      node.style.setProperty("--fill-h", `${Math.max(240, Math.floor(innerHeight - top - gap))}px`);
    });
  };
  update();
  addEventListener("resize", update);
  // Page scroll moves the panel up or down; content above it may change size.
  addEventListener("scroll", update, true);
  const observer = new ResizeObserver(update);
  observer.observe(document.body);
  // Content above the element may change without the body changing size
  // (e.g. a header hidden in focus mode); the parent notices that.
  if (node.parentElement) observer.observe(node.parentElement);
  return {
    destroy() {
      cancelAnimationFrame(frame);
      removeEventListener("resize", update);
      removeEventListener("scroll", update, true);
      observer.disconnect();
    },
  };
}
