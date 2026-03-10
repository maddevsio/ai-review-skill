# PR Review Skills

Claude Code skills for reviewing pull/merge requests on GitHub, Bitbucket, and GitLab. Each platform variant fetches the diff, annotates it with line numbers, runs a multi-phase code review, lets you moderate comments one by one, and posts the result back to the platform.

---

## GitHub

### Prerequisites

- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated (`gh auth login`)
- Python 3

### Installation

Copy the skill and scripts into your project's `.claude` directory:

```bash
mkdir -p .claude/skills/pr-review/scripts
cp /path/to/Github/SKILL.md .claude/skills/pr-review/SKILL.md
cp /path/to/Github/scripts/* .claude/skills/pr-review/scripts/
```

### Usage

```
/pr-review 123
/pr-review https://github.com/org/repo/pull/123
/pr-review          # lists open PRs and asks you to pick one
```

### Quirks

- **`gh` must be authenticated.** If `gh auth status` shows no account, run `gh auth login` first. If `gh` is not authenticated, the skill will stop immediately with a clear message from the CLI: `To get started with GitHub CLI, please run: gh auth login`.
- **Skill files must live at exactly `.claude/skills/pr-review/`.** The `allowed-tools` in SKILL.md are path-locked to `Bash(python3 .claude/skills/pr-review/scripts/*)`. If you put them elsewhere, Claude will not have permission to run them.
- **`REQUEST_CHANGES` on GitHub submits a formal review** that blocks merging when branch protection is enabled. If you just want to leave comments without a blocking verdict, choose "Post comments only" during moderation.

---

## Bitbucket

### Prerequisites

- Python 3
- An Atlassian **API token**

### Installation

Copy the skill and scripts:

```bash
mkdir -p .claude/skills/pr-review/scripts
cp /path/to/Bitbucket/SKILL.md .claude/skills/pr-review/SKILL.md
cp /path/to/Bitbucket/scripts/* .claude/skills/pr-review/scripts/
```

### Getting an API token

1. Go to [id.atlassian.com](https://id.atlassian.com/manage-profile/) → **Security** → **API tokens** → **Create and manage API tokens**
2. Create a new token with these scopes:
   - `read:pullrequest:bitbucket`
   - `read:repository:bitbucket`
   - `write:pullrequest:bitbucket`
   - `write:repository:bitbucket`
3. Copy the generated token — it is shown only once.

### Credentials setup

Run the setup script from your project root (the directory that contains `.claude/`):

```bash
python3 .claude/skills/pr-review/scripts/setup.py
```

This creates `.claude/settings.local.json` with placeholder values. Open it and fill in:

```json
{
  "env": {
    "BITBUCKET_USER": "<your-bitbucket-account-email>",
    "BITBUCKET_TOKEN": "<your-api-token>"
  }
}
```

Then **restart Claude Code** to load the new environment variables.

### Usage

```
/pr-review 123
/pr-review https://bitbucket.org/workspace/repo/pull-requests/123
/pr-review          # lists open PRs and asks you to pick one
```

### Quirks

- **`BITBUCKET_USER` is your email address**, not your display name or Bitbucket username (e.g., `you@example.com`, not `myhandle`). Using the wrong value causes 401 errors.
- **Restart is required after editing `settings.local.json`.** Claude Code reads environment variables at startup. If you edit the file while Claude is running, the new values will not be picked up until you restart.
- **The credential check runs automatically** at the start of every `/pr-review` invocation. If the environment variables are set but contain placeholder text (e.g., `<your-api-token>`), the check will pass but API calls will return 401. Replace placeholders with real values.
- **Skill files must live at exactly `.claude/skills/pr-review/`** — same path-lock constraint as the GitHub variant.

---

## GitLab

### Prerequisites

- Python 3
- A GitLab **Personal Access Token** with `api` scope

### Installation

Copy the skill and scripts. Note that the GitLab skill is named `mr-review` (not `pr-review`):

```bash
mkdir -p .claude/skills/mr-review/scripts
cp /path/to/Gitlab/SKILL.md .claude/skills/mr-review/SKILL.md
cp /path/to/Gitlab/scripts/* .claude/skills/mr-review/scripts/
```

### Getting a Personal Access Token

1. Go to [gitlab.com/-/user_settings/profile](https://gitlab.com/-/user_settings/profile) → **Access** → **Personal access tokens** → **Add new token**
2. Select scope: `api`
3. Set an expiration date if your organization requires it.

### Credentials setup

Run the setup script from your project root:

```bash
python3 .claude/skills/mr-review/scripts/setup.py
```

Open the generated `.claude/settings.local.json` and fill in:

```json
{
  "env": {
    "GITLAB_TOKEN": "<your-personal-access-token>"
  }
}
```

Then **restart Claude Code**.

### Usage

```
/mr-review 42
/mr-review https://gitlab.com/namespace/repo/-/merge_requests/42
/mr-review          # lists open MRs and asks you to pick one
```

Self-hosted GitLab is supported. The `detect-repo.py` script reads your git remote URL and extracts the host automatically — no additional configuration needed.

### Quirks

- **Token scope must be `api`, not `read_api`.** The `read_api` scope is read-only and cannot post comments or approve MRs. Using it causes 403 errors when posting. This is the most common setup mistake.
- **"Request changes" is not a native GitLab API feature.** Selecting "Request changes" during moderation will post all inline comments and add a general note saying changes are requested — but the MR will not enter a formal "changes requested" state as it would on GitHub. GitLab's approval/unapproval model works differently. If you need to block merging, use merge request approval rules on the GitLab project settings side.
- **Restart is required after editing `settings.local.json`** — same as Bitbucket.
- **The credential check runs at the start of every `/mr-review` invocation.** If the token key is present in the file but was not loaded (i.e., you edited the file without restarting), the check script prints: `Keys are in settings.local.json but not loaded — did you restart Claude Code?`
- **`settings.local.json` is per-project.** It lives in the project's `.claude/` directory, not globally. Each project you want to review needs its own credentials configured there.
- **The GitLab diff is reconstructed from the API**, not fetched as a native unified diff. For very large MRs, GitLab may truncate individual file diffs in its API response. If a file appears in the changed files list but comments on it fail to land at the right line, this is likely the cause — check the raw diff in `/tmp/pr-diff-raw-<number>.txt`.
- **Skill files must live at exactly `.claude/skills/mr-review/`** — the allowed-tools are path-locked to that directory.
- **An extra temp file is used (`/tmp/pr-meta-<number>.json`)** to carry diff refs between `get-mr.py` and `post-comments.py`. This file is cleaned up automatically at the end of a successful run, but if the skill is interrupted mid-way (e.g., you cancel), it may be left behind. It is safe to delete manually.
