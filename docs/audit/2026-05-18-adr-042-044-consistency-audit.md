# ADR-042 to ADR-044 Consistency and Citation Audit

Date: 2026-05-18
Scope: `docs/adr/ADR-042.md`, `docs/adr/ADR-043.md`, `docs/adr/ADR-044.md`
Audit focus: self-conflicts, wrong section references, wrong external citations, and concept drift.

## Executive Summary

ADR-042 through ADR-044 are directionally coherent, but they are not internally clean enough to promote without a fix pass. The main issues are:

- ADR-042's own bootstrap/prologue citations point at the wrong sections.
- ADR-043 extends several ADR-042 sections using stale section numbers.
- ADR-042 uses incorrect Codex skill/config paths relative to current Codex docs and ADR-040/ADR-044.
- The addenda defer work without concrete tracking artifacts, contradicting the repository TODO/deferred-work rule.
- Several external citations are over-specific or date-drifted, especially arXiv 2604.21090 and Linux kernel `Assisted-by:`.
- ADR-044's ADR-040 reference card overclaims authority by saying it supersedes conflicting ADR text while also saying ADR-040 is not modified by ADR-044.

Recommended disposition: fix the P0/P1 items before promoting any of the three ADRs beyond Draft.

## P0 Findings

### A1. ADR-042 bootstrap section references are wrong

Evidence:

- `docs/adr/ADR-042.md:140` says Phase 1 is `§26`, but the concrete Phase 1 section is `§26.2`.
- `docs/adr/ADR-042.md:197` says Phase 4 is `§26.5`, but `§26.5` is Phase 3; Phase 4 is `§26.6`.
- `docs/adr/ADR-042.md:267` says Phase 1 is `§27.2`, but `§27.2` is inline exemptions.
- `docs/adr/ADR-042.md:267` says the Fact Substitution Registry is `§11`, but it is `§10`.
- `docs/adr/ADR-042.md:271` says Phase 4 revalidation is `§29.3`, but it is `§28.3`.

Impact:
The bootstrap exemption window is one of ADR-042's central safety valves. If its own citations are wrong, downstream addenda cannot reliably inherit or enforce it.

Recommendation:
Update the prologue and template-freeze references to:

- Phase 1: `§26.2`
- Fact Substitution Registry: `§10`
- Phase 4: `§26.6`
- Post-Phase-4 revalidation: `§28.3`

### A2. ADR-043 extends stale ADR-042 section numbers

Evidence:

- `docs/adr/ADR-043.md:146` cites `ADR-042 §15 (committer.py)`, but `committer.py` is `ADR-042 §16`.
- `docs/adr/ADR-043.md:146` cites `ADR-042 §20 (tool stack)`, but tool stack is `ADR-042 §21`.
- `docs/adr/ADR-043.md:146` cites `ADR-042 §27 (self-iteration)`, but self-iteration is `ADR-042 §28`.
- `docs/adr/ADR-043.md:527-529` says Codex/Claude `PreToolUse` mirroring follows `ADR-042 §12.3 agent-equality`; `§12.3` is "Skills own workflows; root owns policy", not the agent-equality or hook-contract section.

Impact:
These are load-bearing addendum references. They will mislead implementers and any future cross-reference checker.

Recommendation:
Patch the references to `§16`, `§21`, `§28`, and cite either `ADR-042 §4.1` for agent-equality or the concrete hook/config section that actually governs the mechanism.

### A3. ADR-042 uses the wrong Codex skill/config locations

Evidence:

- `docs/adr/ADR-042.md:386` references a Codex `codex_config.toml` hook section.
- `docs/adr/ADR-042.md:1832` says Codex skills live at `~/.codex/skills/<name>/`.
- ADR-040 and ADR-044 consistently use `.agents/skills` for Codex skills.
- Current official Codex docs say user-level config is `~/.codex/config.toml`, project overrides live in `.codex/config.toml`, and Codex skills are read from repository/user/admin/system locations including `.agents/skills` and `$HOME/.agents/skills`.

Impact:
This is a concrete concept error, not just wording. If implemented as written, skill installation and hook/config validation would target the wrong Codex paths, violating ADR-042's agent-equality principle.

Recommendation:
Change Codex skill paths to `.agents/skills` / `$HOME/.agents/skills`, and change config wording to `~/.codex/config.toml` plus project `.codex/config.toml`.

### A4. Deferred work and TODO placeholders do not have concrete tracking artifacts

Evidence:

