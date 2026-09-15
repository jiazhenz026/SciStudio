/**
 * The questionnaire components in `sdk/1/panel-ui.js` (ADR-054 MiniApp FR-049/FR-050, #2447).
 *
 * Rendered for real through the vendored Preact in jsdom, from the files the
 * frame is served. The spec cases are shared with the Python validator
 * (`tests/fixtures/questionnaire/cases.json`): a spec Python refuses must show
 * the error state here, and one it accepts must render every question.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it, vi } from "vitest";

const ROOT = resolve(process.cwd(), "..");
const PANELS = resolve(ROOT, "src/scistudio/panels");
const CASES = JSON.parse(
  readFileSync(resolve(ROOT, "tests/fixtures/questionnaire/cases.json"), "utf8"),
) as { cases: Array<{ name: string; valid: boolean; spec: unknown }> };
const GOOD = CASES.cases[0].spec as {
  questions: Array<{ id: string; type: string; options?: Array<{ value: string }> }>;
};

type Html = (s: TemplateStringsArray, ...v: unknown[]) => unknown;
let ui: Record<string, unknown>;
let preact: { html: Html; render: (v: unknown, el: Element) => void };

function dataUrl(source: string) {
  return `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
}

beforeAll(async () => {
  const preactSource = readFileSync(
    resolve(PANELS, "lib/preact-htm@3.1.1/dist/preact-standalone.module.js"),
    "utf8",
  );
  const preactUrl = dataUrl(preactSource);
  preact = (await import(/* @vite-ignore */ preactUrl)) as typeof preact;
  const uiSource = readFileSync(resolve(PANELS, "sdk/1/panel-ui.js"), "utf8").replace(
    /"[^"]*preact-standalone\.module\.js"/g,
    JSON.stringify(preactUrl),
  );
  ui = (await import(/* @vite-ignore */ dataUrl(uiSource))) as Record<string, unknown>;
});

function mount(vnode: unknown): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  preact.render(vnode, host);
  return host;
}

const flush = () => new Promise((r) => setTimeout(r, 0));

function click(el: Element | null) {
  expect(el).toBeTruthy();
  (el as HTMLElement).click();
}

