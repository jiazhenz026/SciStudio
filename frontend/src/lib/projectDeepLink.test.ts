import { afterEach, describe, expect, it } from "vitest";

import { readProjectDeepLink, sameProjectPath } from "./projectDeepLink";

describe("projectDeepLink (#2385)", () => {
  afterEach(() => {
    delete (window as { scistudioDesktop?: unknown }).scistudioDesktop;
  });

  it("reads the project path and workflow, decoding spaces and unicode", () => {
    const search = `?project=${encodeURIComponent("/tmp/My Projects/细胞")}&workflow=qc%20run`;
    expect(readProjectDeepLink(search)).toEqual({
      project: "/tmp/My Projects/细胞",
      workflow: "qc run",
    });
  });

  it("treats a missing workflow as null and a missing project as no link", () => {
    expect(readProjectDeepLink("?project=%2Ftmp%2Fp")).toEqual({
      project: "/tmp/p",
      workflow: null,
    });
    expect(readProjectDeepLink("?workflow=main")).toBeNull();
    expect(readProjectDeepLink("?ui=ai")).toBeNull();
    expect(readProjectDeepLink("")).toBeNull();
  });

  it("ignores the link inside the desktop shell, which owns the session", () => {
    (window as { scistudioDesktop?: unknown }).scistudioDesktop = {};
    expect(readProjectDeepLink("?project=%2Ftmp%2Fp")).toBeNull();
  });

  it("compares paths across trailing and Windows separators", () => {
    expect(sameProjectPath("/tmp/p/", "/tmp/p")).toBe(true);
    expect(sameProjectPath("C:\\work\\p", "C:/work/p/")).toBe(true);
    expect(sameProjectPath("/tmp/p", "/tmp/q")).toBe(false);
  });
});
