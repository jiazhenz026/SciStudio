/**
 * Public `api` surface for the SciStudio frontend.
 *
 * STRUCTURE (post-#1422 split)
 * ----------------------------
 *
 * The pre-split monolithic `api.ts` ran ~633 LOC and grew with every
 * backend route. After #1422 the file is an assembly shell only: every
 * domain lives in `./api/<domain>.ts` and is spread into the single
 * `api` object below. Behavior is unchanged — the keys, argument
 * shapes, and return types match the pre-split surface exactly so no
 * downstream file required an import update.
 *
 *   - `api/core.ts`       — `ApiError`, `apiFetch`, `JSON_HEADERS`
 *   - `api/projects.ts`   — `/api/projects/*`
 *   - `api/blocks.ts`     — `/api/blocks/*`
 *   - `api/workflows.ts`  — `/api/workflows/*` (incl. execute / cancel / export)
 *   - `api/data.ts`       — `/api/data/*`
 *   - `api/filesystem.ts` — `/api/filesystem/*` + native-dialog
 *   - `api/code.ts`       — ADR-036 file R/W + lint + block-template
 *   - `api/lineage.ts`    — ADR-038 §3.8 lineage namespace + adapters
 *   - `api/git.ts`        — ADR-039 §3.5 git versioning surface
 *
 * `ApiError` is re-exported below so `import { ApiError } from
 * "../lib/api"` continues to resolve.
 */

import { blocksApi } from "./api/blocks";
import { codeApi } from "./api/code";
import { dataApi } from "./api/data";
import { filesystemApi } from "./api/filesystem";
import { gitApi } from "./api/git";
import { lineageApi } from "./api/lineage";
import { projectsApi } from "./api/projects";
import { workflowsApi } from "./api/workflows";

export { ApiError } from "./api/core";

export const api = {
  ...projectsApi,
  ...blocksApi,
  ...workflowsApi,
  ...dataApi,
  ...filesystemApi,
  ...codeApi,
  ...lineageApi,
  ...gitApi,
};
