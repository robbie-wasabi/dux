# dux

A lightweight CLI that turns **GitHub issues into Git worktrees**.
Each issue becomes its own branch, directory, and environment with an automatically assigned port and optional VS Code session — making parallel development effortless.

---

## Features

* Create a worktree directly from a GitHub issue (or open a new issue on the fly).
* Automatically link a **draft PR** to the issue.
* Copy and customize a `.env` file for each worktree.
* Auto-assign a **unique free port** with no central registry.
* Install dependencies and run setup commands per-repo using a minimal `.dux.yml`.
* Pipe the issue context into Claude Code, Codex, or Factory AI Droid right from `dux create`.
* Clean up merged branches and worktrees automatically.
* No global state, no daemon — just pure Git + GitHub CLI.

---

## Why Use dux?

**Problem:** Working on multiple issues simultaneously means constantly switching branches, managing port conflicts, and losing context between tasks.

**Solution:** dux gives each issue its own isolated workspace:

- **Work on multiple issues in parallel** without branch switching
- **No port conflicts** — each worktree gets a unique port automatically
- **Run multiple dev servers** simultaneously for different features
- **Instant context switching** — just `cd` to a different worktree
- **Automatic PR linking** — draft PRs created and linked to issues
- **Zero configuration overhead** — one `.dux.yml` per repo

**Perfect for:**
- Teams working on multiple features simultaneously
- Reviewing PRs while keeping your main work intact
- Testing fixes without disrupting your current work
- Hotfixes that need immediate attention
- Comparing implementations side-by-side

---

## Installation

### Option 1 — Install via `pip` (recommended)

Clone or download the repo, then run:

```bash
pip install .
```

To install in editable (dev) mode:

```bash
pip install -e .
```

This installs the `dux` executable globally (usually in `~/.local/bin`).

### Option 2 — Manual install

```bash
chmod +x dux.py
sudo mv dux.py /usr/local/bin/dux
```

### Requirements

* Python ≥ 3.9
* `git`
* `gh` (GitHub CLI, authenticated via `gh auth login`)
* `tmux` (terminal multiplexer for session management)

---

## Quick Start

### 1 — Initialize the repo

Scaffold a `.dux.yml` template and then edit it to match your project:

```bash
dux init
```

Example configuration:

```yaml
env: .env.local      # Path to env file to copy into each worktree
install: pnpm install # Command to install dependencies
run: pnpm dev        # Command to start dev server (for reference)
port: 3000           # Base port for automatic allocation
```

**Tip:** Use `dux init --force` to overwrite an existing template if you need to regenerate it. Commit `.dux.yml` so the whole team shares the same bootstrap settings.

### 2 — Create a worktree for an existing issue

```bash
dux create "Investigate login redirect" --issue 342 --code
# or simply
dux create --issue 342 --code
```

When no context string is provided alongside `--issue`, dux reuses the issue title (up to the first five words) to name the branch/worktree and seed prompts automatically.

### 3 — Or start a new issue + worktree

```bash
dux create "Refactor parser module" --new "Refactor parser module" --code
```

This creates a new GitHub issue with the given title and immediately sets up a worktree for it.

**What happens when you create a worktree:**

1. Creates a branch named `issue/<number>-<slugified-title>` using the first five words of the issue title (e.g., `issue/342-refactor-parser-module`)
2. Adds a worktree under `.wt/issue/<number>-<slugified-title>`
3. Copies your `.env` file (e.g., `.env.local`) into the worktree
4. Assigns a unique free port (e.g., `PORT=3001`) based on branch name hash
5. Runs the install command from `.dux.yml` (e.g., `pnpm install`)
6. Creates (or reuses) a draft PR linked to the issue
7. Opens the worktree in VS Code (if `--code` flag is used)

### 4 — Working with your worktree

After creating a worktree, you can navigate to it and work independently:

```bash
# Navigate to the worktree directory
cd .wt/issue/342-refactor-parser-module

# The worktree has its own .env file with a unique PORT
cat .env.local  # Shows PORT=3001 (or similar)

# Start your dev server (uses the assigned port)
pnpm dev

# Make changes, commit, and push as normal
git add .
git commit -m "Implement parser refactor"
git push
```

