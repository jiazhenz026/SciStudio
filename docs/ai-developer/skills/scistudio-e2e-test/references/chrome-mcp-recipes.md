# Chrome MCP Recipes

Reusable patterns for driving the SciStudio GUI via Chrome MCP. Each
recipe is small and self-contained — copy the one you need into the
current step instead of trying to keep all of this in your head.

## Table Of Contents

1. [Monaco direct manipulation](#1-monaco-direct-manipulation)
2. [Fetch interception (delay / race conditions)](#2-fetch-interception)
3. [Native dialog hooks (alert / confirm / prompt)](#3-native-dialog-hooks)
4. [Project tree button matching](#4-project-tree-button-matching)
5. [Native picker / dialog bypass](#5-native-picker-bypass)
6. [Reading persisted store state](#6-reading-persisted-store-state)
7. [Reading live event counts](#7-reading-live-event-counts)
8. [Backend restart after editable-install changes](#8-backend-restart)

---

## 1. Monaco Direct Manipulation

`window.monaco.editor.getModels()` returns all loaded models — even for
non-active tabs. `model.setValue(text)` fires the editor's `onChange`,
which routes to the store's `updateFileTabContent`. Use this to simulate
continuous typing without keyboard events. `monaco.editor.getModelMarkers({resource: model.uri})`
reads the live markers — the source of truth for lint-related assertions.

```javascript
const models = window.monaco.editor.getModels();
const target = models.find(m => m.uri.path.endsWith('blocks/my_block.py'));
target.setValue("new\ncontent");
const markers = window.monaco.editor.getModelMarkers({ resource: target.uri });
JSON.stringify({ markerCount: markers.length, markers });
```

When the test needs to type without firing onChange synchronously, use
`model.applyEdits([{range, text}])` instead — gives finer control over
range manipulation.

## 2. Fetch Interception

Delay or fail specific URL families to reproduce stuck-loading or race
conditions. Always preserve `opts.method` and pass `arguments` through.

```javascript
const origFetch = window.fetch;
window.fetch = function(url, opts) {
  if (typeof url === 'string' && url.includes('/api/projects')) {
    return new Promise(res => setTimeout(
      () => origFetch.apply(this, arguments).then(res),
      3000  // 3s delay
    ));
  }
  return origFetch.apply(this, arguments);
};
```

To restore: store the original on `window.__origFetch` first and restore
in cleanup.

## 3. Native Dialog Hooks

Install BEFORE the click that might pop a dialog. Native `alert` /
`confirm` / `prompt` freeze Chrome MCP entirely; the only recovery is
the user dismissing in their actual browser.

```javascript
window.__alertCalls = window.__alertCalls || [];
window.__confirmCalls = window.__confirmCalls || [];
window.alert = (msg) => { window.__alertCalls.push(msg); };
window.confirm = (msg) => { window.__confirmCalls.push(msg); return true; };
window.prompt = (msg, def) => { window.__confirmCalls.push({prompt: msg, default: def}); return def; };
```

After the action, assert:

```javascript
JSON.stringify({
  alerts: window.__alertCalls,
  confirms: window.__confirmCalls,
});
// Expect alerts: [] if the regression sentinel says "no native dialogs"
```

## 4. Project Tree Button Matching

Buttons in `ProjectTree.tsx` render as multi-line text with emoji prefix:
`"▶\n📁\nblocks"`. Exact-match `innerText.trim() === 'blocks'` fails.
Use a combined check:

```javascript
[...document.querySelectorAll('[data-testid^="tree-node-"]')]
  .find(n => n.innerText.includes('blocks') && n.innerText.includes('📁'));
```

Or use the test id directly if the tree exposes one:

```javascript
document.querySelector('[data-testid="tree-node-blocks"]');
```

## 5. Native Picker Bypass

`New Project` opens a folder picker; `Browse` opens a file picker. Both
are native OS dialogs — Chrome MCP cannot interact with them.

Bypass by going direct to the API and then clicking the resulting
recent-card to open the project in the running GUI:

```powershell
$body = @{ name = "e2e-test-project"; path = "C:\Users\jiazh\Downloads\e2e-tmp" } | ConvertTo-Json
curl -X POST -H "Content-Type: application/json" -d $body http://localhost:8000/api/projects/
```

Then in Chrome:

```javascript
[...document.querySelectorAll('[data-testid^="recent-project-"]')]
  .find(n => n.innerText.includes('e2e-test-project'))
  .click();
```

## 6. Reading Persisted Store State

`localStorage["scistudio-studio-ui"].state.tabs` is the canonical persistence
shape. After `partializeFileTab` strips content, `tabs[i].loading === true`
is the rehydration sentinel. This is more reliable than introspecting
React fibers (window has no direct store handle).

```javascript
const state = JSON.parse(localStorage.getItem('scistudio-studio-ui')).state;
JSON.stringify({
  tabCount: state.tabs.length,
  activeTabId: state.activeTabId,
  loadingTabs: state.tabs.filter(t => t.loading).map(t => t.id),
});
```

## 7. Reading Live Event Counts

Count rendered events in the AIChat / log streams without scraping text:

```javascript
JSON.stringify({
  total: document.querySelectorAll('[data-testid^="ev-"]').length,
  byType: [...document.querySelectorAll('[data-testid^="ev-"]')]
    .reduce((acc, n) => {
      const type = n.dataset.testid.replace('ev-', '');
      acc[type] = (acc[type] || 0) + 1;
      return acc;
    }, {}),
});
```

## 8. Backend Restart

`frontend/dist` is the dev-fallback for `_resolve_spa_static_dir`. After
`npm run build` writes new output there, the backend must be restarted —
the static mount is set up once at startup, so a running backend keeps
serving the old bundle.

```powershell
# 1. Kill the existing scistudio gui process
Get-Process python | Where-Object { $_.CommandLine -match 'scistudio gui' } | Stop-Process -Force

# 2. Wait for the port to free
Start-Sleep 1

# 3. Restart with the same args
Start-Process -NoNewWindow scistudio -ArgumentList 'gui', '--port', '8000', '--no-browser'

# 4. Wait for readiness
$deadline = (Get-Date).AddSeconds(60)
do {
  Start-Sleep 0.5
  $ok = $false
  try { $r = Invoke-WebRequest http://localhost:8000/api/health -UseBasicParsing; $ok = $r.StatusCode -eq 200 } catch {}
} while (-not $ok -and (Get-Date) -lt $deadline)
if (-not $ok) { throw "Backend did not become ready within 60s" }
```

If you are running from a worktree, double-check `scistudio.__file__` —
editable-install contamination from a sibling worktree is a real failure
mode.

---

## Related

- `screenshot-recipes.md` — DPI-aware capture, tab activation
- `dev-server-lifecycle.md` — port hygiene, process lifecycle
