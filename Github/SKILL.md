---
name: pr-review
description: PR review — verify plan compliance, code quality, tests, coverage, trace completeness
---

## What this command does

Reviews a PR against its intended scope (implementation plan, PR description, or linked issues). Runs tests, checks coverage, analyzes code quality per task, and posts a structured review comment on the PR.

## Input

- **Argument:** PR URL or PR number (e.g., `https://github.com/<org>/<repo>/pull/123` or `123`)
- If no argument provided, ask the user for the PR URL/number

## Preparation

Read all available project documentation before starting the review: standards, patterns, architectural decisions, coverage thresholds, and any trace/plan templates. Look in the project root and any documentation directories.

## Setup worktree

1. Extract PR number from the URL/argument.
2. Use `gh pr view <number> --json headRefName,baseRefName,number,title,files` to get branch info and changed files.
3. Check if we're already in the correct worktree for this branch:
   - If yes — use it directly, skip cloning.
   - If no — create a temporary worktree:
     ```bash
     git fetch origin <branch>
     git worktree add /tmp/pr-review-<number> origin/<branch> --detach
     cd /tmp/pr-review-<number>
     ```
4. Determine the scope of this PR. If the project uses plan files, find the one relevant to this PR by looking within the changed files list from step 2 — do not pick up plan files that are not part of this PR's diff, as there may be unrelated plans from other developers or issues. If no plan file exists, fall back to the PR description, linked issues, and commit messages to understand what this PR is supposed to implement.

## Review Phases

### Phase 1: Automated checks (BLOCKING)

Run the project's standard automated checks in the worktree and record pass/fail. Adapt commands to the project's toolchain and language:

- **Build** — compile or package the project (e.g., `mvn package`, `dotnet build`, `pip install -e .`)
- **Lint / static analysis** — run the project's linter or static analyzer
- **Format check** — verify code formatting compliance
- **Type check** — if the language/toolchain supports it
- **Tests** — run the full test suite (unit + integration where applicable)
- **Schema/contract lint** — if API schema files changed (`.proto`, OpenAPI, GraphQL, etc.), run the relevant linter

Record exit codes and output per step. If build fails, mark all dependent criteria as ❌ (0).

### Phase 2: Coverage per task

For each task in the plan, or each logical change unit in the diff if no plan exists:

1. Identify the modules/packages from the diff. If a plan exists and lists affected files, use that as additional context.
2. Run coverage using the project's toolchain (e.g., `pytest --cov`, `dotnet test --collect:"Code Coverage"`, `mvn test jacoco:report`).
3. Compare against thresholds defined in project documentation. If none are defined, use these as general guidelines (backend/layered architecture oriented — for frontend projects default to **>= 80% overall**):
   - Service / business logic layers — **>= 90%**
   - Handler / controller layers — **>= 85%**
   - Config / infrastructure layers — **>= 80%**
   - Domain / core models — **>= 95%**

### Phase 3: Code quality per task (static analysis)

For each task, read the changed files and evaluate:

1. **Plan compliance** — is the task implemented as described? If a plan exists, check files listed in plan vs actual changes. If no plan, verify the implementation matches the PR description and linked issues.
2. **Standards & CLAUDE.md compliance** — holistic check against project standards:
   - **ADRs**: all applicable Architecture Decision Records followed as documented in the project.
   - **Patterns**: code follows documented patterns (state machines, layering, error wrapping, etc.)
   - **Antipatterns**: no violations from the project's antipattern list.
   - **CLAUDE.md rules**: TDD applied (tests alongside code), conventional commits, atomic commits, no `--amend` on pushed commits, worktree isolation used.
