# Runtime Parity

## 1. Decision Summary

`ai_developers/skills/` is the canonical source for repository AI developer
skills. Runtime-specific skill directories are mirrors and must stay
synchronized.

Canonical source:

```text
ai_developers/skills/<skill-name>/SKILL.md
```

Runtime mirrors:

```text
.claude/skills/<skill-name>/SKILL.md
.codex/skills/<skill-name>/SKILL.md
.agents/skills/<skill-name>/SKILL.md
```

Rules:

- Edit canonical skills first.
- Mirror the exact content into all supported runtime directories.
- Do not add runtime-only repository rules.
- Do not let `.claude`, `.codex`, or `.agents` become more authoritative than
  `AGENTS.md` and `ai_developers/`.
- Keep local runtime settings, credentials, caches, and auth files ignored.
- Track only the intended skill mirror files.

Verification:

- Compare canonical skill files against every mirror before commit.
- Check that every canonical skill exists in every runtime directory.
- Check that every runtime mirror has a canonical counterpart.
