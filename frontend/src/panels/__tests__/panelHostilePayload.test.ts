/*
 * What the shipped panel documents do when the payload is hostile (#2229).
 *
 * A panel is a plain HTML document that renders whatever the host hands it over
 * `postMessage`, and the provider that filled that payload is not necessarily a
 * built-in one — a package ships providers, and ADR-054 exists so that people
 * and agents author panels too. So "the payload is trusted" is not a property
 * this layer has, and these tests are the ones that say so: each drives a
 * shipped document with a value a hostile provider would send and asserts the
 * document neutralises it.
 *
 * The documents are read from the tree rather than copied, because a copy is
 * the one thing that cannot catch a change to the original. The driving
 * technique — evaluate the document's own script, capture its `message`
 * listener as it registers, hand it `init` — is the same one
 * `App.parts/InteractiveModals.parts/__tests__/tutorialReviewPanel.test.ts`
 * uses; what is different here is only the payload.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

const PANEL_MESSAGE_MARKER = 1;

const PLOT_PANEL = "src/scistudio/panels/builtin/core.plot.basic/index.html";
const REVIEW_PANEL =
  "src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/index.html";

interface PanelMessage {
  readonly type: string;
  readonly payload: Record<string, unknown>;
}

/**
 * The shipped document's body markup and its script.
 *
 * vitest runs with the frontend package as its working directory, so the
 * repository root is one level up.
 */
function readPanelDocument(relativePath: string) {
  const text = readFileSync(join(process.cwd(), "..", relativePath), "utf8");
  return {
    body: (/<body[^>]*>([\s\S]*?)<script>/i.exec(text) ?? [])[1] ?? "",
    script: (/<script>([\s\S]*?)<\/script>/i.exec(text) ?? [])[1] ?? "",
  };
}

/** Evaluate a panel document, hand it `init`, and return what it sent back. */
function mountPanel(
  relativePath: string,
  init: Record<string, unknown>,
): { sent: PanelMessage[]; send: (type: string, payload: Record<string, unknown>) => void } {
  const { body, script } = readPanelDocument(relativePath);
  if (script === "") throw new Error(`${relativePath} carries no inline script`);

  const sent: PanelMessage[] = [];
  let listener: ((event: { data: unknown }) => void) | null = null;

  Object.defineProperty(window, "parent", {
    configurable: true,
    value: {
      postMessage: (message: { type: string; payload: Record<string, unknown> }) =>
        sent.push({ type: message.type, payload: message.payload }),
    },
  });

  document.body.innerHTML = body;

  const addEventListener = window.addEventListener.bind(window);
  window.addEventListener = ((type: string, handler: unknown) => {
    if (type === "message") listener = handler as (event: { data: unknown }) => void;
    else addEventListener(type, handler as EventListener);
  }) as typeof window.addEventListener;
  try {
    new Function(script)();
  } finally {
    window.addEventListener = addEventListener as typeof window.addEventListener;
  }
  if (listener === null) throw new Error(`${relativePath} registered no message listener`);
  const deliver = listener as (event: { data: unknown }) => void;

  const send = (type: string, payload: Record<string, unknown>) =>
    deliver({
      data: { scistudio_panel: PANEL_MESSAGE_MARKER, token: "tok-1", type, payload },
    });

  send("init", init);
  return { sent, send };
}

function mountPlotPanel(target: Record<string, unknown>) {
  return mountPanel(PLOT_PANEL, {
    api_version: "1",
    panel_id: "core.plot.basic",
    capability: "displaying",
    target,
    read_limits: { max_rows: 1000, max_bytes: 1_000_000 },
    asset_base_url: "/api/panels/assets/core.plot.basic/",
    restored_state: null,
  });
}

/** Every URL the mounted document actually put in a `src`. */
function renderedSources(): string[] {
  return [...document.querySelectorAll("img, iframe")]
    .map((node) => node.getAttribute("src"))
    .filter((value): value is string => value !== null);
}

// ---------------------------------------------------------------------------
// core.plot.basic — a `src` out of the payload
// ---------------------------------------------------------------------------

