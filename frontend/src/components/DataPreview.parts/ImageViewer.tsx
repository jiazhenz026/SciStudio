import { useCallback, useEffect, useRef, useState } from "react";

import { LUTS, applyLUTToImage, lutGradient } from "./luts";

export interface ImageViewerProps {
  src: string;
  shape?: number[];
  /**
   * #899 — when the underlying array is 3-D and a slider axis was
   * detected by the backend, these props drive the horizontal slider
   * shown below the image canvas. ``onSliceChange`` is called with the
   * new integer index on every drag; the parent handles fetch +
   * cache + debounce. Render no slider when ``sliceAxisSize`` is null
   * or ``<= 1``.
   */
  sliceAxisName?: string | null;
  sliceAxisSize?: number | null;
  sliceIndex?: number | null;
  onSliceChange?: (idx: number) => void;
}

interface PanState {
  x: number;
  y: number;
}

function useImagePanZoom(): {
  scale: number;
  pan: PanState;
  isDragging: boolean;
  containerRef: React.RefObject<HTMLDivElement>;
  onMouseDown: (e: React.MouseEvent) => void;
  onMouseMove: (e: React.MouseEvent) => void;
  onMouseUp: () => void;
  zoom: (delta: number) => void;
  resetPanZoom: () => void;
} {
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState<PanState>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    setScale((prev) => Math.max(0.1, Math.min(20, prev * (e.deltaY < 0 ? 1.15 : 0.87))));
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  const onMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y };
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !dragStart.current) return;
    setPan({
      x: dragStart.current.px + (e.clientX - dragStart.current.mx),
      y: dragStart.current.py + (e.clientY - dragStart.current.my),
    });
  };

  const onMouseUp = () => {
    setIsDragging(false);
    dragStart.current = null;
  };

  const zoom = (delta: number) => {
    setScale((prev) => Math.max(0.1, Math.min(20, prev * delta)));
  };

  const resetPanZoom = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  return {
    scale,
    pan,
    isDragging,
    containerRef,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    zoom,
    resetPanZoom,
  };
}

function useLUTProcessing(src: string): {
  lutName: string;
  setLutName: (name: string) => void;
  minDisplay: number;
  setMinDisplay: (v: number) => void;
  maxDisplay: number;
  setMaxDisplay: (v: number) => void;
  processedUrl: string | null;
  resetLut: () => void;
} {
  const [lutName, setLutName] = useState("gray");
  const [minDisplay, setMinDisplay] = useState(0);
  const [maxDisplay, setMaxDisplay] = useState(255);
  const [processedUrl, setProcessedUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!src) {
      setProcessedUrl(null);
      return;
    }
    if (lutName === "gray" && minDisplay === 0 && maxDisplay === 255) {
      setProcessedUrl(src);
      return;
    }
    void applyLUTToImage(src, LUTS[lutName] ?? LUTS.gray, minDisplay, maxDisplay).then(
      setProcessedUrl,
    );
  }, [src, lutName, minDisplay, maxDisplay]);

  const resetLut = () => {
    setLutName("gray");
    setMinDisplay(0);
    setMaxDisplay(255);
  };

  return {
    lutName,
    setLutName,
    minDisplay,
    setMinDisplay,
    maxDisplay,
    setMaxDisplay,
    processedUrl,
    resetLut,
  };
}

function ImageCanvas({
  src,
  shape,
  scale,
  pan,
  isDragging,
  containerRef,
  onMouseDown,
  onMouseMove,
  onMouseUp,
}: {
  src: string | null;
  shape?: number[];
  scale: number;
  pan: PanState;
  isDragging: boolean;
  containerRef: React.RefObject<HTMLDivElement>;
  onMouseDown: (e: React.MouseEvent) => void;
  onMouseMove: (e: React.MouseEvent) => void;
  onMouseUp: () => void;
}) {
  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: "0.8rem 0.8rem 0 0",
        background: "#1e293b",
        height: "300px",
        cursor: isDragging ? "grabbing" : "grab",
      }}
      onMouseDown={onMouseDown}
      onMouseLeave={onMouseUp}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
    >
      {src && (
        <img
          alt="Preview"
          draggable={false}
          src={src}
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            imageRendering: scale > 2 ? "pixelated" : "auto",
            maxWidth: "none",
            maxHeight: "none",
            userSelect: "none",
          }}
        />
      )}
      <div
        data-testid="image-info-badge"
        style={{
          position: "absolute",
          bottom: 6,
          left: 6,
          fontSize: 10,
          color: "#94a3b8",
          background: "rgba(0,0,0,0.5)",
          padding: "2px 8px",
          borderRadius: 3,
          pointerEvents: "none",
        }}
      >
        {shape ? `${shape.join(" × ")} | ` : ""}
        {Math.round(scale * 100)}%
      </div>
    </div>
  );
}

function SliceSliderRow({
  sliceAxisName,
  sliceAxisSize,
  sliceIndex,
  onSliceChange,
}: {
  sliceAxisName?: string | null;
  sliceAxisSize: number;
  sliceIndex?: number | null;
  onSliceChange: (idx: number) => void;
}) {
  return (
    <div
      data-testid="image-slice-slider-row"
      style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}
    >
      <span style={{ width: 70, color: "#78716c" }}>
        {(sliceAxisName ?? "axis") + ` (${sliceAxisSize})`}
      </span>
      <input
        aria-label={`Slice slider for ${sliceAxisName ?? "axis"}`}
        data-testid="image-slice-slider"
        type="range"
        min={0}
        max={sliceAxisSize - 1}
        value={sliceIndex ?? 0}
        onChange={(e) => onSliceChange(Number(e.target.value))}
        style={{ flex: 1 }}
      />
      <span style={{ minWidth: 38, textAlign: "right", color: "#78716c" }}>
        {(sliceIndex ?? 0) + 1}/{sliceAxisSize}
      </span>
    </div>
  );
}

