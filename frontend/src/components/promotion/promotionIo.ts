// The real `PromotionIo` — every network call the promotion action makes.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §4 (the user library write
// path), §6 FR-017/FR-018, §6.1 FR-022.
//
// Split from `promoteToUserLibrary.ts` so the action stays transport-free and
// its FR-017 / FR-018 / FR-021 – FR-024 behaviour is unit-testable against a
// fake. It is also the one place that knows a 409 is the collision signal
// (FR-008): the action asks `isCollision`, never a status code.

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
    isCollision: (error: unknown) => error instanceof ApiError && error.status === 409,
  };
}
