/** Load the shipping SDK modules without a backend or a privileged frame host. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SDK = resolve(process.cwd(), "../src/scistudio/panels/sdk/1");
export const dataUrl = (source: string) =>
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;

export function rewriteRendererImports(source: string, preactUrl: string, uiUrl: string): string {
  return source
    .replace(/"[^"\n]*preact-standalone\.module\.js"/g, JSON.stringify(preactUrl))
    .replace(/"[^"\n]*panel-ui\.js"/g, JSON.stringify(uiUrl))
    .replace(/"[^"\n]*(renderer-[a-z]+\.js)"/g, (_match, name: string) =>
      JSON.stringify(
        dataUrl(rewriteRendererImports(readFileSync(resolve(SDK, name), "utf8"), preactUrl, uiUrl)),
      ),
    );
}

export async function loadRenderers() {
  const preactUrl = dataUrl(
    readFileSync(
      resolve(SDK, "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js"),
      "utf8",
    ),
  );
  const uiUrl = dataUrl(
    rewriteRendererImports(readFileSync(resolve(SDK, "panel-ui.js"), "utf8"), preactUrl, ""),
  );
  const renderers = await import(
    /* @vite-ignore */ dataUrl(
      rewriteRendererImports(readFileSync(resolve(SDK, "renderers.js"), "utf8"), preactUrl, uiUrl),
    )
  );
  const preact = await import(/* @vite-ignore */ preactUrl);
  return { ...preact, ...renderers };
}