function ZoomRow({
  scale,
  onZoom,
  onReset,
}: {
  scale: number;
  onZoom: (delta: number) => void;
  onReset: () => void;
}) {
  const btn = {
    fontSize: 12,
    padding: "1px 8px",
    border: "1px solid #d6d3d1",
    borderRadius: 4,
    cursor: "pointer",
    background: "#fff",
  };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 6 }}>
      <button aria-label="Zoom in" onClick={() => onZoom(1.25)} type="button" style={btn}>
        +
      </button>
      <span style={{ minWidth: "3rem", textAlign: "center", color: "#78716c" }}>
        {Math.round(scale * 100)}%
      </span>
      <button aria-label="Zoom out" onClick={() => onZoom(0.8)} type="button" style={btn}>
        −
      </button>
      <button
        onClick={onReset}
        type="button"
        style={{
          fontSize: 10,
          padding: "2px 8px",
          border: "1px solid #d6d3d1",
          borderRadius: 4,
          cursor: "pointer",
          background: "#fff",
          color: "#78716c",
          marginLeft: "auto",
        }}
      >
        Reset
      </button>
    </div>
  );
}

function LUTSelector({
  lutName,
  setLutName,
}: {
  lutName: string;
  setLutName: (name: string) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
      <span style={{ width: 30, color: "#78716c" }}>LUT</span>
      <div style={{ display: "flex", gap: 2, flex: 1, flexWrap: "wrap" }}>
        {Object.keys(LUTS).map((name) => (
          <button
            key={name}
            aria-label={`LUT ${name}`}
            onClick={() => setLutName(name)}
            title={name}
            type="button"
            style={{
              width: 20,
              height: 14,
              borderRadius: 2,
              cursor: "pointer",
              padding: 0,
              border: name === lutName ? "2px solid #3b82f6" : "1px solid #475569",
              background: `linear-gradient(to right, ${lutGradient(LUTS[name])})`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

function MinMaxRange({
  minDisplay,
  setMinDisplay,
  maxDisplay,
  setMaxDisplay,
}: {
  minDisplay: number;
  setMinDisplay: (v: number) => void;
  maxDisplay: number;
  setMaxDisplay: (v: number) => void;
}) {
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
        <span style={{ width: 30, color: "#78716c" }}>Min</span>
        <input
          aria-label="Display minimum"
          type="range"
          min={0}
          max={254}
          value={minDisplay}
          onChange={(e) => setMinDisplay(Math.min(Number(e.target.value), maxDisplay - 1))}
          style={{ flex: 1 }}
        />
        <span style={{ width: 24, textAlign: "right", color: "#78716c" }}>{minDisplay}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 30, color: "#78716c" }}>Max</span>
        <input
          aria-label="Display maximum"
          type="range"
          min={1}
          max={255}
          value={maxDisplay}
          onChange={(e) => setMaxDisplay(Math.max(Number(e.target.value), minDisplay + 1))}
          style={{ flex: 1 }}
        />
        <span style={{ width: 24, textAlign: "right", color: "#78716c" }}>{maxDisplay}</span>
      </div>
    </>
  );
}

export function ImageViewer({
  src,
  shape,
  sliceAxisName,
  sliceAxisSize,
  sliceIndex,
  onSliceChange,
}: ImageViewerProps) {
  const panZoom = useImagePanZoom();
  const lut = useLUTProcessing(src);

  const reset = () => {
    panZoom.resetPanZoom();
    lut.resetLut();
  };

  const displaySrc = lut.processedUrl ?? src;
  const showSlider =
    sliceAxisSize !== null &&
    sliceAxisSize !== undefined &&
    sliceAxisSize > 1 &&
    onSliceChange !== undefined;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0px" }}>
      <ImageCanvas
        src={displaySrc}
        shape={shape}
        scale={panZoom.scale}
        pan={panZoom.pan}
        isDragging={panZoom.isDragging}
        containerRef={panZoom.containerRef}
        onMouseDown={panZoom.onMouseDown}
        onMouseMove={panZoom.onMouseMove}
        onMouseUp={panZoom.onMouseUp}
      />
      <div
        style={{
          padding: "8px 10px",
          borderRadius: "0 0 0.8rem 0.8rem",
          border: "1px solid #e7e5e4",
          borderTop: "none",
          background: "#fff",
          fontSize: 10,
        }}
      >
        {/*
         * #899 — 3-D slice slider. Renders only when the backend
         * reports a slider axis with > 1 entries. Slider position
         * updates parent state immediately; parent handles 200 ms
         * debounce + slice cache + fetch.
         */}
        {showSlider && onSliceChange ? (
          <SliceSliderRow
            sliceAxisName={sliceAxisName}
            sliceAxisSize={sliceAxisSize as number}
            sliceIndex={sliceIndex}
            onSliceChange={onSliceChange}
          />
        ) : null}
        <ZoomRow scale={panZoom.scale} onZoom={panZoom.zoom} onReset={reset} />
        <LUTSelector lutName={lut.lutName} setLutName={lut.setLutName} />
        <MinMaxRange
          minDisplay={lut.minDisplay}
          setMinDisplay={lut.setMinDisplay}
          maxDisplay={lut.maxDisplay}
          setMaxDisplay={lut.setMaxDisplay}
        />
      </div>
    </div>
  );
}
