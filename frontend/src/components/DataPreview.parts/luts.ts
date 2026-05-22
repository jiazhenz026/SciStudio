// LUT Colormaps (canvas-based, matching OptEasy).
//
// Each LUT is a 256-entry lookup table mapping greyscale intensity to
// [r, g, b]. ``applyLUTToImage`` runs a canvas-based transform on a
// dataURL so we can re-color the preview without round-tripping the
// raw array through the backend.

export type LUT = [number, number, number][];

function buildLUT(fn: (t: number) => [number, number, number]): LUT {
  return Array.from({ length: 256 }, (_, i) => {
    const [r, g, b] = fn(i);
    return [
      Math.max(0, Math.min(255, Math.round(r))),
      Math.max(0, Math.min(255, Math.round(g))),
      Math.max(0, Math.min(255, Math.round(b))),
    ] as [number, number, number];
  });
}

export const LUTS: Record<string, LUT> = {
  gray: Array.from({ length: 256 }, (_, i) => [i, i, i] as [number, number, number]),
  fire: buildLUT((t) => [
    Math.min(255, t * 3),
    Math.max(0, (t - 85) * 3),
    Math.max(0, (t - 170) * 3),
  ]),
  ice: buildLUT((t) => [
    Math.max(0, (t - 170) * 3),
    Math.max(0, (t - 85) * 3),
    Math.min(255, t * 3),
  ]),
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

export function lutGradient(lut: LUT): string {
  const stops = [0, 64, 128, 192, 255].map((i) => {
    const [r, g, b] = lut[i];
    return `rgb(${r},${g},${b})`;
  });
  return stops.join(", ");
}

export function applyLUTToImage(
  dataUrl: string,
  lut: LUT,
  minVal: number,
  maxVal: number,
): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data;
      const range = maxVal - minVal || 1;

      for (let i = 0; i < pixels.length; i += 4) {
        const gray = pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114;
        const normalized = Math.max(0, Math.min(255, ((gray - minVal) / range) * 255));
        const idx = Math.round(normalized);
        const [r, g, b] = lut[idx] ?? [idx, idx, idx];
        pixels[i] = r;
        pixels[i + 1] = g;
        pixels[i + 2] = b;
      }

      ctx.putImageData(imageData, 0, 0);
      resolve(canvas.toDataURL("image/png"));
    };
    img.src = dataUrl;
  });
}
