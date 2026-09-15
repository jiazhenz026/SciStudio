// Isolated native compositor fixture, launched by the gated packaging test.
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { captureGui } = require('../../gui-capture');
const output = process.env.SCISTUDIO_GUI_SMOKE_OUTPUT;
app.setPath('userData', path.join(output, 'electron-profile'));
app.setName('SciStudio GUI capture test');
let window;
let count = 0;
const deadline = setTimeout(() => app.exit(2), 15000);
ipcMain.handle('scistudio:capture-gui', async (event, request) => {
  const result = await captureGui(window, event, request);
  fs.writeFileSync(path.join(output, `${count}.json`), JSON.stringify(result));
  fs.writeFileSync(path.join(output, `${count}.png`), Buffer.from(result.png_base64, 'base64'));
  if (++count === 2) setTimeout(() => { clearTimeout(deadline); app.quit(); }, 100);
  return result;
});
const child = `<!doctype html><html><body style="margin:0;display:flex"><canvas id="flat" width="256" height="256"></canvas><canvas id="gpu" width="256" height="256"></canvas><script>
const flat=document.getElementById('flat').getContext('2d');
const gpu=document.getElementById('gpu').getContext('webgl',{preserveDrawingBuffer:true});
function paint(value){flat.fillStyle=value>50?'#196dcc':'#eaa321';flat.fillRect(0,0,256,256);flat.fillStyle='white';flat.font='bold 28px sans-serif';flat.fillText('Threshold '+value,20,120);if(gpu){gpu.clearColor(value>50?0.1:0.8,0.4,value>50?0.8:0.1,1);gpu.clear(gpu.COLOR_BUFFER_BIT);}requestAnimationFrame(()=>requestAnimationFrame(()=>parent.postMessage({painted:value,gpu:!!gpu},'*')));}
addEventListener('message',e=>{if(e.source===parent)paint(e.data.value)});paint(20);
<\/script></body></html>`;
const html = `<!doctype html><html><body style="margin:0;background:white"><h1 style="font:20px sans-serif">Isolated MiniApp screenshot fixture</h1><label>Threshold <input id="level" type="range" min="0" max="100" value="20"></label><iframe id="panel" sandbox="allow-scripts" style="display:block;width:512px;height:256px;border:0"></iframe><script>
const panel=document.getElementById('panel');const level=document.getElementById('level');let captures=0;
level.addEventListener('input',()=>panel.contentWindow.postMessage({value:Number(level.value)},'*'));
addEventListener('message',async e=>{if(e.source!==panel.contentWindow||!e.data.painted)return;if(!e.data.gpu)throw Error('WebGL unavailable');await new Promise(r=>setTimeout(r,150));const b=panel.getBoundingClientRect();await window.scistudioDesktop.captureGui({rect:{x:Math.round(b.x),y:Math.round(b.y),width:512,height:256}});if(++captures===1){level.value='80';level.dispatchEvent(new Event('input',{bubbles:true}));}});
panel.srcdoc=${JSON.stringify(child)};
<\/script></body></html>`;
app.whenReady().then(async () => {
  app.dock?.hide();
  window = new BrowserWindow({ width: 650, height: 430, show: false, title: 'SciStudio isolated screenshot test', webPreferences: { sandbox: true, preload: path.resolve(__dirname, '../../preload.js') } });
  window.showInactive();
  await window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
});
