---
name: mr-review
description: MR review — verify plan compliance, code quality, trace completeness
allowed-tools:
  - Bash(python3 .claude/skills/mr-review/scripts/*)
  - Bash(git log *)
  - Bash(git show *)
  - Bash(cat /tmp/pr-diff-*)
  - Bash(grep * /tmp/pr-diff-*)
  - Bash(sed -n * /tmp/pr-diff-*)
  - Bash(rm /tmp/pr-diff-* /tmp/pr-diff-raw-* /tmp/pr-comments-* /tmp/pr-meta-* /tmp/pr-summary-*)
  - Bash(ls *)
  - Bash(echo *)
  - Read(*)
  - Glob(*)
---

## What this command does

Reviews a GitLab MR against its intended scope (implementation plan, MR description, or linked issues). Analyzes code quality per task and posts a structured review comment on the MR.

## Prerequisites

Before doing anything else, verify credentials are configured:

```bash
python3 .claude/skills/mr-review/scripts/check-credentials.py
```

If this fails, tell the user their GitLab credentials are not configured and guide them through setup:
1. Run `python3 .claude/skills/mr-review/scripts/setup.py` to generate `.claude/settings.local.json`
2. Open `.claude/settings.local.json` and fill in:
   - `GITLAB_TOKEN` — Personal Access Token from GitLab → User Settings → Access Tokens (scope: `api`)
3. Restart Claude Code to load the new environment variables
4. Re-run `/mr-review`

Do not proceed until credentials are set.

## Input

- **Argument:** MR URL or MR number (e.g., `https://gitlab.com/<namespace>/<repo>/-/merge_requests/42` or `42`)
- If no argument provided:
  1. Run `python3 .claude/skills/mr-review/scripts/list-mrs.py` to fetch currently open MRs
  2. Display the list to the user (number, title, author, branch)
  3. Ask the user which MR to review — do NOT auto-select any MR
- Once the MR number is determined, ask the user which review mode to use with `AskUserQuestion`:
  - **"Inline comments"** — full phase-by-phase review with per-finding inline comments
  - **"Summary overview"** — high-level safety assessment posted as a single MR note

## Preparation

Glob for `*.md` files in the project root and common documentation directories (`docs/`, `.claude/`, etc.). Read all found files to understand project standards, patterns, ADRs, and trace/plan templates before starting the review.

## Setup

1. Extract MR number from the URL/argument.
2. Run `python3 .claude/skills/mr-review/scripts/get-mr.py <number>` to get branch info and changed files. Parse the JSON output to extract `headRefName`, `baseRefName`, `diffRefs`, and `files`.
3. Determine the scope of this MR. If the project uses plan files, find the one relevant to this MR by looking within the changed files list from step 2 — do not pick up plan files that are not part of this MR's diff, as there may be unrelated plans from other developers or issues. If no plan file exists, fall back to the MR description, linked issues, and commit messages to understand what this MR is supposed to implement.
4. Fetch and annotate the diff with line numbers:
   ```bash
   python3 .claude/skills/mr-review/scripts/fetch-diff.py <number>
   python3 .claude/skills/mr-review/scripts/annotate-diff.py <number>
   ```
   Read `/tmp/pr-diff-<number>.txt` into context — this is the annotated diff you will reference throughout the entire review. Line numbers shown in the annotated diff are the authoritative new-file line numbers. Use them when producing file/line references in your analysis.

## Summary Flow

_Follow this section only if the user selected "Summary overview". Skip to Review Phases if they selected "Inline comments"._

### Analysis

Read the annotated diff at `/tmp/pr-diff-<number>.txt` along with the MR metadata gathered in Setup. Answer one question: **IS IT SAFE TO MERGE THIS MR?**

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
- **"Approve"** — post the summary and approve the MR (`APPROVE`)
- **"Request changes"** — post the summary and request changes (`REQUEST_CHANGES`)
- **"Post as comment"** — post the summary with no verdict (`COMMENT`)
- **"Cancel"** — do not post anything

If "Cancel": go straight to Cleanup.

Otherwise run:
```bash
python3 .claude/skills/mr-review/scripts/post-summary.py <number> /tmp/pr-summary-<number>.txt <event>
```

> **Note on REQUEST_CHANGES:** GitLab API v4 has no native "request changes" endpoint. Selecting this option appends a "⚠️ Changes requested" footer to the summary note itself — everything lands as one note, no formal "changes requested" state on the MR.

### Cleanup

```bash
rm /tmp/pr-diff-<number>.txt /tmp/pr-diff-raw-<number>.txt /tmp/pr-summary-<number>.txt /tmp/pr-meta-<number>.json
```

Return to the user: summary posted, verdict applied.

---

## Review Phases

### Phase 1: Code quality per task (static analysis)

For each task, read the changed files and evaluate:

1. **Plan compliance** — is the task implemented as described? If a plan exists, check files listed in plan vs actual changes. If no plan, verify the implementation matches the MR description and linked issues.
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

1. Find the trace/log file (modified in MR) if the project uses them.
2. Check against the project's trace template:
   - [ ] Has all required sections (e.g., "What was done", "What was learned", "Problems", "Technical decisions", "Tech debt", "Proposals")
   - [ ] Technical decisions are documented with rationale
   - [ ] Tech debt discovered is listed with priority
   - [ ] Proposals section has patterns, antipatterns, lessons
3. If a plan exists, check that the plan progress table shows all tasks as `done` with timestamps.
4. If a plan exists, check plan frontmatter: `status: completed`.
5. Check atomic commits: `git log --oneline <baseRefName>..<headRefName>` — conventional format?

### Phase 4: Merge-blocking criteria (HARD BLOCKERS)

These checks block merging **when applicable**. If the project does not use a given practice, mark it ➖ N/A. If it exists and fails, the verdict MUST be ❌ regardless of score.

| # | Blocker | Applies when | How to verify | Fail action |
|---|---------|--------------|---------------|-------------|
| B1 | **No E2E / acceptance test conducted** | Project requires E2E testing before merge | Search trace for E2E evidence: deployment, feature walkthrough, lifecycle completion, UI observation | Verdict = ❌, note "E2E test required before merge" |
| B2 | **No trace file** | Project uses trace/log files | No new/modified trace file in MR diff | Verdict = ❌, note "Trace file missing" |
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
TARGET_CODE: the exact code at that line
COMMENT: your review comment
---
```

**Multi-line comment** (only when ALL lines between START_LINE and END_LINE have `+` prefix in the diff):
```
FILE: path/to/file.ts
START_LINE: 40
END_LINE: 45
TARGET_CODE_START: the exact code at START_LINE
TARGET_CODE_END: the exact code at END_LINE
COMMENT: your review comment
---
```

**Rules:**
- `LINE` must be the line containing `TARGET_CODE` in the annotated diff — derive the line number from the code, not the other way around
- For block-level issues (missing test, incomplete implementation, wrong structure), `TARGET_CODE` must be the **opening line** of the block (`describe(`, `function`, `class`, `it(`, etc.) — never the closing bracket
- Line numbers come from the annotated diff (`/tmp/pr-diff-<number>.txt`)
- Only comment on `+` lines (added/modified code)
- If no issues found in a phase: skip — write nothing for that phase
- If the entire MR has no issues: write `LGTM` to the file (no blocks)
- Write blocks incrementally as each phase completes — do not accumulate in context

## Moderation

Before posting, iterate through each comment and ask the user to keep or discard it:

1. Read `/tmp/pr-comments-<number>.txt`. If it contains only `LGTM`, skip moderation and go to Publishing.
2. Parse all blocks. For each block:
   a. Run to get code context (use `START_LINE` for multi-line comments):
      ```bash
      python3 .claude/skills/mr-review/scripts/show-context.py <number> <file> <line>
      ```
   b. Ask the user using `AskUserQuestion`:
      - Header: `Comment N of M — path/to/file.ts:LINE`
      - Question text: include the code context block output from step (a), if any, followed by the comment body
      - Two options: **"Keep"** / **"Discard"**
3. Collect all kept blocks.
4. After the last comment, rewrite `/tmp/pr-comments-<number>.txt` with only the kept blocks (or `LGTM` if all were discarded).
5. Ask the user what action to take using `AskUserQuestion` with four options:
   - **"Approve"** — post comments and approve the MR (`APPROVE`)
   - **"Request changes"** — post comments and request changes (`REQUEST_CHANGES`)
   - **"Post comments only"** — post comments with no verdict (`COMMENT`)
   - **"Cancel"** — discard everything, do not post
6. If "Cancel": skip Publishing, go straight to cleanup.
7. Otherwise proceed to Publishing with the chosen event.

## Publishing

1. Run the comment poster, passing the chosen event:
   ```bash
   python3 .claude/skills/mr-review/scripts/post-comments.py <number> /tmp/pr-comments-<number>.txt <event>
   ```
   where `<event>` is `APPROVE`, `REQUEST_CHANGES`, or `COMMENT`.

   > **Note on REQUEST_CHANGES:** GitLab API v4 has no native "request changes" endpoint. Selecting this option will post all inline comments and add a general note stating changes are requested — but the MR will not enter a formal "changes requested" state as it would on GitHub.

2. Delete temp files:
   ```bash
   rm /tmp/pr-diff-<number>.txt /tmp/pr-diff-raw-<number>.txt /tmp/pr-comments-<number>.txt /tmp/pr-meta-<number>.json
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