/*
 * Each of these is a string a hostile provider could put in `payload.src`, and
 * the reason it must not reach an element:
 *
 * - `javascript:` in the `<iframe>` the PDF branch builds runs script in this
 *   frame. The frame is granted `allow-scripts` and a nested frame inherits it,
 *   so the sandbox does not stop this; what runs holds the panel's `postMessage`
 *   token and can speak to the host as the panel.
 * - an absolute URL to another host is an outbound request that leaves the
 *   application carrying whatever the attacker put in the path — in an `<img>`
 *   as much as in an `<iframe>`, which is why the `<img>` is not excused.
 * - `//host/x` is that second one wearing a relative path's clothes.
 * - a browser strips TAB, LF and CR out of a URL before parsing it, so a check
 *   that ran on the string as it arrived would see a path where the browser
 *   sees a protocol-relative URL.
 * - `data:text/html` and `data:image/svg+xml` are documents, not pictures: in
 *   the `<iframe>` branch either would execute script.
 */
const HOSTILE_SOURCES: ReadonlyArray<readonly [string, string]> = [
  ["a javascript url", "javascript:parent.postMessage(1,'*')"],
  ["a javascript url with a leading space", "  javascript:alert(1)"],
  ["a javascript url in mixed case", "JaVaScRiPt:alert(1)"],
  ["an absolute url to another host", "http://attacker.example/leak.png"],
  ["a protocol-relative url", "//attacker.example/leak.png"],
  ["a protocol-relative url hidden behind a tab", "/\t/attacker.example/leak.png"],
  ["an html data uri", "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="],
  ["an svg data uri", "data:image/svg+xml;base64,PHN2Zy8+"],
  ["a media type that only starts like an allowed one", "data:image/pngevil,AAAA"],
  ["a vbscript url", "vbscript:msgbox(1)"],
  ["a file url", "file:///etc/passwd"],
];

describe("core.plot.basic — a payload-supplied figure source", () => {
  it.each(HOSTILE_SOURCES)("refuses %s", (_name, src) => {
    const { sent } = mountPlotPanel({ payload: { format: "png", src } });

    expect(sent[0]).toEqual({ type: "ready", payload: { api_version: "1" } });
    expect(renderedSources()).toEqual([]);
    expect(document.body.textContent).toContain("This plot was not rendered");
  });

  it.each(HOSTILE_SOURCES)("refuses %s in the PDF frame too", (_name, src) => {
    // The PDF branch is the one that builds an `<iframe>`, which is where a
    // `javascript:` url would actually execute. It gets its own pass because
    // "an `<img>` cannot run what it loads" is not an argument that covers it.
    mountPlotPanel({ payload: { format: "pdf", src } });

    expect(renderedSources()).toEqual([]);
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("renders an inline PNG, which is what the provider actually sends", () => {
    const src = "data:image/png;base64,iVBORw0KGgo=";
    mountPlotPanel({ payload: { format: "png", src } });

    expect(renderedSources()).toEqual([src]);
  });

  it("renders an inline PDF in the frame", () => {
    const src = "data:application/pdf;base64,JVBERi0=";
    mountPlotPanel({ payload: { format: "pdf", src } });

    expect(renderedSources()).toEqual([`${src}#view=Fit`]);
  });

  it("refuses an inline PDF in the image branch and an inline PNG in the frame", () => {
    // The two elements do not accept the same media types, because they do not
    // execute what they load in the same way.
    mountPlotPanel({ payload: { format: "png", src: "data:application/pdf;base64,JVBERi0=" } });
    expect(renderedSources()).toEqual([]);

    mountPlotPanel({ payload: { format: "pdf", src: "data:image/png;base64,iVBORw0KGgo=" } });
    expect(renderedSources()).toEqual([]);
  });

  it("still builds the asset-route url when the payload names only a path", () => {
    mountPlotPanel({ payload: { format: "png", path: "/tmp/run-1/figure.png" } });

    expect(renderedSources()).toEqual(["/api/panels/assets/core.plot.basic/figure.png"]);
  });
});

// ---------------------------------------------------------------------------
// tutorial.review_labels — a label id out of the payload
// ---------------------------------------------------------------------------

/** A slide whose grid is filled with the given label ids. */
function slide(ids: unknown[]) {
  return {
    grid: Array.from({ length: 4 }, (_, y) =>
      Array.from({ length: 4 }, (_, x) => ids[(y * 4 + x) % ids.length]),
    ),
    image: Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => 120)),
    labels: [
      { id: ids[0], area: 1500 },
      { id: ids[1], area: 1500 },
      // Far below the median, so the panel doubts it and rings it — which is
      // the code path that keys a map by the id.
      { id: ids[2], area: 10 },
    ],
  };
}

