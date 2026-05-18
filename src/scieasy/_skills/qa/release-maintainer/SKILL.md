---
name: release-maintainer
description: Version bump + CHANGELOG slice + tag.
allowed-tools: [Read, Edit, Bash]
kind: procedural
priority: P1
pointer: docs/contributing/workflows/release-maintainer.md
adr: 42
---

# release-maintainer skill

For canonical procedure, read: `docs/contributing/workflows/release-maintainer.md`

After reading, execute in order:
1. Slice `[Unreleased]` from `CHANGELOG.md` into a dated release section.
2. Bump `version` in `pyproject.toml` per SemVer (consult §16 audit report for breaking-change flags).
3. Tag via `git tag -a vX.Y.Z -m "..."` and push.
4. Confirm CI release workflow ran clean before announcing.

When uncertain, prefer no edit with explanation.