- `docs/adr/ADR-042.md:12-13`, `docs/adr/ADR-043.md:12-13`, and `docs/adr/ADR-044.md:12-13` all have `closes_issues: []` and `tracking_issue: null`.
- `docs/adr/ADR-042.md:142`, `docs/adr/ADR-042.md:270`, and `docs/adr/ADR-042.md:1951` refer to TODO/tracking markers, but use placeholder-style `TODO(#NNN)`.
- `docs/adr/ADR-043.md:1518-1523` and `docs/adr/ADR-044.md:197-202` defer future security/docs work to future addenda or releases without issue numbers, ADR section links, or concrete tracking URLs.

Impact:
This conflicts with the repository rule that out-of-scope/deferred behavior must be linked to a tracking artifact. It also weakens ADR-042's own traceability goal.

Recommendation:
Create or reference real issue numbers before promotion. Replace `#NNN`, "future addendum", and bare "defer" entries with concrete issue/ADR references.

## P1 Findings

### B1. ADR-042's transitional exemption does not cover future governed files

Evidence:

- ADR-042 frontmatter declares many future files under `governs.files`, including workflows, templates, generated docs, and audit paths.
- `docs/adr/ADR-042.md:276-280` limits the bootstrap exemption to hardcoded facts and governed-contract dotted paths that are not importable yet. It does not mention missing governed files.
- ADR-043 and ADR-044 also declare many future files while sharing the transitional window.

Impact:
Once file-existence/closure checks exist, the ADRs can fail their own rules before Phase 1 has created the declared files. This is a self-contract gap.

Recommendation:
Explicitly define how `governs.files` may reference planned files during the bootstrap window, or move planned artifacts into a `planned_files`/tracker section until they exist.

### B2. Related-ADR frontmatter is not symmetric after ADR-044

Evidence:

- `docs/adr/ADR-042.md:11` has `related: [40, 43]`, missing `44`.
- `docs/adr/ADR-043.md:11` has `related: [42]`, missing `44`.
- `docs/adr/ADR-044.md:11` has `related: [42, 43]`.

Impact:
The addendum chain is asymmetric. A reader starting from ADR-042 or ADR-043 will not discover ADR-044 from frontmatter.

Recommendation:
Update ADR-042 to include `44`, and ADR-043 to include `44`.

### B3. ADR-042 field reference points `agent_editable` to the wrong section

Evidence:

- `docs/adr/ADR-042.md:630` says `agent_editable` details are in `§14.1`.
- `§14.1` is the Real-Behavior-Proof statement, not an `agent_editable` definition.

Impact:
This is a stale self-reference in the schema reference section.

Recommendation:
Point to the section that actually defines editability semantics, or add a small `agent_editable` subsection under `§5`.

### B4. ADR-043's arXiv 2604.21090 citation is over-specific

Evidence:

- `docs/adr/ADR-043.md:1137-1138` says arXiv 2604.21090 found "37% of 34 audited AGENTS.md files fail this requirement" for data classification.
- The arXiv abstract says 37% of evaluated file-model pairs fall below the structural-completeness threshold, and that data classification and assessment rubric criteria are most frequently absent. It does not say 37% fail the data-classification requirement specifically.
- `docs/adr/ADR-043.md:1201` calls assessment rubric the "second-most-missing section"; the abstract supports "most frequently absent" as a group, not a precise rank.

Impact:
The research citation is directionally relevant but the numerical claim is too strong.

Recommendation:
Reword to: "arXiv 2604.21090 reports that 37% of evaluated file-model pairs fell below the structural-completeness threshold, with data classification and assessment-rubric criteria among the most frequently absent."

### B5. ADR-042's Linux kernel `Assisted-by:` citation has a stale date

Evidence:

- `docs/adr/ADR-042.md:3075` says the Linux kernel's `Assisted-by:` convention was "merged 2025".
- Current kernel documentation contains `Documentation/process/coding-assistants.rst` with the `Assisted-by: AGENT_NAME:MODEL_VERSION [TOOL1] [TOOL2]` format.
- Kernel mailing-list references around checkpatch support cite the coding-assistants document and related commits in 2026, not a 2025 merge.

Impact:
The trailer format is broadly aligned, but the date/prestige citation is wrong.

Recommendation:
Change the citation to "Linux kernel AI Coding Assistants documentation, 2026" unless a primary 2025 commit can be produced.

### B6. ADR-044 overclaims authority over ADR-040

Evidence:

- `docs/adr/ADR-044.md:140-141` says where Appendix A and any other ADR text disagree, Appendix A is correct.
- `docs/adr/ADR-044.md:1051-1054` says Appendix A supersedes any conflicting phrasing.
- `docs/adr/ADR-044.md:1153` says ADR-040 is not modified by ADR-044.

