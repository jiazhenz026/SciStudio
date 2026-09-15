// The real `PromotionIo` — every network call the promotion action makes.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §4 (the user library write
// path), §6 FR-017/FR-018, §6.1 FR-022.
//
// Split from `promoteToUserLibrary.ts` so the action stays transport-free and
// its FR-017 / FR-018 / FR-021 – FR-024 behaviour is unit-testable against a
// fake. It is also the one place that knows a 409 is the collision signal
// (FR-008): the action asks `isCollision`, never a status code.

import { miniAppsApi } from "../../miniapps/api";
import { ApiError, api } from "../../lib/api";
import { useAppStore } from "../../store";
import { invalidateTypeCatalog, loadTypeCatalog } from "../../store/useTypeCatalog";
import type { TypeSummary, UserLibraryTarget } from "../../types/api";

import type { PromotionIo, PromotionSource } from "./promoteToUserLibrary";
import type { PromotionSourceRef } from "./promotable";

function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/**
 * Build the io bound to the open project.
 *
 * `projectId` is `null` only when no project is open, in which case nothing
 * project-relative can be read; the promotion entry points are all inside a
 * project surface, so this is a guard rather than a supported state.
 */
export function createPromotionIo(projectId: string | null): PromotionIo {
  const readProjectFile = async (path: string): Promise<PromotionSource> => {
    if (!projectId) {
      throw new Error("Open a project before promoting to your library.");
    }
    const response = await api.getProjectFile(projectId, path);
    return { filename: basename(path), content: response.content, projectPath: path };
  };

  return {
    readSource: async (ref: PromotionSourceRef): Promise<PromotionSource> => {
      if (ref.from === "block") {
        // The block source endpoint resolves the file wherever it lives, which
        // is what lets a "View source" tab promote without the caller knowing
        // the path.
        const response = await api.getBlockSource(ref.blockType);
        // FR-017 needs a project-*relative* path to remove, and this endpoint
        // answers with an absolute one. Promotion is offered only for a
        // resolved origin of `project` (FR-019), and a project-tier block sits
        // directly in `{project}/blocks/` by construction
        // (`scistudio.core.dropins.project_blocks_dir`), so the basename is the
        // whole of the difference. The server re-resolves and sandboxes it
        // anyway; nothing here is trusted.
        const file = basename(response.path);
        return {
          filename: file,
          content: response.source,
          projectPath: response.origin === "project" ? `blocks/${file}` : null,
        };
      }
      if (ref.from === "panelDirectory") {
        // ADR-054 FR-039 — a MiniApp has no single file to read. The promotion
        // is one server-side move of the whole directory, so there is nothing
        // to carry through the caller: this answers with the directory's own
        // name and the project-relative path FR-017's removal consumes, and
        // `writeDirectory` below does the work `write` does for a file.
        return {
          filename: ref.panelId,
          content: "",
          projectPath: `panels/${ref.panelId}`,
        };
      }
      return readProjectFile(ref.path);
    },
    readTypeSource: async (type: TypeSummary): Promise<string> => {
      const file = basename(type.file_path ?? "");
      if (!file.toLowerCase().endsWith(".py")) {
        throw new Error(`"${type.name}" has no readable source file.`);
      }
      const response = await readProjectFile(`types/${file}`);
      return response.content;
    },
    typeCatalogue: async (): Promise<readonly TypeSummary[]> => {
      // FR-022 classifies each resolved type by origin "using the shared
      // resolver". `TypeSummary.origin` *is* that resolver's answer, computed
      // backend-side and transported; re-deriving it here would create the
      // second supply point the spec removes.
      await loadTypeCatalog();
      return useAppStore.getState().types;
    },
    write: async (
      target: UserLibraryTarget,
      filename: string,
      content: string,
      options: { overwrite: boolean; moveFrom?: string | null },
    ) => {
      const response = await api.putUserLibraryFile(target, filename, content, {
        overwrite: options.overwrite,
        // FR-017 — no project, nothing to move out of it. The server only ever
        // removes a path it can resolve inside the project root it was given.
        moveFrom: projectId && options.moveFrom ? { projectId, path: options.moveFrom } : null,
      });
      // The write rebuilt every backend registry (FR-010/FR-062), so the
      // cached type catalogue is stale from here on — including when a cascade
      // wrote a type and the promotion is later abandoned, which reveals
      // nothing and would otherwise leave the new type invisible until a
      // manual reload.
      invalidateTypeCatalog();
      return {
        path: response.path,
        kind: response.kind,
        movedFrom: response.moved_from,
        moveError: response.move_error,
      };
    },
    // FR-008: the endpoint reports an existing file as a 409 rather than
    // overwriting it, so the FR-018 prompt is driven by the server's answer
    // and not by a client-side guess that could race another writer.
    writeDirectory: async (panelId: string, options: { overwrite: boolean }) => {
      const result = await miniAppsApi.promote(panelId, { overwrite: options.overwrite });
      return {
        path: result.path,
        kind: options.overwrite ? ("modified" as const) : ("created" as const),
        // FR-017 — `moved` false means the library copy landed and the project
        // copy could not be removed, so the promotion degraded to a copy. The
        // route reports the fact; it does not report a reason, so the message
        // here is the whole of what is known.
        movedFrom: result.moved ? `panels/${panelId}` : null,
        moveError: result.moved
          ? null
          : "The library copy was written, but the project copy could not be removed.",
      };
    },
    isCollision: (error: unknown) => error instanceof ApiError && error.status === 409,
  };
}
