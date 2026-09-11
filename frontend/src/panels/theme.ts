import type { PanelTheme } from "./types";

export function readPanelTheme(): PanelTheme {
  const root = document.documentElement;
  const style = getComputedStyle(root);
  const names = new Set(["--ss-canvas", "--ss-ink", "--ss-ember", "--ss-pine", "--ss-sea", "--ss-sand"]);
  for (let i = 0; i < style.length; i++) if (style[i].startsWith("--ss-")) names.add(style[i]);
  return {
    mode: root.classList.contains("dark") || root.dataset.theme === "dark" ? "dark" : "light",
    tokens: Object.fromEntries([...names].map((name) => [name, style.getPropertyValue(name).trim()])),
  };
}
export function observePanelTheme(callback: (theme: PanelTheme) => void) {
  const observer = new MutationObserver(() => callback(readPanelTheme()));
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-theme"] });
  return () => observer.disconnect();
}
