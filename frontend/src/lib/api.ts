/**
 * Public `api` surface for the SciStudio frontend.
 *
 * STRUCTURE (post-#1422 split + post-#1410 main-merge)
 * ----------------------------------------------------
 *
 * The pre-split monolithic `api.ts` ran ~633 LOC and grew with every
 * backend route. After #1422 the file became an assembly shell only:
 * every domain lives in `./api/<domain>.ts` and is spread into the
 * single `api` object below. Behavior is unchanged — the keys,
 * argument shapes, and return types match the pre-split surface
 * exactly so no downstream file required an import update.
 *
 *   - `api/core.ts`       — `ApiError`, `apiFetch`, `JSON_HEADERS`
 *   - `api/version.ts`    — ADR-045 version-vector types + source-id
 *                           helpers (#1410)
 *   - `api/projects.ts`   — `/api/projects/*`
 *   - `api/blocks.ts`     — `/api/blocks/*`
 *   - `api/workflows.ts`  — `/api/workflows/*` (incl. execute / cancel
 *                           / export); ADR-045 X-Source-Id headers
 *   - `api/data.ts`       — `/api/data/*`
 *   - `api/filesystem.ts` — `/api/filesystem/*` + native-dialog
 *   - `api/code.ts`       — ADR-036 file R/W + lint + block-template;
 *                           ADR-045 source-id body fields
 *   - `api/lineage.ts`    — ADR-038 §3.8 lineage namespace + adapters
 *   - `api/git.ts`        — ADR-039 §3.5 git versioning surface
 *
 * Re-exports below keep the public surface backwards-compatible:
 * `import { ApiError, createClientSourceId } from "../lib/api"`,
 * `import type { VersionedWorkflowResponse } from "../lib/api"`, etc.
 */

import { blocksApi } from "./api/blocks";
import { codeApi } from "./api/code";
import { dataApi } from "./api/data";
import { filesystemApi } from "./api/filesystem";
import { gitApi } from "./api/git";
import { lineageApi } from "./api/lineage";
import { packagesApi } from "./api/packages";
import { projectsApi } from "./api/projects";
import { tutorialsApi } from "./api/tutorials";
import { workflowsApi } from "./api/workflows";

export { ApiError } from "./api/core";
export {
  consumePendingWorkflowSourceId,
  createClientSourceId,
  setWorkflowWriteStartedListener,
} from "./api/version";
export type {
  ProjectFileResponse,
  ProjectFileWriteResponse,
  VersionedWorkflowResponse,
  VersionedWriteOptions,
} from "./api/version";

export const api = {
  ...projectsApi,
  ...blocksApi,
  ...workflowsApi,
  ...dataApi,
  ...filesystemApi,
  ...codeApi,
  ...lineageApi,
  ...packagesApi,
  ...gitApi,
  ...tutorialsApi,
};
