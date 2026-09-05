/**
 * Trivial fixture panel ESM module.
 *
 * Mirrors the packaged-panel host-module contract (apiVersion + mount)
 * with zero real rendering behaviour. Exists only so core's panel asset
 * serving / manifest tests have a same-origin module to import that exposes
 * a `mount` export.
 *
 * It imports a sibling on purpose (ADR-054 spec 1 FR-042): an ADR-048 bundle is
 * a directory, not a file, and the compatibility shim has to carry the whole of
 * it across for a mount like this one to survive.
 */
import { LABEL } from "./viewer_label.js";

export default {
  apiVersion: "1",
  mount(container, host) {
    container.textContent = LABEL;
    return {
      update(_envelope) {},
      unmount() {},
    };
  },
};