Each worktree is completely isolated:
- Independent working directory
- Own `.env` file with unique port
- Separate git index (can commit/switch branches independently)
- Own dependencies (if installed separately)

When you're done, simply merge your PR and run `dux clean` to remove the worktree.

**Note:** If a worktree already exists for an issue, simply `cd` into the existing directory. Running `dux create` with the same `--issue` will reconnect you to the existing worktree instead of creating a duplicate.

---

## Port Allocation

**dux** allocates ports automatically without any central registry or state files.

**How it works:**
1. Takes the base port from `.dux.yml` (e.g., `3000`)
2. Hashes the branch name to get a deterministic offset
3. Probes for available ports starting from `base_port + offset`
4. Assigns the first free port found

**Port persistence:**
Each worktree stores its assigned port in two places:
* Git worktree config: `git config --worktree issuewt.port <PORT>`
* Environment file: `PORT=<PORT>` in your `.env` file

**View all worktrees and their ports:**

```bash
dux status
```

This shows each worktree's branch, PR status, cleanliness, and assigned port.

---

## Commands

### `dux init`

Generate a `.dux.yml` template in your repo root. Edit the file after generation to set `env`, `install`, `run`, and `port` values for your project.

**Flags:**
* `--force` — Overwrite an existing `.dux.yml`

**Example:**
```bash
dux init
```

### `dux create`

Create a worktree from contextual instructions, optionally linking to GitHub issues.

**Usage:**
```bash
dux create "Quick summary of the work" --issue 123          # Link to existing issue(s)
dux create "Exploratory spike" --new "Spike: try new API"   # Open a new issue first
dux create "Scratch notes for pairing session"              # Context-only worktree
```

If you omit the leading context when using `--issue` or `--new`, dux automatically reuses the issue title (up to five words) for naming and prompts.

