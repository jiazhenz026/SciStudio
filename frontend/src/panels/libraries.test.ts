import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const libraryRoot = resolve(process.cwd(), "../src/scistudio/panels/lib");
interface LibraryEntry {
  name: string;
  version: string;
  license: string;
  files: string[];
  sha256: Record<string, string>;
}
const index = JSON.parse(readFileSync(resolve(libraryRoot, "index.json"), "utf8")) as {
  libraries: LibraryEntry[];
};
describe("packaged panel libraries", () => {
  it("ships every indexed file with its recorded shipped digest and license", () => {
    expect(index.libraries.map((entry) => entry.name).sort()).toEqual([
      "d3",
      "lucide",
      "pdfjs",
      "plotly",
      "preact-htm",
      "three",
    ]);
    for (const entry of index.libraries) {
      expect(entry.license).toBeTruthy();
      expect(entry.files).toContain("LICENSE");
      for (const file of entry.files) {
        const bytes = readFileSync(resolve(libraryRoot, `${entry.name}@${entry.version}`, file));
        expect(createHash("sha256").update(bytes).digest("hex"), `${entry.name}/${file}`).toBe(
          entry.sha256[file],
        );
      }
    }
  });
  it("pins Plotly to the frontend lock and includes dependent renderer bundles", () => {
    const lock = JSON.parse(readFileSync(resolve(process.cwd(), "package-lock.json"), "utf8"));
    expect(index.libraries.find((entry) => entry.name === "plotly")?.version).toBe(
      lock.packages["node_modules/plotly.js"].version,
    );
    expect(index.libraries.find((entry) => entry.name === "three")?.files).toContain(
      "build/three.core.min.js",
    );
    expect(index.libraries.find((entry) => entry.name === "pdfjs")?.files).toContain(
      "build/pdf.worker.min.mjs",
    );
  });
});