describe("Questionnaire", () => {
  it("exports the question components", () => {
    for (const name of [
      "Questionnaire",
      "Question",
      "SingleChoiceQuestion",
      "MultipleChoiceQuestion",
      "TextQuestion",
      "NumberQuestion",
      "SubmitBar",
    ]) {
      expect(typeof ui[name], name).toBe("function");
    }
  });

  it.each(CASES.cases.map((c) => [c.name, c] as const))(
    "agrees with the Python validator: %s",
    (_name, testCase) => {
      const host = mount(
        preact.html`<${ui.Questionnaire as never} spec=${testCase.spec} onSubmit=${() => null} />`,
      );
      const invalid = host.querySelector('[data-testid="questionnaire-invalid"]');
      if (testCase.valid) {
        expect(invalid).toBeNull();
        const questions = (testCase.spec as { questions: unknown[] }).questions;
        expect(host.querySelectorAll(".panel-question")).toHaveLength(questions.length);
        expect(host.querySelector('[data-testid="questionnaire-submit"]')).toBeTruthy();
      } else {
        expect(invalid, "a broken spec shows an error state, not a form").toBeTruthy();
        expect(host.querySelector('[data-testid="questionnaire-submit"]')).toBeNull();
      }
    },
  );

  it("offers Decide for me on every question and submits with nothing answered", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ notified: true, message: "Sent." });
    const host = mount(
      preact.html`<${ui.Questionnaire as never} spec=${GOOD} onSubmit=${onSubmit} />`,
    );
    for (const q of GOOD.questions) {
      expect(host.querySelector(`[data-decide-for-me="${q.id}"]`), q.id).toBeTruthy();
    }
    click(host.querySelector('[data-testid="questionnaire-submit"]'));
    await flush();
    const answers = onSubmit.mock.calls[0][0] as Record<string, { status: string }>;
    expect(Object.keys(answers)).toEqual(GOOD.questions.map((q) => q.id));
    expect(new Set(Object.values(answers).map((a) => a.status))).toEqual(new Set(["skipped"]));
    expect(host.querySelector(".panel-submit-message")?.textContent).toBe("Sent.");
  });

  it("records choices, decide-for-me, text and numbers distinctly", async () => {
    const onSubmit = vi
      .fn()
      .mockResolvedValue({ notified: false, message: "Go back to your AI chat." });
    const host = mount(
      preact.html`<${ui.Questionnaire as never} spec=${GOOD} onSubmit=${onSubmit} />`,
    );
    const card = (id: string) => host.querySelector(`[data-question-id="${id}"]`)!;

    click(card("chart").querySelector('[data-option="pca"]'));
    await flush();
    click(card("colour_by").querySelector('[data-option="qc"]'));
    await flush();
    click(card("colour_by").querySelector('[data-option="cluster"]'));
    await flush();
    click(card("notes").querySelector("[data-decide-for-me]"));
    await flush();
    const genes = card("top_genes").querySelector("input") as HTMLInputElement;
    genes.value = "25";
    genes.dispatchEvent(new Event("input", { bubbles: true }));
    await flush();

    expect(card("chart").getAttribute("data-status")).toBe("answered");
    expect(card("notes").getAttribute("data-status")).toBe("decide_for_me");
    click(host.querySelector('[data-testid="questionnaire-submit"]'));
    await flush();
    expect(onSubmit.mock.calls[0][0]).toEqual({
      chart: { status: "answered", value: "pca" },
      colour_by: { status: "answered", value: ["qc", "cluster"] },
      notes: { status: "decide_for_me" },
      top_genes: { status: "answered", value: 25 },
      opacity: { status: "skipped" },
    });
    const message = host.querySelector(".panel-submit-message");
    expect(message?.getAttribute("data-kind")).toBe("return");
    expect(message?.textContent).toContain("AI chat");
  });

  it("clears a choice or decide-for-me back to skipped when pressed again", async () => {
    const onSubmit = vi.fn().mockResolvedValue({});
    const host = mount(
      preact.html`<${ui.Questionnaire as never} spec=${GOOD} onSubmit=${onSubmit} />`,
    );
    const card = host.querySelector('[data-question-id="chart"]')!;
    click(card.querySelector('[data-option="umap"]'));
    await flush();
    click(card.querySelector('[data-option="umap"]'));
    await flush();
    expect(card.getAttribute("data-status")).toBe("skipped");
    click(card.querySelector("[data-decide-for-me]"));
    await flush();
    click(card.querySelector("[data-decide-for-me]"));
    await flush();
    expect(card.getAttribute("data-status")).toBe("skipped");
  });

  it("shows a refused submit as an error and keeps the form", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("Answer to chart is wrong"));
    const host = mount(
      preact.html`<${ui.Questionnaire as never} spec=${GOOD} onSubmit=${onSubmit} />`,
    );
    click(host.querySelector('[data-testid="questionnaire-submit"]'));
    await flush();
    await flush();
    const message = host.querySelector(".panel-submit-message");
    expect(message?.getAttribute("data-kind")).toBe("error");
    expect(message?.textContent).toContain("Answer to chart is wrong");
    expect(host.querySelectorAll(".panel-question")).toHaveLength(GOOD.questions.length);
  });

  it("tells the author when no submit handler was passed", async () => {
    const host = mount(preact.html`<${ui.Questionnaire as never} spec=${GOOD} />`);
    click(host.querySelector('[data-testid="questionnaire-submit"]'));
    await flush();
    expect(host.querySelector(".panel-submit-message")?.textContent).toContain("submitAnswers");
  });

  it("draws a range question as a slider", () => {
    const range = GOOD.questions.find((q) => q.type === "range");
    const host = mount(preact.html`<${ui.Question as never} question=${range} />`);
    expect(host.querySelector('input[type="range"]')).toBeTruthy();
  });
});
