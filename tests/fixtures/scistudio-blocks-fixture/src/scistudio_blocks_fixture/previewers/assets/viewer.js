/**
 * Trivial fixture panel ESM module.
 *
 * Mirrors the packaged-panel host-module contract (apiVersion + mount)
 * with zero real rendering behaviour. Exists only so core's panel asset
 * serving / manifest tests have a same-origin module to import that exposes
 * a `mount` export.
 */
export default {
  apiVersion: "1",
  mount(container, host) {
    container.textContent = "fixture panel";
    return {
      update(_envelope) {},
      unmount() {},
    };
  },
};
