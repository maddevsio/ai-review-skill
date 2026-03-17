---
name: pr-review
description: PR review — verify plan compliance, code quality, trace completeness
allowed-tools:
  - Bash(python3 .claude/skills/pr-review/scripts/*)
  - Bash(gh pr list *)
  - Bash(gh pr view *)
  - Bash(git log *)
  - Bash(git show *)
  - Bash(cat /tmp/pr-diff-*)
  - Bash(grep * /tmp/pr-diff-*)
  - Bash(sed -n * /tmp/pr-diff-*)
  - Bash(rm /tmp/pr-diff-* /tmp/pr-diff-raw-* /tmp/pr-comments-* /tmp/pr-summary-*)
  - Bash(ls *)
  - Bash(echo *)
  - Read(*)
  - Glob(*)
---

## What this command does

Reviews a PR against its intended scope (implementation plan, PR description, or linked issues). Analyzes code quality per task and posts a structured review comment on the PR.

## Input

- **Argument:** PR URL or PR number (e.g., `https://github.com/<org>/<repo>/pull/123` or `123`)
- If no argument provided:
  1. Run `gh pr list --state open` to fetch currently open PRs
  2. Display the list to the user (number, title, author, branch)
  3. Ask the user which PR to review — do NOT auto-select any PR
- Once the PR number is determined, ask the user which review mode to use with `AskUserQuestion`:
  - **"Inline comments"** — full phase-by-phase review with per-finding inline comments
  - **"Summary overview"** — high-level safety assessment posted as a single review comment

## Preparation

Glob for `*.md` files in the project root and common documentation directories (`docs/`, `.claude/`, etc.). Read all found files to understand project standards, patterns, ADRs, and trace/plan templates before starting the review.

## Setup

1. Extract PR number from the URL/argument.
2. Use `gh pr view <number> --json headRefName,baseRefName,number,title,files` to get branch info and changed files.
3. Determine the scope of this PR. If the project uses plan files, find the one relevant to this PR by looking within the changed files list from step 2 — do not pick up plan files that are not part of this PR's diff, as there may be unrelated plans from other developers or issues. If no plan file exists, fall back to the PR description, linked issues, and commit messages to understand what this PR is supposed to implement.
4. Fetch and annotate the diff with line numbers:
   ```bash
   python3 .claude/skills/pr-review/scripts/fetch-diff.py <number>
   python3 .claude/skills/pr-review/scripts/annotate-diff.py <number>
   ```
   Read `/tmp/pr-diff-<number>.txt` into context — this is the annotated diff you will reference throughout the entire review. Line numbers shown in the annotated diff are the authoritative new-file line numbers. Use them when producing file/line references in your analysis.

## Summary Flow

_Follow this section only if the user selected "Summary overview". Skip to Review Phases if they selected "Inline comments"._

### Analysis

Read the annotated diff at `/tmp/pr-diff-<number>.txt` along with the PR metadata gathered in Setup. Answer one question: **IS IT SAFE TO MERGE THIS PR?**

Focus exclusively on:
- Critical bugs that could cause crashes, data loss, or incorrect behavior in production
- Security vulnerabilities (injection, auth bypass, sensitive data exposure, etc.)
- Breaking changes to APIs, interfaces, or contracts
- Missing error handling in critical execution paths
- Obvious logic errors or off-by-one mistakes
- Performance issues severe enough to cause service degradation

Do NOT report on: code style, naming conventions, documentation gaps, test coverage, or minor improvements.

Write your assessment to `/tmp/pr-summary-<number>.txt` using this exact structure:

```
## Overall Assessment
[SAFE TO MERGE / NEEDS ATTENTION / DO NOT MERGE]
One-sentence verdict.

## Critical Issues
[List only blockers. If none, write "None identified."]

## Notable Concerns
[Secondary issues worth knowing but not blocking. If none, write "None."]

## Summary
2–3 sentences wrapping up your assessment.
```

Display the written assessment to the user.

### Publishing

Ask the user what action to take with `AskUserQuestion`:
- **"Approve"** — post the summary and approve the PR (`APPROVE`)
- **"Request changes"** — post the summary and request changes (`REQUEST_CHANGES`)
- **"Post as comment"** — post the summary with no verdict (`COMMENT`)
- **"Cancel"** — do not post anything

If "Cancel": go straight to Cleanup.

Otherwise run:
```bash
python3 .claude/skills/pr-review/scripts/post-summary.py <number> /tmp/pr-summary-<number>.txt <event>
```

### Cleanup

```bash
rm /tmp/pr-diff-<number>.txt /tmp/pr-diff-raw-<number>.txt /tmp/pr-summary-<number>.txt
```

Return to the user: summary posted, verdict applied.

---

## Review Phases

### Phase 1: Code quality per task (static analysis)

For each task, read the changed files and evaluate:

1. **Plan compliance** — is the task implemented as described? If a plan exists, check files listed in plan vs actual changes. If no plan, verify the implementation matches the PR description and linked issues.
2. **Standards & CLAUDE.md compliance** — holistic check against project standards:
   - **ADRs**: all applicable Architecture Decision Records followed as documented in the project.
   - **Patterns**: code follows documented patterns (state machines, layering, error wrapping, etc.)
   - **Antipatterns**: no violations from the project's antipattern list.
   - **CLAUDE.md rules**: conventional commits, atomic commits, no `--amend` on pushed commits, worktree isolation used.
3. **SoC** — does each module/component have one responsibility?
4. **DRY** — is there code/logic duplication?
5. **KISS** — is the solution simple or over-engineered?
6. **Security** — no injection, no secrets in code, boundary validation.
7. **Hardcoded values** — no hardcoded ports, URLs, credentials, or status strings that should live in config/env/constants.
8. **API/Schema contracts** — if API contracts or schema files changed: backward compatible, fields follow conventions.
9. **i18n** (frontend only) — all user-visible text uses the project's i18n mechanism; new keys present in all locale dictionaries.
10. **Event system** (if events added/changed) — channel/topic names follow convention, payload structure matches consumer expectations, no cross-channel leaks.
11. **Observability** (backend/services) — new business-critical code paths have appropriate logging and metrics. Not every function needs instrumentation — only responsibility-bearing paths: failure branches, state transitions, external calls, retry/escalation logic. Silent failures are unacceptable in production paths. Skip if the project is a pure frontend or CLI with no logging infrastructure.

### Phase 3: Trace & process review

1. Find the trace/log file (modified in PR) if the project uses them.
2. Check against the project's trace template:
   - [ ] Has all required sections (e.g., "What was done", "What was learned", "Problems", "Technical decisions", "Tech debt", "Proposals")
   - [ ] Technical decisions are documented with rationale
   - [ ] Tech debt discovered is listed with priority
   - [ ] Proposals section has patterns, antipatterns, lessons
3. If a plan exists, check that the plan progress table shows all tasks as `done` with timestamps.
4. If a plan exists, check plan frontmatter: `status: completed`.
5. Check atomic commits: `git log --oneline <baseRefName>..<branch>` — conventional format?

### Phase 4: Merge-blocking criteria (HARD BLOCKERS)

These checks block merging **when applicable**. If the project does not use a given practice, mark it ➖ N/A. If it exists and fails, the verdict MUST be ❌ regardless of score.

| # | Blocker | Applies when | How to verify | Fail action |
|---|---------|--------------|---------------|-------------|
| B1 | **No E2E / acceptance test conducted** | Project requires E2E testing before merge | Search trace for E2E evidence: deployment, feature walkthrough, lifecycle completion, UI observation | Verdict = ❌, note "E2E test required before merge" |
| B2 | **No trace file** | Project uses trace/log files | No new/modified trace file in PR diff | Verdict = ❌, note "Trace file missing" |
| B3 | **Trace missing required sections** | B2 is applicable and trace file exists | Any required sections absent or empty | Verdict = ❌, note which sections are missing |
| B4 | **Plan progress not updated** | Project uses plan files | Progress table has tasks not marked `✅ done` or missing timestamps | Verdict = ❌, note "Plan progress table incomplete" |
| B5 | **Plan frontmatter not `completed`** | Project uses plan files | `status:` in plan frontmatter is not `completed` | Verdict = ❌, note "Plan status not set to completed" |

For each applicable blocker that fails, write an inline comment on the relevant file/line explaining what's missing.

## Comment Format

Write review comments to `/tmp/pr-comments-<number>.txt` as you complete each phase. Use this structured format:

**Single-line comment:**
```
FILE: path/to/file.ts
LINE: 42
COMMENT: your review comment
---
```

**Multi-line comment** (only when ALL lines between START_LINE and END_LINE have `+` prefix in the diff):
```
FILE: path/to/file.ts
START_LINE: 40
END_LINE: 45
COMMENT: your review comment
---
```

**Rules:**
- Line numbers come from the annotated diff (`/tmp/pr-diff-<number>.txt`)
- Only comment on `+` lines (added/modified code)
- If no issues found in a phase: skip — write nothing for that phase
- If the entire PR has no issues: write `LGTM` to the file (no blocks)
- Write blocks incrementally as each phase completes — do not accumulate in context

## Moderation

Before posting, iterate through each comment and ask the user to keep or discard it:

1. Read `/tmp/pr-comments-<number>.txt`. If it contains only `LGTM`, skip moderation and go to Publishing.
2. Parse all blocks. For each block, ask the user using `AskUserQuestion`:
   - Header: `Comment N of M — path/to/file.ts:LINE`
   - Show the full comment body in the question text
   - Two options: **"Keep"** / **"Discard"**
3. Collect all kept blocks.
4. After the last comment, rewrite `/tmp/pr-comments-<number>.txt` with only the kept blocks (or `LGTM` if all were discarded).
5. Ask the user what action to take using `AskUserQuestion` with four options:
   - **"Approve"** — post comments and approve the PR (`APPROVE`)
   - **"Request changes"** — post comments and request changes (`REQUEST_CHANGES`)
   - **"Post comments only"** — post comments with no verdict (`COMMENT`)
   - **"Cancel"** — discard everything, do not post
6. If "Cancel": skip Publishing, go straight to cleanup.
7. Otherwise proceed to Publishing with the chosen event.

## Publishing

1. Run the comment poster, passing the chosen event:
   ```bash
   python3 .claude/skills/pr-review/scripts/post-comments.py <number> /tmp/pr-comments-<number>.txt <event>
   ```
   where `<event>` is `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`.
2. Delete temp files:
   ```bash
   rm /tmp/pr-diff-<number>.txt /tmp/pr-diff-raw-<number>.txt /tmp/pr-comments-<number>.txt
   ```

## Output

Return to user:
1. N inline comments posted
2. List of skipped comments (if any) with reasons

## Parallelization

Use subagents where possible:
- **Per-task code review** — can be parallelized across tasks
- **Trace review** — independent, can run in parallel with code review

## After context compaction

Re-read:
1. Project architecture/standards documentation — patterns, antipatterns
2. The plan file — task list and expected implementation (if plan exists)
3. `/tmp/pr-diff-<number>.txt` — the annotated diff
4. `/tmp/pr-comments-<number>.txt` — comments written so far (inline comments mode)
5. `/tmp/pr-summary-<number>.txt` — summary written so far (summary mode)