**Flags:**
* `--issue <numbers>` — Link one or more issue numbers (comma-separated)
* `--new <title>` — Create a new GitHub issue with the provided title
* `--base <branch>` — Override the detected default branch
* `--ready` — Mark PR as ready for review instead of draft
* `--code` — Open worktree in VS Code after creation
* `--claude` — Open Claude Code in tmux session with issue description
* `--codex` — Open Codex in tmux session with issue description
* `--droid` — Open Droid (Factory AI) in tmux session with issue description
* `--run` — Start dev server after setup
* `--no-bootstrap` — Skip `.dux.yml` setup (don't install deps or copy env)
* `--start` — Automatically trigger the selected coding assistant inside tmux

**Example:**
```bash
dux create "Investigate 500 on login" --issue 42 --claude
dux create "Pay down tech debt" --issue 104,105 --droid --start
dux create "Draft accessibility audit" --new "Accessibility audit" --code --ready
dux create "Pairing scratchpad"  # No GitHub issue, just a dedicated worktree
```

Factory AI Droid CLI can be installed via:

```bash
curl -fsSL https://app.factory.ai/cli | sh
```

### `dux status`

List all worktrees with their PR status, cleanliness, assigned ports, and active tmux sessions.

**Example output:**
```bash
issue/342-refactor-parser  clean  DRAFT    3001 tmux https://github.com/...
  /path/to/repo/.wt/issue/342-refactor-parser
```

**Columns:** `<branch> <dirty/clean> <PR state> <port> <tmux session> <PR URL>`

### `dux clean`

Remove worktrees and branches for PRs that have been merged.

**Example:**
```bash
dux clean  # Removes all merged worktrees
```

### `dux view`

Open the current branch's GitHub PR in your default browser.

**Usage:**
```bash
dux view  # Runs from anywhere inside the repo
```

If no PR exists for the current branch, a helpful error is displayed so you can create one with `gh pr create` or `dux create`.

---

## Example Workflow

**First time setup:**
```bash
cd my-repo
dux init
# Edit .dux.yml to set env/install/run/port
```

**Start working on an issue:**
```bash
# Create worktree for existing issue #123
dux create "Investigate payment failure" --issue 123 --code

# Or create a new issue and worktree
dux create "Plan OAuth rollout" --new "Add OAuth login" --code

# Or spin up scratch work without a GitHub issue
dux create "Prototype new dashboard layout"
```

**Work in isolation:**
```bash
# Navigate to worktree (VS Code already opened if you used --code)
cd .wt/issue/123-investigate-payment-failure

# Your dev server runs on its own port (e.g., PORT=4001)
npm start

# Make changes, commit, push
git add .
git commit -m "Implement OAuth provider"
git push
```

**Check status of all worktrees:**
```bash
dux status
```

**After PR is merged:**
```bash
dux clean
```

---

## AI Assistant Integration

**dux** integrates with multiple AI coding assistants to help you work on issues. When you use the assistant flags (`--claude`, `--codex`, or `--droid`), dux will:

1. Create a `.dux_issue.txt` file in the worktree with the full issue description
2. Open a tmux session with the AI assistant
3. Pass the issue description to the assistant for autonomous work

### Supported Assistants

**Claude Code** (`--claude`)
- Uses `claude --dangerously-skip-permissions` for autonomous operation
- Installation: Follow instructions at [Claude Code](https://docs.claude.com/en/docs/claude-code)

**Codex** (`--codex`)
- Uses `codex --dangerously-bypass-approvals-and-sandbox` for autonomous operation
- Installation: Follow instructions at [Codex](https://github.com/codex-ai/codex)

**Droid (Factory AI)** (`--droid`)
- Uses `droid exec --skip-permissions-unsafe` for autonomous operation
- Installation: `curl -fsSL https://app.factory.ai/cli | sh`
- Documentation: [Factory AI Droid CLI](https://docs.factory.ai/cli/droid-exec/overview)

### Examples

**Single issue with AI assistant:**
```bash
dux create "Triage flaky e2e test" --issue 123 --claude
dux create "Review architecture doc" --issue 123 --codex
dux create "Debug websocket reconnect" --issue 123 --droid
```

**Multiple issues with AI assistant:**
```bash
dux create "Prep release" --issue 123,124,125 --claude
```

**Combine with other flags:**
```bash
dux create "Hardening sprint" --issue 123 --droid --code --start
```

---

## Uninstallation

If installed via pip:

```bash
pip uninstall dux
```

---

## Development

To contribute or modify locally:

```bash
git clone <repo-url>
cd dux
pip install -e .
```

---

## tmux Session Management

**dux** uses tmux to create isolated development sessions for each worktree. Each session is named after the branch (e.g., `issue/89-task-create-global-404-page`).

### Common tmux Commands

**Detach from session** (keep it running in background):
```bash
Ctrl+b, then d
```

**List all sessions:**
```bash
tmux ls
```

**Attach to existing session:**
```bash
tmux attach -t issue/89-task-create-global-404-page
```

**Kill a session:**
```bash
tmux kill-session -t issue/89-task-create-global-404-page
```

**Switch between sessions** (while inside tmux):
```bash
Ctrl+b, then s  # Shows session list
```

### Installing tmux

**macOS:**
```bash
brew install tmux
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tmux
```

**Other Linux:**
```bash
# Most package managers have tmux
sudo yum install tmux  # RHEL/CentOS
```

### tmux Tips

- Each tmux session persists even if you close your terminal
- You can have multiple windows and panes within a session
- `Ctrl+b, ?` shows all tmux keybindings
- Sessions are automatically isolated per worktree/branch

---

## Troubleshooting

### `gh` command not found
Make sure GitHub CLI is installed and authenticated:
```bash
brew install gh        # macOS
gh auth login          # Authenticate
```

### Port already in use
The port allocation algorithm probes for free ports automatically. If you see this error:
- Check what's running on that port: `lsof -i :<PORT>`
- Increase the port span in the code or choose a different base port in `.dux.yml`

### Worktree already exists
If you try to create a worktree that already exists, use `dux status` to see existing worktrees and simply `cd` into the directory.

### `.env` file not copied
Make sure:
1. The `.env` file path in `.dux.yml` is correct
2. The file exists in your repo root
3. You're not using `--no-bootstrap`

### PR not created automatically
Check that:
1. You're authenticated with `gh auth status`
2. You have push permissions to the repo
3. The branch was pushed successfully

### How do I delete a worktree manually?
```bash
git worktree remove .wt/issue/<branch-name>
git branch -D issue/<branch-name>
```

---

## License

MIT — do anything, just don't remove the credit.