3. **SoC** — does each module/component have one responsibility?
4. **DRY** — is there code/logic duplication?
5. **KISS** — is the solution simple or over-engineered?
6. **Security** — no injection, no secrets in code, boundary validation.
7. **Hardcoded values** — no hardcoded ports, URLs, credentials, or status strings that should live in config/env/constants.
8. **API/Schema contracts** — if API contracts or schema files changed: backward compatible, fields follow conventions.
9. **i18n** (frontend only) — all user-visible text uses the project's i18n mechanism; new keys present in all locale dictionaries.
10. **Event system** (if events added/changed) — channel/topic names follow convention, payload structure matches consumer expectations, no cross-channel leaks.
11. **Observability** (backend/services) — new business-critical code paths have appropriate logging and metrics. Not every function needs instrumentation — only responsibility-bearing paths: failure branches, state transitions, external calls, retry/escalation logic. Silent failures are unacceptable in production paths. Skip if the project is a pure frontend or CLI with no logging infrastructure.

### Phase 4: Trace & process review

1. Find the trace/log file (modified in PR) if the project uses them.
2. Check against the project's trace template:
   - [ ] Has all required sections (e.g., "What was done", "What was learned", "Problems", "Technical decisions", "Tech debt", "Proposals")
   - [ ] Technical decisions are documented with rationale
   - [ ] Tech debt discovered is listed with priority
   - [ ] Proposals section has patterns, antipatterns, lessons
3. If a plan exists, check that the plan progress table shows all tasks as `done` with timestamps.
4. If a plan exists, check plan frontmatter: `status: completed`.
5. Check atomic commits: `git log --oneline <baseRefName>..<branch>` — conventional format?

### Phase 5: Merge-blocking criteria (HARD BLOCKERS)

These checks block merging **when applicable**. If the project does not use a given practice, mark it ➖ N/A. If it exists and fails, the verdict MUST be ❌ regardless of score.

| # | Blocker | Applies when | How to verify | Fail action |
|---|---------|--------------|---------------|-------------|
| B1 | **No E2E / acceptance test conducted** | Project requires E2E testing before merge | Search trace for E2E evidence: deployment, feature walkthrough, lifecycle completion, UI observation | Verdict = ❌, note "E2E test required before merge" |
| B2 | **No trace file** | Project uses trace/log files | No new/modified trace file in PR diff | Verdict = ❌, note "Trace file missing" |
| B3 | **Trace missing required sections** | B2 is applicable and trace file exists | Any required sections absent or empty | Verdict = ❌, note which sections are missing |
| B4 | **Plan progress not updated** | Project uses plan files | Progress table has tasks not marked `✅ done` or missing timestamps | Verdict = ❌, note "Plan progress table incomplete" |
| B5 | **Plan frontmatter not `completed`** | Project uses plan files | `status:` in plan frontmatter is not `completed` | Verdict = ❌, note "Plan status not set to completed" |
| B6 | **Tests fail** | Project has automated tests | Phase 1 automated checks have failures | Verdict = ❌ |

Report all blocker results in a dedicated section of the review (see "Merge Blockers" in report format below).

## Incremental Report Writing

**CRITICAL:** Write the report to `/tmp/pr-review-<number>.md` incrementally as you complete each phase. Do NOT accumulate all data in context and write at the end — this risks context overflow on large PRs.

1. After Phase 1 (automated checks): write the header, summary skeleton, and automated checks table.
2. After Phase 2 (coverage): append coverage details table.
3. After Phase 3 (code quality): append task review matrix and risks.
4. After Phase 4 (trace): append trace review.
5. After Phase 5 (merge blockers): append merge blockers table, footnotes, and verdict.

If context compaction occurs mid-review, re-read the temp file to recover progress.

## Report Format

Write the report to a local temp file first: `/tmp/pr-review-<number>.md`

### Scoring rules

**Score:** 0-10. Icons: ✅ (8-10), ⚠️ (5-7), ❌ (0-4), ➖ (N/A — not applicable to this PR).

**Numeric metrics are mandatory where measurable.** Always include raw numbers alongside the score:
- Tests: `✅ 8 (47/47 pass)`
- Coverage: `⚠️ 6 (82%, threshold 90%)`
- Plan compliance: `✅ 9 (14/15 files match plan)`
- DRY: `⚠️ 5 (3 duplicated fragments)`
- Antipatterns: `✅ 10 (0 violations)`
- Commits: `✅ 9 (8/8 conventional)`
- Trace sections: `⚠️ 6 (5/6 present, missing "Proposals")`

