/**
 * Contract coverage for the shared panel component set (SDK major 1).
 *
 * Every component here is rendered for real through Preact in jsdom, because the
 * failures this set produces are silent: a prop that never reaches the DOM node,
 * a ref that resolves to a component instance instead of an element, an icon
 * whose data shape was assumed rather than checked. Each of those shipped once.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const SDK = resolve(PANELS, "sdk/1");

// The panel set and Preact are served to the frame as ES modules; import them
// the same way so the test exercises the real files, not a copy.
let ui: Record<string, unknown>;
let preact: { html: unknown; render: (v: unknown, el: Element) => void };

/**
 * Import a vendored/SDK module by its real contents. A plain dynamic import of
 * these paths goes through the bundler's resolver, which treats the versioned
 * `name@version` directory as a bare specifier; evaluating the file as a data
 * URL runs exactly what the frame is served instead.
 */
async function importPanelModule(file: string, rewrite?: (src: string) => string) {
  const source = readFileSync(file, "utf8");
  const body = rewrite ? rewrite(source) : source;
  return import(
    /* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(body).toString("base64")}`
  );
}

beforeAll(async () => {
  const preactFile = resolve(PANELS, "lib/preact-htm@3.1.1/dist/preact-standalone.module.js");
  preact = (await importPanelModule(preactFile)) as typeof preact;
  // panel-ui imports Preact by the frame-relative path; point that at the same
  // data URL so both modules share one Preact instance (hooks require it).
  const preactUrl = `data:text/javascript;base64,${Buffer.from(readFileSync(preactFile, "utf8")).toString("base64")}`;
  ui = (await importPanelModule(resolve(SDK, "panel-ui.js"), (src) =>
    src.replace(/"[^"]*preact-standalone\.module\.js"/g, JSON.stringify(preactUrl)),
  )) as Record<string, unknown>;
});

function mount(vnode: unknown): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  preact.render(vnode, host);
  return host;
}

describe("panel-ui — every component renders a DOM node", () => {
  it("exports the documented set", () => {
    for (const name of [
      "Panel",
      "Stack",
      "Row",
      "Spacer",
      "Card",
      "Meta",
      "Hint",
      "Label",
      "Badge",
      "Button",
      "Input",
      "Select",
      "Field",
      "ScrollArea",
      "Table",
      "Legend",
      "ItemGrid",
      "Item",
      "Pager",
      "Icon",
      "ErrorState",
      "EmptyState",
    ]) {
      expect(typeof ui[name], `${name} is exported`).toBe("function");
    }
  });

  it("renders each simple component with its semantic class", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const cases: Array<[string, string]> = [
      ["Panel", "panel"],
      ["Stack", "panel-stack"],
      ["Row", "panel-row"],
      ["Card", "panel-card"],
      ["Hint", "panel-hint"],
      ["Label", "panel-label"],
      ["Badge", "panel-badge"],
      ["Button", "panel-button"],
      ["ScrollArea", "panel-scroll"],
      ["Table", "panel-table"],
      ["ItemGrid", "panel-grid"],
      ["Item", "panel-item"],
      ["ErrorState", "panel-error"],
      ["EmptyState", "panel-empty"],
    ];
    for (const [name, cls] of cases) {
      const host = mount(html`<${ui[name] as never}>x<//>`);
      expect(host.querySelector(`.${cls}`), `${name} renders .${cls}`).toBeTruthy();
    }
  });
});

describe("panel-ui — props reach the DOM", () => {
  it("forwards elementRef to the real element, not the component", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    // A plain `ref` on a function component silently resolves to the component;
    // every container in this set takes `elementRef` instead. This is the bug
    // that broke the array panel's scroll measurement.
    for (const name of [
      "Panel",
      "Stack",
      "Row",
      "Card",
      "ScrollArea",
      "Table",
      "ItemGrid",
      "Item",
      "Button",
      "Input",
    ]) {
      const box: { current: unknown } = { current: null };
      mount(html`<${ui[name] as never} elementRef=${box} />`);
      expect(box.current, `${name} elementRef is an element`).toBeInstanceOf(HTMLElement);
    }
  });

  it("passes through arbitrary attributes and merges class names", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(
      html`<${ui.Card as never} class="extra" data-testid="probe" title="t">body<//>`,
    );
    const node = host.querySelector("[data-testid=probe]") as HTMLElement;
    expect(node).toBeTruthy();
    expect(node.className).toContain("panel-card");
    expect(node.className).toContain("extra");
    expect(node.getAttribute("title")).toBe("t");
  });

  it("wires Button and Input handlers", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    let clicked = 0;
    let typed = "";
    const host = mount(html`
      <div>
        <${ui.Button as never} onClick=${() => (clicked += 1)}>go<//>
        <${ui.Input as never}
          value="a"
          onInput=${(e: Event) => (typed = (e.target as HTMLInputElement).value)}
        />
      </div>
    `);
    (host.querySelector("button") as HTMLButtonElement).click();
    const input = host.querySelector("input") as HTMLInputElement;
    input.value = "b";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    expect(clicked).toBe(1);
    expect(typed).toBe("b");
  });
});

describe("panel-ui — composite components", () => {
  it("Meta emphasises the first item and lists the rest", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(
      html`<${ui.Meta as never} items=${["Array", "shape [3, 3]", "", null, "dtype float64"]} />`,
    );
    const spans = [...host.querySelectorAll("span")];
    expect(spans[0].className).toContain("panel-meta-key");
    expect(spans[0].textContent).toBe("Array");
    // Empty and nullish entries are dropped rather than rendered as gaps.
    expect(spans.map((s) => s.textContent)).toEqual(["Array", "shape [3, 3]", "dtype float64"]);
  });

  it("Field lays out name, control and readout", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(
      html`<${ui.Field as never} name="z (10)" readout="3 / 9">
        <${ui.Input as never} type="range" />
      <//>`,
    );
    expect(host.querySelector(".panel-field-name")?.textContent).toBe("z (10)");
    expect(host.querySelector(".panel-readout")?.textContent).toBe("3 / 9");
    expect(host.querySelector("input[type=range]")).toBeTruthy();
  });

  it("Legend renders the ramp between its bounds", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(
      html`<${ui.Legend as never} min="-1" mid="0" max="3" stops=${["red", "white", "blue"]} />`,
    );
    const ramp = host.querySelector(".panel-legend-ramp") as HTMLElement;
    expect(ramp.getAttribute("style")).toContain("linear-gradient");
    expect(host.textContent).toContain("-1");
    expect(host.textContent).toContain("3");
  });

  it("Select renders options from plain values and {value,label} pairs", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(
      html`<${ui.Select as never} options=${[16, { value: 32, label: "32×32" }]} />`,
    );
    const options = [...host.querySelectorAll("option")];
    expect(options.map((o) => o.value)).toEqual(["16", "32"]);
    expect(options[1].textContent).toBe("32×32");
  });

  it("Pager disables the ends and reports the page", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const first = mount(html`<${ui.Pager as never} page=${1} totalPages=${4} />`);
    const buttons = [...first.querySelectorAll("button")] as HTMLButtonElement[];
    expect(buttons[0].disabled).toBe(true);
    expect(buttons[1].disabled).toBe(false);
    expect(first.textContent).toContain("page 1/4");
    // Pagination is navigation, never a warning that the data is partial (#1886).
    expect(first.textContent?.toLowerCase()).not.toContain("truncated");
    expect(first.textContent?.toLowerCase()).not.toContain("incomplete");

    const last = mount(
      html`<${ui.Pager as never} page=${4} totalPages=${4} label="rows 151–200 of 200" />`,
    );
    const lastButtons = [...last.querySelectorAll("button")] as HTMLButtonElement[];
    expect(lastButtons[1].disabled).toBe(true);
    expect(last.textContent).toContain("rows 151–200 of 200");
  });

  it("Item exposes the name, sub-line and click", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    let opened = 0;
    const host = mount(
      html`<${ui.Item as never} name="sample.tif" sub="Image" onClick=${() => (opened += 1)} />`,
    );
    expect(host.querySelector(".panel-item-name")?.textContent).toBe("sample.tif");
    expect(host.querySelector(".panel-item-sub")?.textContent).toBe("Image");
    (host.querySelector("button") as HTMLButtonElement).click();
    expect(opened).toBe(1);
  });
});

describe("panel-ui — Icon against the real lucide build", () => {
  beforeAll(() => {
    // Load the vendored UMD bundle the way the frame does.
    const src = readFileSync(resolve(PANELS, "lib/lucide@1.45.0/dist/lucide.min.js"), "utf8");
    const module = { exports: {} as Record<string, unknown> };
    new Function("window", "module", "exports", "self", src)(
      window as unknown as Record<string, unknown>,
      module,
      module.exports,
      window as unknown as Record<string, unknown>,
    );
    if (!(window as unknown as { lucide?: unknown }).lucide) {
      (window as unknown as { lucide: unknown }).lucide = module.exports;
    }
  });

  it("renders an svg from lucide's child-element arrays", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(html`<${ui.Icon as never} name="Activity" />`);
    const svg = host.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("viewBox")).toBe("0 0 24 24");
    // The icon's geometry must actually be in the DOM, not an empty shell.
    expect(svg?.children.length ?? 0).toBeGreaterThan(0);
  });

  it("accepts the kebab-case spelling", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(html`<${ui.Icon as never} name="chevron-right" />`);
    expect(host.querySelector("svg")?.children.length ?? 0).toBeGreaterThan(0);
  });

  it("renders nothing for an unknown icon instead of throwing", () => {
    const html = preact.html as (s: TemplateStringsArray, ...v: unknown[]) => unknown;
    const host = mount(html`<${ui.Icon as never} name="definitely-not-an-icon" />`);
    expect(host.querySelector("svg")).toBeNull();
  });
});
