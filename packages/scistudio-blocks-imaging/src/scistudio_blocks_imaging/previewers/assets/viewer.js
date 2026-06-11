/**
 * ADR-048 SPEC 1 — packaged Image/Label previewer ESM module.
 *
 * Self-contained, dependency-free, vanilla ES module (NO npm build step, NO
 * React). It implements the host-module contract defined in
 * `frontend/src/components/DataPreview.parts/previewerHostApi.ts`:
 *
 *   export default {
 *     apiVersion: "1",
 *     mount(container: HTMLElement, host: PreviewHostApi): {
 *       update?(envelope), unmount()
 *     }
 *   }
 *
 * The frontend PreviewHost validates the manifest, same-origin `import()`s
 * this module, reads the named export (`default`), checks `apiVersion`, then
 * calls `mount(container, host)`. The module reads all data through the
 * constrained `host` API only:
 *   - `host.envelope.payload`        — shape/axes/slice/src + image_metadata
 *   - `host.kind`                    — "array" (Image) / "composite" (Label)
 *   - `host.session.patchQuery(q)`   — drive the slice slider (server re-render)
 *   - `host.session.getResource(id)` — bounded tile/export reads
 *   - `host.exportArtifact(req)`     — user-initiated PNG export
 *   - `host.reportError(msg)`        — non-fatal error channel
 *
 * It causes NO workflow/runtime/lineage mutation (FR-023). All rendering is
 * canvas/DOM based; LUT + display-range recolouring runs entirely client-side
 * on the PNG data-URI the backend supplies, exactly mirroring the legacy
 * `ImageViewer.tsx` / `luts.ts` behaviour.
 */

const API_VERSION = "1";

/* ---------------------------------------------------------------------------
 * LUT colormaps — ported verbatim from luts.ts (9 colormaps).
 * Each LUT is a 256-entry [r, g, b] table.
 * ------------------------------------------------------------------------- */

function clamp255(v) {
  return Math.max(0, Math.min(255, Math.round(v)));
}

function buildLUT(fn) {
  const lut = new Array(256);
  for (let i = 0; i < 256; i += 1) {
    const [r, g, b] = fn(i);
    lut[i] = [clamp255(r), clamp255(g), clamp255(b)];
  }
  return lut;
}

const LUTS = {
  gray: buildLUT((t) => [t, t, t]),
  fire: buildLUT((t) => [Math.min(255, t * 3), Math.max(0, (t - 85) * 3), Math.max(0, (t - 170) * 3)]),
  ice: buildLUT((t) => [Math.max(0, (t - 170) * 3), Math.max(0, (t - 85) * 3), Math.min(255, t * 3)]),
  green: buildLUT((t) => [0, t, 0]),
  red: buildLUT((t) => [t, 0, 0]),
  blue: buildLUT((t) => [0, 0, t]),
  cyan: buildLUT((t) => [0, t, t]),
  magenta: buildLUT((t) => [t, 0, t]),
  viridis: buildLUT((t) => {
    const r = Math.round(68 + (253 - 68) * Math.sin((t / 256) * Math.PI * 0.8));
    const g = Math.round(1 + (231 - 1) * (t / 255));
    const b = Math.round(84 + (37 - 84) * (t / 255));
    return [Math.min(255, r), Math.min(255, g), Math.max(0, b)];
  }),
};

function lutGradient(lut) {
  return [0, 64, 128, 192, 255]
    .map((i) => {
      const [r, g, b] = lut[i];
      return `rgb(${r},${g},${b})`;
    })
    .join(", ");
}

/**
 * Re-colour a PNG data-URL through a LUT + display [min, max] range, returning
 * a new PNG data-URL. Mirrors `applyLUTToImage` in luts.ts. Resolves with the
 * original URL on any decode failure so the viewer never blanks out.
 */
