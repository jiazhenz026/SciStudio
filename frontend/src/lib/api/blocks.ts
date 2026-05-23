/**
 * Block schema + validation endpoints.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type {
  BlockListResponse,
  BlockSchemaResponse,
  ConnectionValidationResponse,
} from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const blocksApi = {
  listBlocks: () => apiFetch<BlockListResponse>("/api/blocks/"),
  getBlockSchema: (blockType: string) =>
    apiFetch<BlockSchemaResponse>(`/api/blocks/${encodeURIComponent(blockType)}/schema`),
  // #889: ``source_node_config`` / ``target_node_config`` let the
  // backend resolve effective ports for LoadData (``core_type``
  // chooses the output type) and variadic blocks (config-declared
  // ports). They are optional so older callers keep working.
  validateConnection: (body: {
    source_block: string;
    source_port: string;
    target_block: string;
    target_port: string;
    source_node_config?: Record<string, unknown>;
    target_node_config?: Record<string, unknown>;
  }) =>
    apiFetch<ConnectionValidationResponse>("/api/blocks/validate-connection", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
};
