// Project/UI targeting belongs to the renderer broker. This boundary only
// captures pixels of the owning SciStudio main window, never another app.
const MAX_PNG_BYTES = 4 * 1024 * 1024;

async function captureGui(window, event, request) {
  if (!window || window.isDestroyed() || event.sender !== window.webContents ||
      event.senderFrame !== window.webContents.mainFrame) {
    throw new Error("Only the SciStudio workspace may request a GUI screenshot");
  }
  if (!window.isVisible() || window.isMinimized()) {
    throw new Error("SciStudio window is hidden or minimized; show it before capturing");
  }
  const rect = request?.rect;
  if (!rect || !["x", "y", "width", "height"].every((key) => Number.isInteger(rect[key])) ||
      rect.x < 0 || rect.y < 0 || rect.width < 1 || rect.height < 1 ||
      rect.width > 16384 || rect.height > 16384) {
    throw new Error("Capture requires a bounded rectangle inside the workspace");
  }
  const url = event.sender.getURL();
  const zoom = event.sender.getZoomFactor();
  const bounds = window.getContentSize();
  const x = Math.floor(rect.x * zoom);
  const y = Math.floor(rect.y * zoom);
  let right = Math.ceil((rect.x + rect.width) * zoom);
  let bottom = Math.ceil((rect.y + rect.height) * zoom);
  // Blink exposes integer CSS viewport dimensions. At fractional zoom their
  // round-trip can exceed the DIP content bounds by at most one CSS pixel.
  // Clip that rounding fringe; never ask the compositor for pixels outside it.
  const fringe = Math.ceil(zoom);
  if (x >= bounds[0] || y >= bounds[1] || right > bounds[0] + fringe || bottom > bounds[1] + fringe) {
    throw new Error("Capture rectangle extends outside the workspace");
  }
  right = Math.min(right, bounds[0]);
  bottom = Math.min(bottom, bounds[1]);
  let changed = false;
  const invalidate = () => { changed = true; };
  window.on("hide", invalidate);
  window.on("minimize", invalidate);
  event.sender.on("did-start-navigation", invalidate);
  event.sender.on("zoom-changed", invalidate);
  let shot;
  try {
    shot = await event.sender.capturePage({ x, y, width: right - x, height: bottom - y }, { stayHidden: true, stayAwake: false });
    if (changed || window.isDestroyed() || !window.isVisible() || window.isMinimized() ||
        event.sender.getURL() !== url || event.sender.getZoomFactor() !== zoom || shot.isEmpty()) {
      throw new Error("SciStudio changed, navigated or returned an empty screenshot; retry");
    }
  } finally {
    window.removeListener("hide", invalidate);
    window.removeListener("minimize", invalidate);
    event.sender.removeListener("did-start-navigation", invalidate);
    event.sender.removeListener("zoom-changed", invalidate);
  }
  let size = shot.getSize();
  const scale = Math.min(1, 1920 / size.width, 1920 / size.height, Math.sqrt(4_000_000 / (size.width * size.height)));
  if (scale < 1) {
    shot = shot.resize({ width: Math.max(1, Math.floor(size.width * scale)), height: Math.max(1, Math.floor(size.height * scale)), quality: "best" });
    size = shot.getSize();
  }
  const bytes = shot.toPNG();
  if (bytes.length > MAX_PNG_BYTES) throw new Error("GUI screenshot is too large; capture a smaller MiniApp target");
  return { png_base64: bytes.toString("base64"), width: size.width, height: size.height };
}

module.exports = { captureGui };
