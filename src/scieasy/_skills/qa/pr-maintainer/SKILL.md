---
name: pr-maintainer
description: Triage labels, dedup, RBP-gate enforcement on open pull requests.
allowed-tools: [Bash, Read]
kind: procedural
priority: P1
pointer: docs/contributing/workflows/pr-maintainer.md
adr: 42
---

# pr-maintainer skill

For canonical procedure, read: `docs/contributing/workflows/pr-maintainer.md`

After reading, execute in order:
1. `gh pr list --json number,title,labels --state open` to triage.
2. For each PR: confirm `Closes #N` body, RBP artifact (if §14.2 class applies), CI green, Codex reconcile complete.
3. Apply labels per `.github/labels.yaml` taxonomy; dedup against existing PRs.
4. Merge only when all gates pass; never `--no-verify`.

When uncertain, prefer no edit with explanation.