Format: `<icon> <score> (<metric>)`. The metric in parentheses is the evidence.

### Report structure

```markdown
## PR Review: #<number> — <title>

### Summary

<2-3 sentence overall assessment>

**Stats:** N files changed, +X/−Y lines, N commits[, N tasks in plan — if plan exists]

### Automated Checks

| Check | Result | Metric |
|-------|--------|--------|
| Build | ✅/❌ | exit code, N packages/modules |
| Lint / static analysis | ✅/❌ | N warnings, N errors |
| Format check | ✅/❌ | N unformatted files |
| Tests | ✅/❌ | N passed, N failed, N skipped |
| Type check (if applicable) | ✅/❌ | exit code, N errors |
| Schema/contract lint (if schema changed) | ✅/❌ | N issues |

### Task Review Matrix

Rows = criteria, Columns = tasks from the plan (or logical change units from the diff if no plan exists).
Each cell: `<icon> <score> (<metric>)`.

| Criteria | TASK-1 | TASK-2 | ... | TASK-N | Overall |
|----------|--------|--------|-----|--------|---------|
| Plan compliance | | | | | |
| Standards & CLAUDE.md | | | | | |
| Tests pass | | | | | |
| Coverage | | | | | |
| SoC | | | | | |
| DRY | | | | | |
| KISS | | | | | |
| Security | | | | | |
| Hardcoded values | | | | | |
| API/Schema contracts | | | | | |
| i18n | | | | | |
| Event system | | | | | |
| Observability | | | | | |

**Metrics guide per criteria:**

| Criteria | What to measure |
|----------|----------------|
| Plan compliance | N/M files from plan found in diff; N missing items |
| Standards & CLAUDE.md | N ADR violations; N pattern violations; N antipattern hits; N CLAUDE.md rule violations (0 total = perfect) |
| Tests pass | N passed / N total; N new tests added |
| Coverage | XX% (threshold YY%); delta from base branch |
| SoC | N modules with mixed concerns (0 = perfect) |
| DRY | N duplicated code fragments found |
| KISS | N over-engineered abstractions (0 = perfect) |
| Security | N issues (injection, secrets, missing validation) |
| Hardcoded values | N hardcoded ports/URLs/statuses/credentials found (0 = perfect) |
| API/Schema contracts | N breaking changes; N convention violations |
| i18n | N raw strings without i18n wrapper; N missing locale keys (0 = perfect) |
| Event system | N events with wrong channel/structure; N cross-channel leaks (0 = perfect) |
| Observability | N critical paths without logging; N state-changing operations without metrics; N silent error swallows (0 = perfect) |

### Risks

#### Mandatory checks (M1-M5 always, M6+ agent adds)

M1-M5 MUST be evaluated on every PR. For each, write a verdict (➖ N/A, ✅ OK, ⚠️ or ❌ with details). Skip only if the PR has zero relevance (e.g., docs-only PR → skip all).

**After evaluating M1-M5, the reviewer MUST add their own checks (M6, M7, ...) based on what they see in the diff.** Think about what could go wrong with THIS specific PR. The list below is a starting point, not a ceiling.

| # | Check | When relevant | What to verify |
|---|-------|---------------|----------------|
| M1 | **Inter-service / inter-module contracts** | Any change to shared APIs, schema files, or domain types | Do existing callers still work? Are new fields optional / backward-compatible? Are shared types changed without updating all consumers? |
| M2 | **Frontend i18n** | Any frontend change that adds or modifies user-visible text | All labels, placeholders, error messages, and headings use the i18n mechanism. Every new key has entries in all locale files. No raw hardcoded strings in JSX/templates. |
| M3 | **Event system** | Any change that publishes or subscribes to events | Event channel/topic names follow convention. Payload structure matches consumer expectations. No cross-channel leaks. |
| M4 | **Hardcoded values in code** | Any new or modified service code | No hardcoded ports, hostnames, timeouts, URLs, credentials, retry counts, or status strings that should live in config/env/constants. |
| M5 | **New tech debt introduced** | Every PR | Does this PR introduce things that will need to be revisited? For each item found, state what exactly became debt, why (conscious trade-off vs oversight), and suggested priority (High/Medium/Low). If none found — write "✅ No new tech debt." |
| M6 | **Observability gaps** | Any new service/handler/domain logic | New business-critical paths must have appropriate logging and metrics. Silent error swallows in production paths are ❌. |

**M5 — what to look for:**
- Leftover smoke/debug scripts not tied to any Makefile/task-runner target
- `TODO`, `FIXME`, `HACK`, `XXX` comments added in the diff
- Partial implementations: function stubs, empty interface methods, feature flags that are always on/off
- Missing error handling that was skipped "for now"
- Tests marked as skipped or commented out
- Copied code instead of extracting shared utility (intentional "we'll refactor later")
- Missing metrics/logging for new code paths that should be observable
- Schema or API fields added but unused (reserved for future)
- Workarounds for upstream bugs with no tracking issue linked
- Known limitations documented in code/trace but not tracked anywhere actionable
- Stale configuration: env vars, config fields, compose settings, CLI flags, or constants no longer read after this PR — or new code that stopped using previously required config without cleaning it up

**Common agent-added checks (add as M6, M7, ... when applicable):**

| Candidate | When to add | What to verify |
|-----------|-------------|----------------|
| **DB migration safety** | New or altered migrations | Reversible? Locks on large tables? Data loss on rollback? Column renames vs add+drop? |
| **Race conditions / concurrency** | Shared state, threads, DB transactions | Missing lock? SELECT-then-UPDATE without row lock? Concurrent collection access? |
| **Error handling & observability** | New service/handler code | Are errors wrapped with context? Logged at correct level? Returned to caller with proper codes? Metrics incremented on failure paths? |
| **Docker / Compose changes** | Dockerfile, docker-compose, env files | Image size regression? Missing health checks? Env vars documented? Volume mounts correct? |
| **State machine transitions** | Lifecycle state changes | Valid transitions per documented state diagram? Guards present? Invalid transitions rejected? |
| **Backward-incompatible config** | New env vars, config changes | Are new vars optional with defaults? Will existing deployments break without config update? |
| **SQL injection / input validation** | New queries, user-facing endpoints | Parameterized queries? Input sanitized at boundary? |
| **Resource leaks** | New connections, threads, file handles, timers | Proper cleanup/dispose/close? Context/cancellation respected? Long-running tasks have exit path? |
| **Test quality** | New or modified tests | Do tests actually assert behavior (not just "no error")? Edge cases covered? Mocks verify interactions? |

The reviewer should not blindly add all candidates — only those relevant to the specific PR. But if the PR touches migrations, there MUST be a migration safety check. If it touches concurrency, there MUST be a concurrency check. Etc.

#### Mandatory Risk Checks

| # | Verdict | Details |
|---|---------|---------|
| M1 Inter-service contracts | ➖ N/A / ✅ OK / ⚠️ / ❌ | <explanation> |
| M2 Frontend i18n | ➖ N/A / ✅ OK / ⚠️ / ❌ | <explanation> |
| M3 Event system | ➖ N/A / ✅ OK / ⚠️ / ❌ | <explanation> |
| M4 Hardcoded values | ➖ N/A / ✅ OK / ⚠️ / ❌ | <explanation> |
| M5 New tech debt | ✅ None / ⚠️ N items | <list each item: what, why, priority> |
| M6 <agent-added> | ✅ OK / ⚠️ / ❌ | <explanation> |
| ... | | |

#### Additional risks

Beyond the mandatory checks, identify other risks introduced or exposed by this PR:
- Are there obvious gaps between the intended scope (plan, PR description, or linked issues) and actual implementation?
- Could this change cause regressions in other services/modules?
- Are there deployment ordering dependencies (must deploy X before Y)?
- Does the change degrade performance (N+1 queries, missing indexes, large payloads)?

| Risk | Severity | Task | Mitigation |
|------|----------|------|------------|
| Description of risk | High/Medium/Low | TASK-X | How it's mitigated or what's needed |
| ... | | | |

If no additional risks identified — write "None identified."

### Coverage Details

| Module / Layer | Coverage | Threshold | Delta | Status |
|----------------|----------|-----------|-------|--------|
| `<path>` | XX% | YY% | +Z% | ✅/❌ |
| ... | | | | |
| **Total** | **XX%** | | | |

### Trace Review

| Criteria | Score | Metric |
|----------|-------|--------|
| Sections present | /10 | N/N required sections |
| Technical decisions | /10 | N decisions documented |
| Tech debt listed | /10 | N items with priority |
| Proposals | /10 | N proposals (patterns/antipatterns/lessons) |
| E2E evidence | /10 | Y/N deployment mention, N smoke tests referenced |
| Plan progress | /10 | N/M tasks marked done (➖ if no plan) |
| Atomic commits | /10 | N/N conventional; N non-conventional |

### Footnotes

For every ⚠️ or ❌ in the matrix, provide a numbered footnote. Use plain markdown numbered list:

1. **TASK-X / Criteria:** explanation of the issue and suggested fix.
2. **TASK-Y / Criteria:** ...

### Merge Blockers

Hard blockers that override the score. Mark each as ✅, ❌, or ➖ N/A based on whether the practice applies to this project. If any applicable blocker fails, verdict is ❌ regardless of score.

| # | Blocker | Status | Details |
|---|---------|--------|---------|
| B1 | E2E / acceptance test conducted | ✅/❌/➖ | <evidence in trace, or "no evidence found", or "N/A — not required by project"> |
| B2 | Trace file present | ✅/❌/➖ | <path or "missing", or "N/A — project does not use trace files"> |
| B3 | Trace sections complete | ✅/❌/➖ | <N/N required sections present, or "N/A"> |
| B4 | Plan progress updated | ✅/❌/➖ | <N/M tasks with ✅ and timestamps, or "N/A — no plan"> |
| B5 | Plan status = completed | ✅/❌/➖ | <current status value, or "N/A — no plan"> |
| B6 | Tests pass | ✅/❌/➖ | <from Phase 1, or "N/A — no automated tests"> |

**Applicable blockers passed: N/N** — if any applicable blocker fails, verdict is ❌ MERGE BLOCKED.

### Verdict

**Overall score: X.X/10** (weighted: automated checks 30%, task matrix 50%, trace/process 20% — if a category is N/A, distribute its weight proportionally across the remaining applicable categories)

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Automated checks | X/10 | 30% | X.X |
| Task review matrix | X/10 | 50% | X.X |
| Trace & process | X/10 or ➖ | 20% | X.X |

- ✅ **Ready to merge** (8.0-10.0, all blockers passed)
- ⚠️ **Needs minor fixes** (5.0-7.9, all blockers passed) — list top 3 issues
- ❌ **Needs significant work** (0-4.9, OR any blocker failed) — list blocking issues
```

## Publishing

1. Post the report as a PR comment:
   ```bash
   gh pr comment <number> --body-file /tmp/pr-review-<number>.md
   ```
2. Delete the temp file:
   ```bash
   rm /tmp/pr-review-<number>.md
   ```
3. If a temp worktree was created, remove it:
   ```bash
   git worktree remove /tmp/pr-review-<number> --force
   ```

## Output

Return to user:
1. Overall verdict (score + recommendation)
2. Link to the PR comment
3. Summary of critical issues (if any)

## Parallelization

Use subagents where possible:
- **Test suites** — run independent test suites in parallel (e.g., different services, packages, or layers)
- **Per-task code review** — can be parallelized across tasks
- **Trace review** — independent, can run in parallel with code review

## After context compaction

Re-read:
1. Project architecture/standards documentation — patterns, antipatterns
2. The plan file — task list and expected implementation (if plan exists)
3. The temp report file — what you've already reviewed