function mountReviewPanel(payload: Record<string, unknown>) {
  return mountPanel(REVIEW_PANEL, {
    api_version: "1",
    panel_id: "tutorial.review_labels",
    capability: "producing",
    target: payload,
    bindings: { prompt: { type: "interactive_prompt", snapshot: payload } },
    read_limits: { max_rows: 1000, max_bytes: 1_000_000 },
    asset_base_url: "/api/panels/assets/tutorial.review_labels/",
    restored_state: null,
  });
}

/** Every 2-D context method the panel called during the mount, in order. */
let drawn: string[] = [];

/** The four ids that are also names every plain object already answers to. */
const INHERITED_NAMES = ["__proto__", "toString", "constructor", "valueOf"] as const;

describe("tutorial.review_labels — a label id out of the payload", () => {
  beforeEach(() => {
    // jsdom ships no canvas backend and the panel draws on every render. A
    // context that accepts every call is enough — what is wanted is that the
    // drawing code, which is where the maps are keyed, actually runs — and
    // recording the calls is how a test can see what it drew.
    drawn = [];
    (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).getContext = () =>
      new Proxy(
        {},
        {
          get:
            (_target, property) =>
            (...args: unknown[]) => {
              drawn.push(String(property));
              return args.length === 0 ? undefined : undefined;
            },
        },
      );
  });

  it.each(INHERITED_NAMES)("still rings the label it doubts when its id is %s", (name) => {
    // The panel rings what it doubts, and the ring is the whole ask: it marks
    // what the reader is being asked to look at. Every map on that path was a
    // plain object keyed by an id out of the payload, and a plain object
    // already answers to these four names — so `slide.removed[id]` reported the
    // label as struck out before the reader had touched it, the ring was
    // skipped as a question already answered, and the reader was asked to
    // confirm a judgement they were never shown.
    mountReviewPanel({ slides: [slide([1, 2, name])] });

    expect(drawn).toContain("strokeRect");
  });

  it("draws no ring when the doubted label has already been struck out", () => {
    // The other side of that assertion, so the one above is about the ring
    // rather than about the panel drawing something on every render.
    mountReviewPanel({ slides: [slide([1, 2, 3])] });
    const before = drawn.filter((call) => call === "strokeRect").length;
    expect(before).toBeGreaterThan(0);

    (document.querySelector('[data-label-id="3"]') as HTMLElement).click();

    expect(drawn.filter((call) => call === "strokeRect").length).toBe(before);
  });

  it.each(INHERITED_NAMES)("does not treat the id %s as an already-struck-out label", (name) => {
    mountReviewPanel({ slides: [slide([1, 2, name])] });

    const rows = [...document.querySelectorAll("[data-label-id]")];
    expect(rows).toHaveLength(3);
    expect(rows.filter((row) => row.className.includes("gone"))).toEqual([]);
  });

  it("leaves Object.prototype alone when an id is __proto__", () => {
    // The standing invariant behind all of the above, and the one the CodeQL
    // alert names. It holds today for a reason that is an accident rather than
    // a design — `box.top = y` runs only when `y < box.top`, and `box.top` on
    // `Object.prototype` is `undefined`, so every comparison is false and
    // nothing is written. A null-prototype map makes it hold because there is
    // no prototype to reach; this test is what says so afterwards.
    const { sent } = mountReviewPanel({ slides: [slide([1, 2, "__proto__"])] });

    expect(sent[0]).toEqual({ type: "ready", payload: { api_version: "1" } });
    const probe = {} as Record<string, unknown>;
    expect(probe.top).toBeUndefined();
    expect(probe.left).toBeUndefined();
    expect(probe.bottom).toBeUndefined();
    expect(probe.right).toBeUndefined();
    expect(Object.getPrototypeOf({})).toBe(Object.prototype);
  });

  it("emits a Python literal that carries no NaN when an id is not a number", () => {
    // The emission is code the block runs, so a non-numeric id must not reach
    // it as `NaN` — a syntax error the reader would meet as a broken cell
    // rather than as a bad payload. This is the regression the null-prototype
    // map would otherwise introduce: with a plain object `removed["__proto__"]`
    // was silently dropped, and with a null-prototype one it is a real key.
    const { sent } = mountReviewPanel({ slides: [slide([1, 2, "__proto__"])] });

    const rows = [...document.querySelectorAll("[data-label-id]")] as HTMLElement[];
    rows.forEach((row) => row.click());
    const emits = sent.filter((message) => message.type === "emit");
    expect(emits.length).toBeGreaterThan(0);
    expect(String(emits[emits.length - 1].payload.code)).not.toContain("NaN");
    expect(String(emits[emits.length - 1].payload.code)).toContain("removed = [[1, 2]]");
  });
});
