const test = require('node:test');
const assert = require('node:assert/strict');
const { captureGui } = require('../gui-capture');
const { EventEmitter } = require('node:events');

function fixture() {
  const image = { isEmpty: () => false, getSize: () => ({ width: 800, height: 600 }), toPNG: () => Buffer.from('png') };
  const calls = [];
  const contents = Object.assign(new EventEmitter(), { mainFrame: {}, getZoomFactor: () => 1, getURL: () => 'http://localhost:8000', capturePage: async (...args) => { calls.push(args); return image; } });
  const window = Object.assign(new EventEmitter(), { getContentSize: () => [1000, 800], webContents: contents, isDestroyed: () => false, isVisible: () => true, isMinimized: () => false });
  return { window, event: { sender: contents, senderFrame: contents.mainFrame }, image, calls };
}
const request = { rect: { x: 10, y: 20, width: 400, height: 300 } };

test('only the main SciStudio frame can capture its owning window', async () => {
  const f = fixture();
  const result = await captureGui(f.window, f.event, request);
  assert.deepEqual(f.calls, [[request.rect, { stayHidden: true, stayAwake: false }]]);
  assert.equal(result.width, 800);
  await assert.rejects(captureGui(f.window, { ...f.event, senderFrame: {} }, request), /Only the SciStudio/);
  await assert.rejects(captureGui(f.window, { ...f.event, sender: {} }, request), /Only the SciStudio/);
});

test('hidden windows, invalid regions and navigation during capture return no pixels', async () => {
  const f = fixture();
  await assert.rejects(captureGui({ ...f.window, isMinimized: () => true }, f.event, request), /hidden or minimized/);
  await assert.rejects(captureGui(f.window, f.event, { rect: { ...request.rect, x: -1 } }), /bounded rectangle/);
  f.window.webContents.capturePage = async () => { f.window.webContents.getURL = () => 'changed'; return f.image; };
  await assert.rejects(captureGui(f.window, f.event, request), /navigated/);
});

test('large compositor images are resized and PNG byte bounds are enforced', async () => {
  const f = fixture();
  f.image.getSize = () => ({ width: 4000, height: 3000 });
  f.image.resize = ({ width, height }) => ({ getSize: () => ({ width, height }), toPNG: () => Buffer.alloc(4 * 1024 * 1024 + 1) });
  await assert.rejects(captureGui(f.window, f.event, request), /too large/);
});


test('CSS viewport coordinates follow zoom and transient hide invalidates capture', async () => {
  const f = fixture();
  f.event.sender.getZoomFactor = () => 1.5;
  await captureGui(f.window, f.event, request);
  assert.deepEqual(f.calls[0][0], { x: 15, y: 30, width: 600, height: 450 });
  f.event.sender.capturePage = async () => { f.window.emit('hide'); return f.image; };
  await assert.rejects(captureGui(f.window, f.event, request), /changed/);
  assert.equal(f.window.listenerCount('hide'), 0);
});


test('fractional zoom clips only integer CSS viewport rounding at the window edge', async () => {
  const f = fixture();
  f.event.sender.getZoomFactor = () => 1.5;
  await captureGui(f.window, f.event, { rect: { x: 0, y: 0, width: 667, height: 533 } });
  assert.deepEqual(f.calls[0][0], { x: 0, y: 0, width: 1000, height: 800 });
  await assert.rejects(captureGui(f.window, f.event, { rect: { x: 0, y: 0, width: 670, height: 533 } }), /outside the workspace/);
});
