/**
 * Trivial fixture previewer ESM module.
 *
 * Mirrors the packaged-previewer host-module contract (apiVersion + mount)
 * with zero real rendering behaviour. Exists only so core's previewer asset
 * serving / manifest tests have a same-origin module to import that exposes
 * a `mount` export.
 */
export default {
  apiVersion: "1",
  mount(container, host) {
    container.textContent = "fixture previewer";
    return {
      update(_envelope) {},
      unmount() {},
    };
  },
};
