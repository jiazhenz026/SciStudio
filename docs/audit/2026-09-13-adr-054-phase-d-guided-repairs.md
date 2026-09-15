---
title: "ADR-054 Phase D guided audit repairs"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
related_specs:
  - adr-054-miniapp
language_source: en
---

# Guided audit repairs — 2026-09-13

Issue #2354; worktree `.worktrees/adr054-phase-d`, branch
`feat/2354-miniapp-phase-d`. The owner requested audit repair followed by a
running desktop for interactive testing. This is a guided testing checkpoint,
not a claim of PR readiness or a replacement for the original September 11
audit results.

## Repairs

| Audit surface | Change and regression coverage |
| --- | --- |
| WebSocket reconnect | Reuse the assigned client identity in reconnect URLs; defer MiniApp context creation until identity exists. Hook and tab tests cover both boundaries. |
| Canvas entry | Preserve the integrated MiniApp callbacks and portal the menu above the hover card. The desktop menu visibly exposes Open in Array explorer and New MiniApp. |
| Create / Convert | Adopt the returned terminal session with its actual provider and permission mode and reveal the AI panel. Dialog tests assert terminal registration and focus. |
| Preview column | Apply the store visibility request to the panel handle and synchronize resize state. The regression asserts actual imperative expansion. |
| Reload / toolbar / copy | Ignore historical file-change counters on mount, hide workflow controls over MiniApps, and use the MiniApp noun in promotion dialogs. |
| Source discovery | List available outputs across project workflows through the existing source resolver. Create uses the project listing; API coverage checks the new endpoint. |
| API responsiveness | Move stop outside the context lock, detach teardown without joining on the event loop, and execute blocking calls outside the AnyIO route limiter. HTTP regression sends blocked calls and probes a sync health route through process stop and crash. |
| Process ownership | Capture identity before launch; reclaim detached POSIX descendants on close and root crash; keep root ownership even when a Job Object reports no members. Windows launch requires suspended assignment and successful resume. Each launch also has a unique ownership token, and late cleanup is idempotent, so an old process monitor cannot kill or unregister a replacement process. |
| Teardown | Bound cooperative wait and termination, then kill remaining owned processes. Tests cover an in-flight call ignoring SIGTERM, detached descendants, and context deregistration. |
| Read-only contexts | Reject hardlinks to panel.py; advertise call only with Python; reject stop on contexts without a process. |
| Agent catalogue | Include the library category and remove obsolete gui_presence import suppression. |
| Desktop sidebar | Restore 280px first-open width and a 240px minimum; retain separate AI presentation sizing and manual widths. Hook regressions cover first open, drag-collapse/reopen, and presentation switching. |
| MiniApp presentation | Hide resident-memory metrics from the ordinary toolbar per the owner directive; preserve state and process controls. The tab regression confirms memory units are absent. |
| Repository evidence | Repair public docstring content, declared documentation coverage, stale scope omissions, and test synchronization. Record validation using the guided gate ledger. |

## Desktop startup diagnosis and observed result

The supplied desktop runtime is x86_64, while an installed plugin directory
contains arm64 NumPy. MiniApp launch previously prepended plugin roots before
runtime dependencies, producing an import failure with an empty log. MiniApps
now use the same sanitized startup environment and deferred import roots as
block workers. Bootstrap also records setup/import exceptions in the log and
the tab displays the process error.

After restarting the desktop-owned backend from this worktree, the existing
`ADR054-tests` project and its Array explorer MiniApp were exercised in the
Electron window:

- Process status reached Running with an 8 × 8 float32 array.
- The page reported one setup call. Changing threshold from 50 to 61 changed
  the result from 32/64 (50%) to 27/64 (42.19%).
- Switching to the workflow and back preserved threshold 61 and one setup call.
- Right-clicking a node showed readable MiniApp actions above the node hover UI.
- The active MiniApp had its own process controls and no workflow Run toolbar.

The owner resolved the separate macOS tray observation: menu-bar crowding hid
the icon. No desktop tray change was made.

## Evidence boundaries

Automated check events and sanitized outputs are recorded in
`.workflow/records/2354-guided-miniapp-audit-fixes.json`. The inherited integration
ledger's declared scope was also reconciled. Tests execute against explicit
Git candidate snapshots so the gate sees the uncommitted guided changes.

Native Windows process-tree execution, the missing independent no-context
review, full PR CI, and owner copy review remain obligations of #2354 before
Phase D can be declared ready to merge. Local Windows launch-failure tests use
API stubs and do not establish native Windows lifecycle behavior.
The comment-only cleanup in `engine/gui_presence.py` requires verified
maintainer authorization at PR time; the ledger records that requested label,
not an approval. No PR or merge is performed in this testing checkpoint.

The pre-existing scalar Load error in the test workflow (zero-dimensional
array indexed with one dimension) is outside the MiniApp audit scope and is
recorded here for #2354 triage. Array explorer testing
used the successful `load_one` output.


## Subsequent owner feedback

The owner found previous-project sources in a new project's create picker.
`open_project` clears the data catalogue while retaining workflow runs; the
MiniApp resolver had walked those retained runs without checking their launch
project and could re-register raw storage outputs. Source discovery and source
resolution now reject other-project or unowned runs before accessing outputs.
Regression coverage exercises real project creation/switching as well as list,
create, and context refusal with retained previous-project runs.

The frontend no longer seeds creation from canvas output caches, clears picker
state across projects, and ignores a superseded response. Labels identify node
instances instead of repeating block type names. The sidebar New button stays
on one line, and cards open with one click. Backend fixes require a desktop
backend restart at a user-approved testing boundary; the active session was not
interrupted while the owner continued testing.