function applyLUTToImage(dataUrl, lut, minVal, maxVal) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve(dataUrl);
          return;
        }
        ctx.drawImage(img, 0, 0);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const pixels = imageData.data;
        const range = maxVal - minVal || 1;
        for (let i = 0; i < pixels.length; i += 4) {
          const gray = pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114;
          const normalized = Math.max(0, Math.min(255, ((gray - minVal) / range) * 255));
          const idx = Math.round(normalized);
          const [r, g, b] = lut[idx] || [idx, idx, idx];
          pixels[i] = r;
          pixels[i + 1] = g;
          pixels[i + 2] = b;
        }
        ctx.putImageData(imageData, 0, 0);
        resolve(canvas.toDataURL("image/png"));
      } catch (err) {
        resolve(dataUrl);
      }
    };
    img.onerror = () => resolve(dataUrl);
    img.src = dataUrl;
  });
}

/* ---------------------------------------------------------------------------
 * Small DOM helpers (no framework).
 * ------------------------------------------------------------------------- */

function el(tag, style, props) {
  const node = document.createElement(tag);
  if (style) Object.assign(node.style, style);
  if (props) Object.assign(node, props);
  return node;
}

function payloadOf(envelope) {
  if (!envelope || typeof envelope !== "object") return {};
  const p = envelope.payload;
  return p && typeof p === "object" ? p : {};
}

/**
 * The Image payload lives directly on the envelope; the Label payload nests
 * the raster preview under `payload.raster`. Normalise both to a common
 * `{ src, shape, sliceAxisName, sliceAxisSize, sliceIndex, image_metadata }`.
 */
function viewModel(envelope, kind) {
  const payload = payloadOf(envelope);
  const meta = payload.image_metadata && typeof payload.image_metadata === "object" ? payload.image_metadata : {};
  if (kind === "composite") {
    const raster = payload.raster && typeof payload.raster === "object" ? payload.raster : null;
    return {
      src: raster ? raster.src : null,
      shape: raster ? raster.shape : null,
      sliceAxisName: raster ? raster.slice_axis_name : null,
      sliceAxisSize: raster ? raster.slice_axis_size : null,
      sliceIndex: raster ? raster.slice_index : null,
      slots: payload.slots && typeof payload.slots === "object" ? payload.slots : {},
      imageMetadata: meta,
      isLabel: true,
    };
  }
  return {
    src: payload.src || null,
    shape: payload.shape || null,
    sliceAxisName: payload.slice_axis_name ?? null,
    sliceAxisSize: payload.slice_axis_size ?? null,
    sliceIndex: payload.slice_index ?? null,
    slots: null,
    imageMetadata: meta,
    isLabel: false,
  };
}

/* ---------------------------------------------------------------------------
 * The PreviewerModule export.
 * ------------------------------------------------------------------------- */

