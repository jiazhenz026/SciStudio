import { useState } from "react";
import { createRoot } from "react-dom/client";
import type { PanelSnapshot } from "../../src/panels/types";
import { PanelFrame } from "../../src/panels/PanelFrame";
import { PreviewHost } from "../../src/components/DataPreview.parts/PreviewHost";

function BrowserHost() {
  const [mounted, setMounted] = useState(true);
  const [snapshot, setSnapshot] = useState<PanelSnapshot | null>(null);
  const [maximized, setMaximized] = useState<PanelSnapshot | null>(null);
  const query = new URLSearchParams(location.search);
  const panelId = `browser.${query.get("panel") ?? "reader"}`;
  const target = { kind: "data_ref" as const, ref: query.get("target") ?? "data-a" };
  return (
    <main>
      <button onClick={() => setMounted(false)}>Unmount</button>
      <button
        onClick={() => {
          setMaximized(snapshot);
          setMounted(false);
        }}
      >
        Maximize child
      </button>
      {maximized && (
        <section aria-label="Maximized preview">
          <PreviewHost
            target={maximized.target}
            panelId={maximized.panelId}
            previewSessionId={maximized.previewSessionId}
            initialViewState={maximized.viewState}
          />
        </section>
      )}
      {mounted &&
        (query.get("host") === "preview" ? (
          <PreviewHost target={target} panelId={panelId} onPanelSnapshot={setSnapshot} />
        ) : (
          <PanelFrame request={{ kind: "preview", target, panel_id: panelId }} />
        ))}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<BrowserHost />);
