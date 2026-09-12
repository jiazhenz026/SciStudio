/**
 * Contracts over the *set* of built-in panels rather than over any one of them
 * (ADR-054 Phase B). Each panel's own behaviour is pinned in its own file —
 * arrayPanel, collectionPanel, compositePanel, dataframePanel, seriesPanel,
 * textPanel, artifactPanel, plotPanel, fallbackPanel, dataRouterPanel,
 * pairEditorPanel — and what belongs here is what has to hold for all of them,
 * including the ones added later.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const BUILTIN = resolve(process.cwd(), "../src/scistudio/panels/builtin");
const HERE = resolve(process.cwd(), "src/panels");

const panelIds = readdirSync(BUILTIN, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

const entryOf = (id: string) => readFileSync(resolve(BUILTIN, id, "index.html"), "utf8");
const scriptOf = (id: string) => readFileSync(resolve(BUILTIN, id, "panel.js"), "utf8");

/** The file each panel's behaviour is pinned in. */
const COVERAGE: Record<string, string> = {
  "core.array.basic": "arrayPanel.test.ts",
  "core.artifact.basic": "artifactPanel.test.ts",
  "core.base.fallback": "fallbackPanel.test.ts",
  "core.collection.basic": "collectionPanel.test.ts",
  "core.composite.basic": "compositePanel.test.ts",
  "core.dataframe.basic": "dataframePanel.test.ts",
  "core.interactive.data_router": "dataRouterPanel.test.ts",
  "core.interactive.pair_editor": "pairEditorPanel.test.ts",
  "core.plot.basic": "plotPanel.test.ts",
  "core.series.basic": "seriesPanel.test.ts",
  "core.text.basic": "textPanel.test.ts",
};

describe("every built-in panel", () => {
  it("has a file pinning what it renders", () => {
    // A panel added with no named file fails here, rather than shipping with
    // the set's contracts as its only coverage.
    expect(Object.keys(COVERAGE).sort()).toEqual(panelIds);
    for (const file of Object.values(COVERAGE)) {
      expect(existsSync(resolve(HERE, file)), file).toBe(true);
    }
  });

  it.each(panelIds)("%s wears the application's look", (id) => {
    const html = entryOf(id);
    /*
     * The shared stylesheet is where the host's theme tokens land. A panel
     * carrying its own copy of the styling drifts from the product the first
     * time either changes — and in dark mode it drifts into being unreadable,
     * which is how the pair editor's fixed pastels were found.
     */
    expect(html).toContain('href="../../sdk/1/panel.css"');
    expect(html).toContain('src="../../sdk/1/scistudio-panel.js"');
  });

  it.each(panelIds)("%s is loaded the way it is written", (id) => {
    const html = entryOf(id);
    const script = scriptOf(id);
    // An ES module loaded as a classic script fails at its first `export`, and
    // the only thing the reader sees is "Script error." in the frame.
    if (/^\s*(export|import)\s/m.test(script)) {
      expect(html).toMatch(/<script type="module" src="panel\.js">/);
    }
  });

  it.each(panelIds)("%s reports a failure instead of rendering nothing", (id) => {
    // A failed read has to reach the host's error surface; a blank frame leaves
    // the reader with nothing to act on and no way to tell it apart from a
    // panel that legitimately has nothing to show.
    expect(scriptOf(id)).toContain("reportError");
  });
});

describe("interactive panels leave the way out to the host", () => {
  const interactive = panelIds.filter((id) => id.startsWith("core.interactive."));

  it("is asserting over the interactive panels that exist", () => {
    expect(interactive).toEqual(["core.interactive.data_router", "core.interactive.pair_editor"]);
  });

  it.each(interactive)("%s draws no Cancel of its own", (id) => {
    /*
     * The window around an interactive frame offers Cancel and Escape from
     * outside the frame, so that no panel can fail to provide a way out of a
     * waiting block or hide the one there is. A panel that needs to withdraw
     * from code calls `api.cancel()`; one that draws its own button duplicates
     * a control and implies the guarantee lives somewhere it does not.
     */
    expect(scriptOf(id)).not.toMatch(/>\s*Cancel\s*</);
  });
});
