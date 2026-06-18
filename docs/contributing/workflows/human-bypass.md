---
title: "Human Bypass Workflow"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-gate-record-sentrux-workflow
---

# Human Bypass Workflow

## 1. Change Summary

This workflow explains how human maintainers bypass AI-only gate requirements
without bypassing repository quality checks. It implements ADR-042 Section 9 and
ADR-042 Addendum 1.

Human bypass is reviewable. Human maintainers may skip local hooks, including
all hooks, when they judge that local enforcement is blocking legitimate work.
Final code quality is decided through PR review and CI.

## 2. What Can Be Bypassed

Human-authored PRs may bypass AI-only evidence checks when the
`human-authored` label is applied by an authorized maintainer:

- committed AI gate record requirement;
- AI-only local gate session requirement;
- AI commit trailers such as `Assisted-by`;
- persona-policy checks that apply only to AI runtime configuration;
- AI-only artifact and codemod requirements when the PR has no AI-authored
  commits.

## 3. What Cannot Be Bypassed

Human bypass does not decide final repository quality. PR review and CI remain
the final quality boundary.

Recommended local checks for human-authored changes are:

```bash
PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --mode local
pytest <targeted-tests-or-test-directory>
python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json
```

Humans may skip all local hooks when needed:

```bash
git commit --no-verify
```

If local hooks are skipped, the PR should say so briefly. The reviewer decides
whether the submitted checks and CI signal are sufficient.

## 4. Local Procedure

1. Confirm the PR is human-authored.
2. Prefer running the standard human check set:

```bash
PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --mode local
pytest <targeted-tests-or-test-directory>
python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json
```

3. If only one AI-only hook is blocking you, you may skip only that hook:

```bash
SKIP=scistudio-gate-record-pre-commit git commit
```

4. If several local hooks block legitimate human work, skip all local hooks:

```bash
git commit --no-verify
```

5. Mention skipped hooks in the PR body if relevant. PR review is the final
   quality decision.

## 5. PR Procedure

1. Open the PR normally.
2. The PR body must close the issue delivered by the PR:

```text
Closes #1234
```

3. In the PR body, add a short human-authored statement:

```text
Human-authored PR. Requesting human-authored label for AI-only gate bypass.
Quality checks run:
- gate_record check --mode local
- pytest ...
- full audit ...
Local hooks skipped: yes/no
```

4. Ask an authorized maintainer to apply the `human-authored` label.
5. Wait for CI and review. CI may mark AI-only gate checks as `skipped-human`.
   Reviewers decide whether the submitted check evidence is sufficient.
6. If the PR contains AI-authored commits, `Assisted-by` trailers, or an active
   AI gate record, `human-authored` alone is not enough. Either provide normal
   AI gate evidence or request the `admin-approved:bypass` administrator
   override.

## 6. Administrator Override Procedure

Use administrator overrides only for narrow recovery cases.

1. Record the reason in the PR body or review comment.
2. Apply the specific label:
   - `human-authored` for human-authored PRs;
   - `admin-approved:bypass` for one-off AI gate workflow override;
   - `admin-approved:core-change` for protected core changes;
   - `admin-approved:merge` for approved merge automation.
3. Ensure CI verifies the actor who applied the label.
4. Override labels do not merge PRs by themselves; reviewers still decide final
   quality.

## 7. CI Expectations

CI treats human bypass as follows:

- AI-only gate checks may report `skipped-human`;
- `human_bypass_guard` verifies label provenance;
- invalid label provenance fails CI;
- AI evidence in the PR disables the simple `human-authored` bypass unless an
  administrator override is also recorded.

## 8. Examples

Human docs PR:

```text
Closes #1300

Human-authored PR. Requesting human-authored label for AI-only gate bypass.
Quality checks run:
- python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json
Local hooks skipped: no
```

Human source PR:

```text
Closes #1301

Human-authored PR. Requesting human-authored label for AI-only gate bypass.
Quality checks run:
- gate_record check --mode local
- pytest tests/qa/test_example.py
- python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json
Local hooks skipped: yes
```
