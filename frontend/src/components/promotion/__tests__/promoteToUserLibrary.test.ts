// The one promotion action (ADR-053 §6, §6.1).
//
// FR-017 (promotion moves: the project's copy is consumed), FR-018 (a
// collision prompts and is never resolved
// silently), FR-019 (a non-project origin is refused), FR-021 – FR-024
// (cascade offered, decline warns, second level reported) are properties of
// `promoteToUserLibrary` itself, so they are asserted against it directly with
// a fake io rather than through any one entry point's UI.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TypeSummary, UserLibraryTarget } from "../../../types/api";
import { promotableBlock, promotableType, type PromotableItem } from "../promotable";
import {
  promoteToUserLibrary,
  type CollisionAnswer,
  type PromotionAnswer,
  type PromotionIo,
  type PromotionPlan,
  type PromotionPrompts,
} from "../promoteToUserLibrary";
import { makeBlock, projectType } from "./fixtures";

class Conflict extends Error {}

interface Written {
  target: UserLibraryTarget;
  filename: string;
  content: string;
  overwrite: boolean;
  /** FR-017 — the project file this write was told to consume, or `null`. */
  moveFrom: string | null;
}

function makeIo(options?: {
  sources?: Record<string, { filename: string; content: string; projectPath?: string | null }>;
  catalogue?: readonly TypeSummary[];
  existing?: Set<string>;
  /** Make every removal fail, so the copy-not-move degradation is observable. */
  moveFails?: string;
}) {
  const writes: Written[] = [];
  const existing = options?.existing ?? new Set<string>();
  const sources = options?.sources ?? {};
  const io: PromotionIo = {
    readSource: vi.fn(async (ref) => {
      const key = ref.from === "block" ? `block:${ref.blockType}` : ref.path;
      const found = sources[key] ?? { filename: "fallback.py", content: "# fallback\n" };
      return {
        filename: found.filename,
        content: found.content,
        // FR-017 — the real io derives this from the origin for a block and
        // from the request for a project file; the fake mirrors both shapes.
        projectPath:
          found.projectPath !== undefined
            ? found.projectPath
            : ref.from === "projectFile"
              ? ref.path
              : `blocks/${found.filename}`,
      };
    }),
    readTypeSource: vi.fn(async (type) => {
      const key = `types/${(type.file_path ?? "").split("/").pop()}`;
      return sources[key]?.content ?? "";
    }),
    typeCatalogue: vi.fn(async () => options?.catalogue ?? []),
    write: vi.fn(async (target, filename, content, opts) => {
      const key = `${target}/${filename}`;
      if (existing.has(key) && !opts.overwrite) {
        throw new Conflict(`${filename} already exists in the user library ${target} directory.`);
      }
      const overwritten = existing.has(key);
      existing.add(key);
      const moveFrom = opts.moveFrom ?? null;
      writes.push({ target, filename, content, overwrite: opts.overwrite, moveFrom });
      const kind: "created" | "modified" = overwritten ? "modified" : "created";
      const failed = Boolean(options?.moveFails) && moveFrom !== null;
      return {
        path: `/home/dev/.scistudio/${key}`,
        kind,
        movedFrom: failed ? null : moveFrom,
        moveError: failed ? (options?.moveFails ?? null) : null,
      };
    }),
    isCollision: (error: unknown) => error instanceof Conflict,
  };
  return { io, writes, existing };
}

function makePrompts(overrides?: Partial<PromotionPrompts>): PromotionPrompts {
  return {
    confirm:
      overrides?.confirm ??
      vi.fn(
        async (): Promise<PromotionAnswer> => ({ action: "promote", includeDependencies: true }),
      ),
    resolveCollision:
      overrides?.resolveCollision ??
      vi.fn(async (): Promise<CollisionAnswer> => ({ action: "cancel" })),
  };
}

const projectBlock = makeBlock({
  type_name: "normalize",
  name: "Normalize",
  origin: "project",
});

function blockItem(): PromotableItem {
  return promotableBlock(projectBlock);
}

