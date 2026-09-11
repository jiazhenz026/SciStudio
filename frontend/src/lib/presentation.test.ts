import { afterEach, describe, expect, it } from "vitest";
import { cleanup, act, renderHook } from "@testing-library/react";
import { readPresentation, setPresentation, usePresentation } from "./presentation";

afterEach(() => {
  cleanup();
  delete window.scistudioDesktop;
  window.history.replaceState(null, "", "/");
});

describe("page presentation", () => {
  it("defaults to workbench and accepts only the explicit AI value", () => {
    for (const query of ["", "?ui=unknown", "?ui=workbench"]) {
      window.history.replaceState(null, "", `/${query}`);
      expect(readPresentation()).toBe("workbench");
    }
    window.history.replaceState(null, "", "/?ui=ai");
    expect(readPresentation()).toBe("ai");
  });

  it("updates subscribers without replacing prefix, other parameters, hash or history state", () => {
    window.history.replaceState({ page: 7 }, "", "/user/alice/scistudio/?project=demo#result");
    const { result } = renderHook(usePresentation);
    act(() => setPresentation("ai"));
    expect(result.current).toBe("ai");
    expect(window.location.pathname).toBe("/user/alice/scistudio/");
    expect(window.location.search).toBe("?project=demo&ui=ai");
    expect(window.location.hash).toBe("#result");
    expect(window.history.state).toEqual({ page: 7 });
    act(() => setPresentation("workbench"));
    expect(result.current).toBe("workbench");
  });

  it("responds to browser history and ignores cross-page storage preferences", () => {
    const { result } = renderHook(usePresentation);
    act(() => {
      window.history.replaceState(null, "", "/?ui=ai");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(result.current).toBe("ai");
    act(() =>
      window.dispatchEvent(new StorageEvent("storage", { key: "ui", newValue: "workbench" })),
    );
    expect(result.current).toBe("ai");
  });
});

it("locks Electron to workbench and ignores attempts to change its URL mode", () => {
  window.scistudioDesktop = {
    platform: "win32",
    versions: { electron: "test", chrome: "test" },
    relaunch: async () => {},
    onMenuAction: () => () => {},
  };
  window.history.replaceState(null, "", "/?ui=ai");
  expect(readPresentation()).toBe("workbench");
  setPresentation("workbench");
  expect(window.location.search).toBe("?ui=ai");
  expect(readPresentation()).toBe("workbench");
});
