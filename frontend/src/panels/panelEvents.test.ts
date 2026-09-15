/**
 * #2465 — which open previews a panel-service signal re-routes.
 *
 * Only previews whose data type (type chain and collection-ness) the changed
 * claims or the changed choice concern re-route; legacy-rendered previews
 * re-route when the legacy previewers were reloaded.
 */
import { describe, expect, it } from "vitest";

import type { PreviewEnvelope } from "../types/api";

import {
  notifyPanelContextsRevoked,
  notifyPanelFilesChanged,
  previewIsAffected,
  requestPreviewReroute,
  subscribePanelContextRevoked,
  subscribePanelFilesChanged,
  subscribePreviewReroute,
} from "./panelEvents";

function envelope(
  partial: Partial<PreviewEnvelope> & { target: PreviewEnvelope["target"] },
): PreviewEnvelope {
  return {
    session_id: "pv-1",
    previewer_id: "lab.view",
    kind: "panel",
    payload: {},
    resources: [],
    metadata: {
      sampled: false,
      truncated: false,
      cached: false,
      derived: false,
      complete: true,
      failed: false,
    },
    diagnostics: [],
    error: null,
    ...partial,
  } as PreviewEnvelope;
}

const IMAGE = envelope({
  target: {
    kind: "data_ref",
    ref: "d",
    recorded_type: "Image",
    type_chain: ["DataObject", "Array", "Image"],
  },
});
const IMAGES = envelope({
  target: {
    kind: "collection_ref",
    ref: "c",
    collection_item_type: "Image",
    type_chain: ["DataObject", "Array", "Image"],
  },
});
const TABLE = envelope({
  kind: "dataframe",
  previewer_id: "pkg.table",
  target: {
    kind: "data_ref",
    ref: "t",
    recorded_type: "DataFrame",
    type_chain: ["DataObject", "DataFrame"],
  },
});

describe("previewIsAffected", () => {
  it("matches an item claim anywhere in the type chain, never a collection", () => {
    expect(previewIsAffected(IMAGE, { types: ["Array"] })).toBe(true);
    expect(previewIsAffected(IMAGE, { types: ["Image"] })).toBe(true);
    expect(previewIsAffected(IMAGES, { types: ["Image"] })).toBe(false);
    expect(previewIsAffected(TABLE, { types: ["Image"] })).toBe(false);
  });

  it("matches a collection claim only for collections of that item chain", () => {
    expect(previewIsAffected(IMAGES, { types: ["Collection[Array]"] })).toBe(true);
    expect(previewIsAffected(IMAGE, { types: ["Collection[Image]"] })).toBe(false);
    expect(previewIsAffected(IMAGES, { types: ["Collection"] })).toBe(true);
    expect(previewIsAffected(IMAGES, { types: ["DataObject"] })).toBe(false);
    expect(previewIsAffected(TABLE, { types: ["DataObject"] })).toBe(true);
  });

  it("matches a choice on the most specific type only", () => {
    expect(previewIsAffected(IMAGE, { choiceType: "Image" })).toBe(true);
    expect(previewIsAffected(IMAGE, { choiceType: "Array" })).toBe(false);
    expect(previewIsAffected(IMAGES, { choiceType: "Image" })).toBe(true);
  });

  it("re-routes only legacy-rendered previews on a legacy reload", () => {
    expect(previewIsAffected(TABLE, { legacy: true })).toBe(true);
    expect(previewIsAffected(IMAGE, { legacy: true })).toBe(false);
  });
});

describe("the channels reach only the mounts they name", () => {
  it("files_changed and contexts_revoked", () => {
    const heard: string[] = [];
    const stops = [
      subscribePanelFilesChanged("lab.a", () => heard.push("files:a")),
      subscribePanelFilesChanged("lab.b", () => heard.push("files:b")),
      subscribePanelContextRevoked("pc-1", () => heard.push("revoked:1")),
      subscribePanelContextRevoked("pc-2", () => heard.push("revoked:2")),
    ];
    notifyPanelFilesChanged("lab.a");
    notifyPanelContextsRevoked(["pc-2"]);
    notifyPanelContextsRevoked([]);
    expect(heard).toEqual(["files:a", "revoked:2"]);
    stops.forEach((stop) => stop());
  });

  it("an empty re-route request reaches nobody", () => {
    const heard: unknown[] = [];
    const stop = subscribePreviewReroute((signal) => heard.push(signal));
    requestPreviewReroute({ types: [] });
    requestPreviewReroute({ types: ["Image"] });
    expect(heard).toEqual([{ types: ["Image"] }]);
    stop();
  });
});