const BLOCK_SOURCE = { filename: "normalize.py", content: "import numpy as np\n" };

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FR-017 — promotion moves", () => {
  it("names the project file the write must consume", async () => {
    const { io, writes } = makeIo({ sources: { "block:normalize": BLOCK_SOURCE } });
    const outcome = await promoteToUserLibrary(blockItem(), { io, prompts: makePrompts() });

    expect(outcome.status).toBe("promoted");
    expect(writes).toEqual([
      {
        target: "blocks",
        filename: "normalize.py",
        content: BLOCK_SOURCE.content,
        overwrite: false,
        // The removal is the server's, and it happens only as part of this
        // write — there is no separate delete call this action could make.
        moveFrom: "blocks/normalize.py",
      },
    ]);
    expect(io.readSource).toHaveBeenCalledTimes(1);
    expect(outcome.promoted).toMatchObject({
      filename: "normalize.py",
      path: "/home/dev/.scistudio/blocks/normalize.py",
      overwritten: false,
      movedFrom: "blocks/normalize.py",
      moveError: null,
    });
    expect(outcome.warnings).toEqual([]);
  });

  it("moves a data type out of the project too, not only a block", async () => {
    // Owner directive: blocks and types must behave the same. They did not —
    // the two registries resolve a cross-tier name clash in opposite
    // directions, so a copied block appeared to promote and a copied type did
    // not. Moving removes the clash for both.
    const type = projectType("Spectrum", "spectrum");
    const { io, writes } = makeIo({
      sources: { "types/spectrum.py": { filename: "spectrum.py", content: "x = 1\n" } },
    });

    const outcome = await promoteToUserLibrary(promotableType(type)!, {
      io,
      prompts: makePrompts(),
    });

    expect(outcome.status).toBe("promoted");
    expect(writes.map((entry) => entry.moveFrom)).toEqual(["types/spectrum.py"]);
    expect(outcome.promoted?.movedFrom).toBe("types/spectrum.py");
  });

  it("reports a copy rather than claiming a move when the removal fails", async () => {
    // The library copy is on disk, so the promotion succeeded — but the
    // project still holds a file with the same class name in it, and which one
    // the process loads is then decided by a registry policy the user cannot
    // see. Saying nothing would leave them in exactly the confusion FR-017
    // exists to end.
    const { io } = makeIo({
      sources: { "block:normalize": BLOCK_SOURCE },
      moveFails: "permission denied",
    });
    const outcome = await promoteToUserLibrary(blockItem(), { io, prompts: makePrompts() });

    expect(outcome.status).toBe("promoted");
    expect(outcome.promoted).toMatchObject({ movedFrom: null, moveError: "permission denied" });
    expect(outcome.warnings.join(" ")).toContain("could not be removed");
    expect(outcome.warnings.join(" ")).toContain("Both copies now exist");
  });
});

describe("FR-019 — a non-project origin is refused outright", () => {
  it("refuses a built-in block even when called directly", async () => {
    const { io, writes } = makeIo();
    const builtin = promotableBlock(
      makeBlock({ type_name: "load", name: "Load", origin: "builtin" }),
    );
    const outcome = await promoteToUserLibrary(builtin, { io, prompts: makePrompts() });
    expect(outcome.status).toBe("failed");
    expect(writes).toEqual([]);
  });
});