const previewerModule = {
  apiVersion: API_VERSION,

  /**
   * @param {HTMLElement} container host-owned DOM mount point
   * @param {object} host PreviewHostApi instance (constrained, read-only)
   */
  mount(container, host) {
    // ---- view state (client-side only; no workflow truth) ----------------
    const state = {
      scale: 1,
      panX: 0,
      panY: 0,
      isDragging: false,
      dragStart: null,
      lutName: "gray",
      minDisplay: 0,
      maxDisplay: 255,
      vm: viewModel(host.envelope, host.kind),
    };

    // ---- root + canvas image ---------------------------------------------
    const root = el("div", { display: "flex", flexDirection: "column", gap: "0px", fontSize: "10px" });

    const stage = el("div", {
      position: "relative",
      overflow: "hidden",
      borderRadius: "0.8rem 0.8rem 0 0",
      background: "#1e293b",
      height: "300px",
      cursor: "grab",
    });
    const imgEl = el("img", {
      position: "absolute",
      left: "50%",
      top: "50%",
      maxWidth: "none",
      maxHeight: "none",
      userSelect: "none",
    });
    imgEl.alt = "Image preview";
    imgEl.draggable = false;
    stage.appendChild(imgEl);

    const badge = el(
      "div",
      {
        position: "absolute",
        bottom: "6px",
        left: "6px",
        fontSize: "10px",
        color: "#94a3b8",
        background: "rgba(0,0,0,0.5)",
        padding: "2px 8px",
        borderRadius: "3px",
        pointerEvents: "none",
      },
      { textContent: "" },
    );
    badge.dataset.testid = "image-info-badge";
    stage.appendChild(badge);
    root.appendChild(stage);

    // ---- controls panel ---------------------------------------------------
    const panel = el("div", {
      padding: "8px 10px",
      borderRadius: "0 0 0.8rem 0.8rem",
      border: "1px solid #e7e5e4",
      borderTop: "none",
      background: "#fff",
      fontSize: "10px",
    });
    root.appendChild(panel);

    // Slice slider row (only when a >1 slider axis exists).
    const sliceRow = el("div", { display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px" });
    sliceRow.dataset.testid = "image-slice-slider-row";
    const sliceLabel = el("span", { width: "70px", color: "#78716c" });
    const sliceInput = el("input", { flex: "1" }, { type: "range", min: "0" });
    sliceInput.dataset.testid = "image-slice-slider";
    const sliceReadout = el("span", { minWidth: "38px", textAlign: "right", color: "#78716c" });
    sliceRow.append(sliceLabel, sliceInput, sliceReadout);
    panel.appendChild(sliceRow);

    // Zoom row.
    const zoomRow = el("div", { display: "flex", alignItems: "center", gap: "4px", marginBottom: "6px" });
    const btnStyle = {
      fontSize: "12px",
      padding: "1px 8px",
      border: "1px solid #d6d3d1",
      borderRadius: "4px",
      cursor: "pointer",
      background: "#fff",
    };
    const zoomIn = el("button", btnStyle, { type: "button", textContent: "+", title: "Zoom in" });
    zoomIn.setAttribute("aria-label", "Zoom in");
    const zoomReadout = el("span", { minWidth: "3rem", textAlign: "center", color: "#78716c" });
    const zoomOut = el("button", btnStyle, { type: "button", textContent: "−", title: "Zoom out" });
    zoomOut.setAttribute("aria-label", "Zoom out");
    const resetBtn = el(
      "button",
      {
        fontSize: "10px",
        padding: "2px 8px",
        border: "1px solid #d6d3d1",
        borderRadius: "4px",
        cursor: "pointer",
        background: "#fff",
        color: "#78716c",
        marginLeft: "auto",
      },
      { type: "button", textContent: "Reset" },
    );
    const exportBtn = el(
      "button",
      {
        fontSize: "10px",
        padding: "2px 8px",
        border: "1px solid #d6d3d1",
        borderRadius: "4px",
        cursor: "pointer",
        background: "#fff",
        color: "#78716c",
        marginLeft: "6px",
      },
      { type: "button", textContent: "Export" },
    );
    exportBtn.setAttribute("aria-label", "Export image");
    zoomRow.append(zoomIn, zoomReadout, zoomOut, resetBtn, exportBtn);
    panel.appendChild(zoomRow);

    // LUT selector row (9 swatches).
    const lutRow = el("div", { display: "flex", alignItems: "center", gap: "4px", marginBottom: "4px" });
    lutRow.append(el("span", { width: "30px", color: "#78716c" }, { textContent: "LUT" }));
    const lutBox = el("div", { display: "flex", gap: "2px", flex: "1", flexWrap: "wrap" });
    const lutButtons = {};
    Object.keys(LUTS).forEach((name) => {
      const sw = el("button", {
        width: "20px",
        height: "14px",
        borderRadius: "2px",
        cursor: "pointer",
        padding: "0",
        border: name === state.lutName ? "2px solid #3b82f6" : "1px solid #475569",
        background: `linear-gradient(to right, ${lutGradient(LUTS[name])})`,
      });
      sw.type = "button";
      sw.title = name;
      sw.setAttribute("aria-label", `LUT ${name}`);
      sw.addEventListener("click", () => {
        state.lutName = name;
        syncLutButtons();
        void recolour();
      });
      lutButtons[name] = sw;
      lutBox.appendChild(sw);
    });
    lutRow.appendChild(lutBox);
    panel.appendChild(lutRow);

    // Min / Max display range rows.
    function rangeRow(labelText, ariaLabel, min, max) {
      const row = el("div", { display: "flex", alignItems: "center", gap: "6px", marginBottom: "2px" });
      row.append(el("span", { width: "30px", color: "#78716c" }, { textContent: labelText }));
      const input = el("input", { flex: "1" }, { type: "range", min: String(min), max: String(max) });
      input.setAttribute("aria-label", ariaLabel);
      const readout = el("span", { width: "24px", textAlign: "right", color: "#78716c" });
      row.append(input, readout);
      return { row, input, readout };
    }
    const minCtl = rangeRow("Min", "Display minimum", 0, 254);
    const maxCtl = rangeRow("Max", "Display maximum", 1, 255);
    minCtl.input.value = String(state.minDisplay);
    maxCtl.input.value = String(state.maxDisplay);
    panel.append(minCtl.row, maxCtl.row);

    // OME/channel metadata panel.
    const metaPanel = el("div", {
      marginTop: "6px",
      paddingTop: "6px",
      borderTop: "1px solid #f1f5f9",
      color: "#64748b",
      lineHeight: "1.5",
    });
    metaPanel.dataset.testid = "image-metadata-panel";
    panel.appendChild(metaPanel);

    // ---- rendering --------------------------------------------------------
    function syncLutButtons() {
      Object.keys(lutButtons).forEach((name) => {
        lutButtons[name].style.border = name === state.lutName ? "2px solid #3b82f6" : "1px solid #475569";
      });
    }

    function applyTransform() {
      imgEl.style.transform =
        `translate(-50%, -50%) translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
      imgEl.style.imageRendering = state.scale > 2 ? "pixelated" : "auto";
      zoomReadout.textContent = `${Math.round(state.scale * 100)}%`;
      const shapeStr = state.vm.shape && state.vm.shape.length ? `${state.vm.shape.join(" × ")} | ` : "";
      badge.textContent = `${shapeStr}${Math.round(state.scale * 100)}%`;
    }

    function recolour() {
      const baseSrc = state.vm.src;
      if (!baseSrc) {
        imgEl.removeAttribute("src");
        return Promise.resolve();
      }
      if (state.lutName === "gray" && state.minDisplay === 0 && state.maxDisplay === 255) {
        imgEl.src = baseSrc;
        return Promise.resolve();
      }
      return applyLUTToImage(baseSrc, LUTS[state.lutName] || LUTS.gray, state.minDisplay, state.maxDisplay).then(
        (url) => {
          imgEl.src = url;
        },
      );
    }

    function renderMeta() {
      const md = state.vm.imageMetadata || {};
      metaPanel.replaceChildren();
      const lines = [];
      if (state.vm.isLabel && state.vm.slots) {
        lines.push(`slots: ${Object.keys(state.vm.slots).join(", ") || "(none)"}`);
      }
      if (md.objective) lines.push(`objective: ${md.objective}`);
      if (md.instrument) lines.push(`instrument: ${md.instrument}`);
      if (md.source_file) lines.push(`source: ${md.source_file}`);
      if (typeof md.n_objects === "number") lines.push(`objects: ${md.n_objects}`);
      if (Array.isArray(md.channels) && md.channels.length) {
        lines.push(`channels: ${md.channels.map((c) => c.name || "?").join(", ")}`);
      }
      if (Array.isArray(md.wavelengths_nm) && md.wavelengths_nm.length) {
        lines.push(`wavelengths(nm): ${md.wavelengths_nm.join(", ")}`);
      }
      if (md.has_ome) lines.push("OME metadata present");
      if (!lines.length) {
        metaPanel.style.display = "none";
        return;
      }
      metaPanel.style.display = "block";
      lines.forEach((text) => metaPanel.appendChild(el("div", null, { textContent: text })));
    }

    function renderSlice() {
      const size = state.vm.sliceAxisSize;
      const showSlider = typeof size === "number" && size > 1;
      sliceRow.style.display = showSlider ? "flex" : "none";
      if (!showSlider) return;
      const idx = typeof state.vm.sliceIndex === "number" ? state.vm.sliceIndex : 0;
      sliceLabel.textContent = `${state.vm.sliceAxisName || "axis"} (${size})`;
      sliceInput.max = String(size - 1);
      sliceInput.value = String(idx);
      sliceInput.setAttribute("aria-label", `Slice slider for ${state.vm.sliceAxisName || "axis"}`);
      sliceReadout.textContent = `${idx + 1}/${size}`;
    }

    function renderAll() {
      renderSlice();
      renderMeta();
      applyTransform();
      void recolour();
    }

    // ---- interaction ------------------------------------------------------
    function setScale(next) {
      state.scale = Math.max(0.1, Math.min(20, next));
      applyTransform();
    }

    const onWheel = (e) => {
      e.preventDefault();
      setScale(state.scale * (e.deltaY < 0 ? 1.15 : 0.87));
    };
    stage.addEventListener("wheel", onWheel, { passive: false });

    const onMouseDown = (e) => {
      state.isDragging = true;
      state.dragStart = { mx: e.clientX, my: e.clientY, px: state.panX, py: state.panY };
      stage.style.cursor = "grabbing";
    };
    const onMouseMove = (e) => {
      if (!state.isDragging || !state.dragStart) return;
      state.panX = state.dragStart.px + (e.clientX - state.dragStart.mx);
      state.panY = state.dragStart.py + (e.clientY - state.dragStart.my);
      applyTransform();
    };
    const onMouseUp = () => {
      state.isDragging = false;
      state.dragStart = null;
      stage.style.cursor = "grab";
    };
    stage.addEventListener("mousedown", onMouseDown);
    stage.addEventListener("mousemove", onMouseMove);
    stage.addEventListener("mouseup", onMouseUp);
    stage.addEventListener("mouseleave", onMouseUp);

    zoomIn.addEventListener("click", () => setScale(state.scale * 1.25));
    zoomOut.addEventListener("click", () => setScale(state.scale * 0.8));
    resetBtn.addEventListener("click", () => {
      state.scale = 1;
      state.panX = 0;
      state.panY = 0;
      state.lutName = "gray";
      state.minDisplay = 0;
      state.maxDisplay = 255;
      minCtl.input.value = "0";
      maxCtl.input.value = "255";
      syncLutButtons();
      renderAll();
    });
    exportBtn.addEventListener("click", () => {
      try {
        const p = host.exportArtifact({ resourceId: "export", filename: "image.png", format: "png" });
        if (p && typeof p.catch === "function") {
          p.catch((err) => host.reportError("export failed", { error: String(err) }));
        }
      } catch (err) {
        host.reportError("export failed", { error: String(err) });
      }
    });

    minCtl.input.addEventListener("input", () => {
      const v = Math.min(Number(minCtl.input.value), state.maxDisplay - 1);
      state.minDisplay = v;
      minCtl.input.value = String(v);
      minCtl.readout.textContent = String(v);
      void recolour();
    });
    maxCtl.input.addEventListener("input", () => {
      const v = Math.max(Number(maxCtl.input.value), state.minDisplay + 1);
      state.maxDisplay = v;
      maxCtl.input.value = String(v);
      maxCtl.readout.textContent = String(v);
      void recolour();
    });
    minCtl.readout.textContent = String(state.minDisplay);
    maxCtl.readout.textContent = String(state.maxDisplay);

    // Slice slider: drive the server re-render via the bounded session API.
    let sliceTimer = null;
    sliceInput.addEventListener("input", () => {
      const idx = Number(sliceInput.value);
      sliceReadout.textContent = `${idx + 1}/${state.vm.sliceAxisSize || 1}`;
      if (sliceTimer) clearTimeout(sliceTimer);
      sliceTimer = setTimeout(() => {
        try {
          const p = host.session.patchQuery({ slice_index: idx });
          if (p && typeof p.then === "function") {
            p.then((env) => {
              if (env) instance.update(env);
            }).catch((err) => host.reportError("slice fetch failed", { error: String(err) }));
          }
        } catch (err) {
          host.reportError("slice fetch failed", { error: String(err) });
        }
      }, 200);
    });

    container.appendChild(root);
    syncLutButtons();
    renderAll();

    const instance = {
      update(envelope) {
        state.vm = viewModel(envelope, host.kind);
        renderAll();
      },
      unmount() {
        if (sliceTimer) clearTimeout(sliceTimer);
        stage.removeEventListener("wheel", onWheel);
        stage.removeEventListener("mousedown", onMouseDown);
        stage.removeEventListener("mousemove", onMouseMove);
        stage.removeEventListener("mouseup", onMouseUp);
        stage.removeEventListener("mouseleave", onMouseUp);
        if (root.parentNode) root.parentNode.removeChild(root);
      },
    };
    return instance;
  },
};

export default previewerModule;
