# Live REST smoke transcript — PR-C #1356 branch-delete orphan guard

Date: 2026-05-21
Backend: `PYTHONPATH=src python -m scistudio gui --port 8766 --no-browser` from
`feat/issue-1356/branch-delete-orphan-guard` (commit `02c2704d`).
Project: `C:/tmp/smoke-1356/smoke-1356`.

End-to-end repro of ADR-039 Addendum 1 §11.4 row #1356 — silent auto-tag
safety net on branch delete.

## Scenario

1. Create a feature branch on a fresh project.
2. Add a divergent commit to the feature branch (simulates a workflow run).
3. Insert a `runs` row with `workflow_git_commit = <feature-tip-sha>`.
4. Switch back to `main`, delete the feature branch via REST.
5. Verify: branch is gone, `refs/scistudio/lineage/<sha>` exists, SHA still
   reachable, Lineage Restore still works, lineage refs do NOT pollute
   BranchPicker (`/api/git/branches`) or History chip labels (`/api/git/log`).

## 1. Setup

```
$ curl -X POST /api/projects/ -d '{"name":"smoke-1356", ...}'
{"id":"project-bbb7a066", "path":"C:\\tmp\\smoke-1356\\smoke-1356", ...}

$ curl -X POST /api/git/branch/create -d '{"name":"feature-1356"}'
{"status":"ok","name":"feature-1356"}

$ curl -X POST /api/git/branch/switch -d '{"branch_name":"feature-1356"}'
{"status":"ok","current_branch":"feature-1356","auto_commit_sha":"b6274c69..."}

$ echo "id: feature\nnodes: []\n" > <project>/workflows/feature.yaml
$ curl -X POST /api/git/commit -d '{"message":"feature tip commit"}'
{"commit_sha":"e5f7840e6abf521733f205db0bdb28ef0fe3a86a"}
```

The feature branch now has a divergent tip at `e5f7840e`.

## 2. Insert lineage row referencing the feature tip

Direct sqlite insert into the project's `.scistudio/lineage.db` (the
running GUI process opens fresh connections per call, so the row is
visible to the next `/api/git/branches/feature-1356` DELETE):

```python
INSERT INTO runs (
    run_id, workflow_id, workflow_git_commit, ...
) VALUES (
    'smoke-1356-run',
    'feature',
    'e5f7840e6abf521733f205db0bdb28ef0fe3a86a',
    ...
)
```

Verified row present:

```
('smoke-1356-run', 'e5f7840e6abf521733f205db0bdb28ef0fe3a86a')
```

## 3. Delete the feature branch (the GUI BranchPicker trash-icon path)

```
$ curl -X POST /api/git/branch/switch -d '{"branch_name":"main"}'
{"status":"ok","current_branch":"main","auto_commit_sha":"2128356..."}

$ curl -X DELETE /api/git/branches/feature-1356?force=true
{"status":"ok"}
```

Note the response shape is unchanged — **no warn dialog, no payload
change**. This is the owner-decided option C silent auto-tag behavior.

## 4. Verify the safety net pinned the orphan SHA

```
$ curl /api/git/branches
[{"name":"main","head_sha":"b6274c69...","is_current":true}]
```

Branch list shows ONLY `main` — the feature branch is gone AND the new
`refs/scistudio/lineage/*` ref does NOT pollute the picker.

```
$ git -C <project> for-each-ref --format='%(refname) -> %(objectname)' \
    'refs/scistudio/lineage/*'
refs/scistudio/lineage/e5f7840e6abf521733f205db0bdb28ef0fe3a86a
  -> e5f7840e6abf521733f205db0bdb28ef0fe3a86a
```

The lineage ref exists, named after the SHA, pointing at the SHA.

```
$ git -C <project> cat-file -e e5f7840e6abf521733f205db0bdb28ef0fe3a86a
$ echo "exit code: $?"
exit code: 0
```

The SHA is still reachable — `git gc` will preserve it.

## 5. Lineage Restore still works after the branch delete

This is the end-state guarantee: the Lineage tab's "Restore this run's
workflow" path resolves `runs.workflow_git_commit` via plain `git`.

```
$ curl -X POST /api/git/restore -d '{"commit_sha":"e5f7840e..."}'
{"status":"ok","auto_commit_sha":null}

$ ls <project>/workflows/
feature.yaml   ← restored from the orphan SHA
main.yaml
```

The `workflows/feature.yaml` file that only existed on the deleted
branch is restored. Without the safety net, the SHA would have been
unreachable after `git gc` and restore would have failed.

## 6. Verify lineage refs are hidden from the History chip renderer

```
$ curl /api/git/log?limit=3
b6274c6  branches=["main"]
e5f7840  branches=[]              ← orphan commit, NO chip label
035df2e  branches=[]
```

The orphan commit `e5f7840` has `branches: []` — the lineage ref does
NOT generate a chip label. This is by design: `log()` scans
`refs/heads/`, `refs/remotes/`, and `refs/tags/`. The
`refs/scistudio/lineage/*` namespace is deliberately outside all three.

## Summary

| Invariant | Verified |
|---|---|
| Branch deleted | yes |
| Response payload unchanged (no warn, no auto_commit_sha) | yes |
| `refs/scistudio/lineage/<sha>` ref created | yes |
| Orphan SHA still reachable via `git cat-file -e` | yes |
| Lineage Restore on the deleted-branch run still works | yes |
| Lineage refs do NOT appear in `/api/git/branches` (BranchPicker) | yes |
| Lineage refs do NOT appear in `/api/git/log` chip labels | yes |

Owner option C (silent auto-tag) acceptance criteria all pass.