describe("FR-018 — a collision prompts, and never overwrites silently", () => {
  it("writes with overwrite:false first, so an existing file is reported not replaced", async () => {
    const { io } = makeIo({
      sources: { "block:normalize": BLOCK_SOURCE },
      existing: new Set(["blocks/normalize.py"]),
    });
    const resolveCollision = vi.fn<PromotionPrompts["resolveCollision"]>(async () => ({
      action: "cancel",
    }));
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({ resolveCollision }),
    });

    expect(resolveCollision).toHaveBeenCalledTimes(1);
    expect(resolveCollision.mock.calls[0][0]).toMatchObject({
      target: "blocks",
      filename: "normalize.py",
    });
    // The detail comes from the server's 409, not from a client-side guess.
    expect(resolveCollision.mock.calls[0][0].detail).toContain("already exists");
    expect(outcome.status).toBe("cancelled");
    expect(outcome.promoted).toBeNull();
  });

  it("overwrites only after the user chooses Overwrite", async () => {
    const { io, writes } = makeIo({
      sources: { "block:normalize": BLOCK_SOURCE },
      existing: new Set(["blocks/normalize.py"]),
    });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        resolveCollision: vi.fn(async (): Promise<CollisionAnswer> => ({ action: "overwrite" })),
      }),
    });

    // Two attempts: the first refuses (overwrite:false) and is what produced
    // the prompt; only the second carries the user's explicit opt-in.
    expect(vi.mocked(io.write).mock.calls.map((call) => call[3].overwrite)).toEqual([false, true]);
    expect(writes.map((entry) => entry.overwrite)).toEqual([true]);
    expect(outcome.status).toBe("promoted");
    expect(outcome.promoted?.overwritten).toBe(true);
  });

  it("retries a renamed file with overwrite back at false", async () => {
    const { io, writes } = makeIo({
      sources: { "block:normalize": BLOCK_SOURCE },
      existing: new Set(["blocks/normalize.py"]),
    });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        resolveCollision: vi.fn(
          async (): Promise<CollisionAnswer> => ({ action: "rename", filename: "normalize_v2" }),
        ),
      }),
    });

    expect(writes).toEqual([
      {
        target: "blocks",
        filename: "normalize_v2.py",
        content: BLOCK_SOURCE.content,
        overwrite: false,
        // Renaming changes where the copy lands, not which file it consumes:
        // the original is still `blocks/normalize.py` and still has to go.
        moveFrom: "blocks/normalize.py",
      },
    ]);
    expect(outcome.promoted?.filename).toBe("normalize_v2.py");
  });
});

