/* SDK 1: composable core preview presentation components. See miniapp-renderers.md. */
/**
 * @overview
 * The data views SciStudio's own previews are built from, importable by any
 * panel. Load `panel.css` and `renderers.css`, and use the vendored Preact at
 * `../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js`; a second
 * Preact instance breaks hooks.
 *
 * ```javascript
 * import { html, render } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
 * import { ArrayView, TextView } from "../../sdk/1/renderers.js";
 * ```
 *
 * The views take values, controlled state, and callbacks. They never call
 * `window.scistudio`: the panel reads the data, keeps the state, and decides
 * what saving or opening does. Importing a module mounts nothing, and several
 * instances can share a page. Every view accepts `error`, which takes
 * precedence over data, and shows its loading state while its main data prop
 * is absent. Pass new objects when values change; inputs are not mutated.
 *
 * Each view also lives in its own `renderer-*.js` module. Other named exports
 * of those modules are helpers, not part of this contract.
 */
export { ArrayView } from "./renderer-array.js";
export { DataFrameView } from "./renderer-dataframe.js";
export { SeriesView } from "./renderer-series.js";
export { TextView } from "./renderer-text.js";
export { ArtifactView } from "./renderer-artifact.js";
export { MetadataView } from "./renderer-base.js";
export { CollectionView } from "./renderer-collection.js";
export { CompositeView } from "./renderer-composite.js";
export { PlotView } from "./renderer-plot.js";