Impact:
ADR-044 cannot both avoid modifying ADR-040 and claim authority to supersede conflicting ADR text about ADR-040. That collapses ADR ownership boundaries.

Recommendation:
Demote Appendix A to a "reference card / audit summary". If it finds drift in ADR-040, file an ADR-040 addendum or correction rather than letting ADR-044 override it.

### B7. ADR-044 overstates Codex hook parity from ADR-040 Addendum 4

Evidence:

- `docs/adr/ADR-044.md:1108` summarizes A4 as "Codex hook parity".
- ADR-040 Addendum 4 records a known upstream gap: Codex 0.130 on Windows did not fire PreToolUse/PostToolUse hooks in the tested configurations.

Impact:
The summary is optimistic enough to mislead a reader into thinking parity is behaviorally verified on all supported platforms.

Recommendation:
Change to "Codex hook declarations/provisioning parity, with known Codex 0.130 Windows executor gap."

## P2 Findings

### C1. ADR-044's production boundary table needs a wording guardrail

Evidence:

- `docs/adr/ADR-044.md:1071-1074` says ADR-042/043/044 do not directly cover production.
- ADR-044 itself creates `docs/prod-agent/README.md` and `docs/user/prod-env-artifacts.md` to document production-agent artifacts.

Impact:
The intended meaning is probably "does not govern production runtime behavior", but the table can be misread as "does not cover prod-agent docs".

Recommendation:
Clarify the row as: "ADR-042/043/044 govern documentation and QA in the SciEasy source repo; ADR-040 governs production runtime behavior."

### C2. ADR-044 has a typo in consistency-scope wording

Evidence:

- `docs/adr/ADR-044.md:881` says "All ADRs (§/specs/architecture — already in scope)".

Impact:
Minor, but it is exactly the kind of reference-text drift ADR-042 is supposed to prevent.

Recommendation:
Replace with "All ADRs/specs/architecture docs — already in scope."

### C3. OpenClaw / NemoClaw / Agentic Control Plane references are not traceable enough

Evidence:

- ADR-042 Appendix C cites multiple OpenClaw patterns without stable public references.
- ADR-043 cites NemoClaw attack-pattern research and Agentic Control Plane-style concepts without stable URLs in the cross-reference table.
- Some may be internal project knowledge, but the ADRs do not label them as internal, private, or owner-provided.

Impact:
Readers cannot distinguish public precedent from internal design inspiration.

Recommendation:
For each such source, either add a stable URL, add an in-repo reference, or mark it explicitly as "internal/project-owner-provided context, not externally verifiable".

## Verified External Sources

- OpenAI Codex config reference: user config is `~/.codex/config.toml`; project overrides live in `.codex/config.toml` and load only for trusted projects.  
  https://developers.openai.com/codex/config-reference
- OpenAI Codex skills reference: repository/user skill locations use `.agents/skills` and `$HOME/.agents/skills`.  
  https://developers.openai.com/codex/skills
- Anthropic Claude Code memory docs: target under 200 lines per `CLAUDE.md`; path-scoped rules/skills are recommended for large or task-specific content.  
  https://code.claude.com/docs/en/memory
- GitHub Blog, 2025-11-19: 2,500+ `agents.md` analysis and three-tier boundaries example.  
  https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/
- GitHub Blog, 2026-05-07: "Any change that weakens CI is a blocker. Full stop."  
  https://github.blog/ai-and-ml/generative-ai/agent-pull-requests-are-everywhere-heres-how-to-review-them/
- arXiv 2604.21090: 34 AGENTS.md files; 37% of evaluated file-model pairs below structural-completeness threshold; data classification and assessment rubric criteria frequently absent.  
  https://arxiv.org/abs/2604.21090
- Linux kernel AI Coding Assistants documentation: `Assisted-by: AGENT_NAME:MODEL_VERSION [TOOL1] [TOOL2]`.  
  https://kernel.org/doc/html/next/process/coding-assistants.html
- Linux Foundation AAIF announcement: AGENTS.md donated/stewarded under the Agentic AI Foundation in December 2025.  
  https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation

## Suggested Fix Order

1. Patch all wrong section references in ADR-042 and ADR-043.
2. Correct Codex path/config terminology in ADR-042.
3. Add concrete tracking issues or remove placeholder TODO/deferred claims.
4. Reword overclaimed external citations.
5. Fix ADR-044 Appendix A authority language so ADR-040 remains the source of truth for ADR-040.
6. Add symmetric `related` frontmatter links across 042/043/044.
7. Clean remaining P2 wording issues.