describe("FR-021 – FR-024 — cascade", () => {
  const spectrum = projectType("Spectrum", "spectrum");
  const trace = projectType("Trace", "trace");
  const catalogue: TypeSummary[] = [spectrum, trace];
  const sources = {
    "block:normalize": { filename: "normalize.py", content: "from spectrum import Spectrum\n" },
    "types/spectrum.py": { filename: "spectrum.py", content: "from trace import Trace\n" },
  };

  it("offers the project-level type dependencies and promotes them as one action", async () => {
    const { io, writes } = makeIo({ sources, catalogue });
    let seen: PromotionPlan | null = null;
    const confirm = vi.fn(async (plan: PromotionPlan): Promise<PromotionAnswer> => {
      seen = plan;
      return { action: "promote", includeDependencies: true };
    });

    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({ confirm }),
    });

    expect(seen!.cascade.dependencies.map((entry) => entry.type.name)).toEqual(["Spectrum"]);
    // Dependencies land before the block, so a failure never leaves a block
    // in the library whose types are missing.
    expect(writes.map((entry) => `${entry.target}/${entry.filename}`)).toEqual([
      "types/spectrum.py",
      "blocks/normalize.py",
    ]);
    expect(outcome.promotedDependencies.map((entry) => entry.label)).toEqual(["Spectrum"]);
  });

  it("still promotes the block when the cascade is declined, and warns explicitly", async () => {
    const { io, writes } = makeIo({ sources, catalogue });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        confirm: vi.fn(
          async (): Promise<PromotionAnswer> => ({ action: "promote", includeDependencies: false }),
        ),
      }),
    });

    expect(outcome.status).toBe("promoted");
    expect(writes.map((entry) => entry.target)).toEqual(["blocks"]);
    expect(outcome.declinedDependencies).toEqual(["Spectrum"]);
    expect(outcome.warnings.join(" ")).toContain("fail to load in other projects");
  });

  it("reports a second-level dependency rather than silently missing it", async () => {
    const { io } = makeIo({ sources, catalogue });
    const outcome = await promoteToUserLibrary(blockItem(), { io, prompts: makePrompts() });

    expect(outcome.secondLevel).toEqual([{ name: "Trace", via: "Spectrum" }]);
    expect(outcome.warnings.join(" ")).toContain("Trace");
    expect(outcome.warnings.join(" ")).toContain("one level deep");
  });

  it("does not run a cascade for a type — that is the second level (FR-024)", async () => {
    const { io } = makeIo({
      sources: {
        "types/spectrum.py": { filename: "spectrum.py", content: "from trace import Trace\n" },
      },
      catalogue,
    });
    const outcome = await promoteToUserLibrary(promotableType(spectrum)!, {
      io,
      prompts: makePrompts(),
    });
    expect(outcome.status).toBe("promoted");
    expect(outcome.promotedDependencies).toEqual([]);
    expect(io.readTypeSource).not.toHaveBeenCalled();
  });

  it("cancels the whole action when a dependency's collision prompt is cancelled", async () => {
    const { io, writes } = makeIo({
      sources,
      catalogue,
      existing: new Set(["types/spectrum.py"]),
    });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        resolveCollision: vi.fn(async (): Promise<CollisionAnswer> => ({ action: "cancel" })),
      }),
    });

    expect(outcome.status).toBe("cancelled");
    // The block never landed — a half-cascade is not a promotion.
    expect(writes).toEqual([]);
  });

  // Reported by an external review of PR #2036: a cancel after the cascade has
  // written is not a cancellation of anything the user can see. `runPromotion`
  // shows no notice for `cancelled`, so the UI looked like nothing had
  // happened while files had in fact been added to My Library.
  it("reports a partial result when the item is cancelled after a dependency landed", async () => {
    const { io, writes } = makeIo({
      sources,
      catalogue,
      existing: new Set(["blocks/normalize.py"]),
    });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        resolveCollision: vi.fn(async (): Promise<CollisionAnswer> => ({ action: "cancel" })),
      }),
    });

    expect(writes.map((entry) => `${entry.target}/${entry.filename}`)).toEqual([
      "types/spectrum.py",
    ]);
    expect(outcome.status).toBe("partial");
    expect(outcome.promoted).toBeNull();
    expect(outcome.promotedDependencies.map((entry) => entry.label)).toEqual(["Spectrum"]);
    expect(outcome.warnings.join(" ")).toContain("Spectrum");
    expect(outcome.warnings.join(" ")).toContain("still there");
  });

  it("reports a partial result when a later dependency's prompt is cancelled", async () => {
    const { io, writes } = makeIo({
      sources: {
        "block:normalize": {
          filename: "normalize.py",
          content: "from spectrum import Spectrum\nfrom trace import Trace\n",
        },
        "types/spectrum.py": { filename: "spectrum.py", content: "" },
        "types/trace.py": { filename: "trace.py", content: "" },
      },
      catalogue,
      existing: new Set(["types/trace.py"]),
    });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        resolveCollision: vi.fn(async (): Promise<CollisionAnswer> => ({ action: "cancel" })),
      }),
    });

    expect(writes.map((entry) => `${entry.target}/${entry.filename}`)).toEqual([
      "types/spectrum.py",
    ]);
    expect(outcome.status).toBe("partial");
    expect(outcome.promotedDependencies.map((entry) => entry.label)).toEqual(["Spectrum"]);
  });
});

describe("cancellation and failure", () => {
  it("writes nothing when the confirmation is cancelled", async () => {
    const { io, writes } = makeIo({ sources: { "block:normalize": BLOCK_SOURCE } });
    const outcome = await promoteToUserLibrary(blockItem(), {
      io,
      prompts: makePrompts({
        confirm: vi.fn(async (): Promise<PromotionAnswer> => ({ action: "cancel" })),
      }),
    });
    expect(outcome.status).toBe("cancelled");
    expect(writes).toEqual([]);
  });

  it("reports a read failure instead of throwing", async () => {
    const { io } = makeIo();
    io.readSource = vi.fn(async () => {
      throw new Error("source unavailable");
    });
    const outcome = await promoteToUserLibrary(blockItem(), { io, prompts: makePrompts() });
    expect(outcome.status).toBe("failed");
    expect(outcome.error).toContain("source unavailable");
  });
});
