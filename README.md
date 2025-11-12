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

Create a `.dux.yml` defining how to bootstrap each worktree:

```bash
dux init \
  --env .env.local \
  --install "pnpm install" \
  --run "pnpm dev" \
  --port 3000
```

Resulting `.dux.yml`:

```yaml
env: .env.local      # Path to env file to copy into each worktree
install: pnpm install # Command to install dependencies
run: pnpm dev        # Command to start dev server (for reference)
port: 3000           # Base port for automatic allocation
```

**Note:** The `.dux.yml` file should be committed to your repo so all team members use the same configuration.

### 2 — Create a worktree for an existing issue

```bash
dux create 342 --code
```

This will create a worktree for GitHub issue #342.

### 3 — Or start a new issue + worktree

```bash
dux create --new "Refactor parser module" --code
```

This will create a new GitHub issue and immediately set up a worktree for it.

**What happens when you create a worktree:**

1. Creates a branch named `issue/<number>-<slugified-title>` (e.g., `issue/342-refactor-parser-module`)
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

**Note:** If a worktree already exists for an issue, simply `cd` into the existing directory. Running `dux create` again for the same issue may cause conflicts.

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

Generate a `.dux.yml` configuration file in your repo root.

**Flags:**
* `--env <path>` — Path to env file to copy (default: `.env.local`)
* `--install <cmd>` — Dependency install command (default: `pnpm install`)
* `--run <cmd>` — Dev server command (default: `pnpm dev`)
* `--port <number>` — Base port for allocation (default: `3000`)
* `--force` — Overwrite existing `.dux.yml`

**Example:**
```bash
dux init --env .env --install "npm ci" --run "npm start" --port 4000
```

### `dux create`

Create a worktree for an existing GitHub issue or create a new issue.

**Usage:**
```bash
dux create [ISSUE#]              # Use existing issue
dux create --new "Issue title"   # Create new issue
```

**Flags:**
* `--code` — Open worktree in VS Code after creation
* `--claude` — Open Claude Code in tmux session with issue description
* `--codex` — Open Codex in tmux session with issue description
* `--droid` — Open Droid (Factory AI) in tmux session with issue description
* `--run` — Start dev server after setup
* `--ready` — Mark PR as ready for review (instead of draft)
* `--no-bootstrap` — Skip `.dux.yml` setup (don't install deps or copy env)
* `--base <branch>` — Override the detected default branch

**Example:**
```bash
dux create 42 --claude           # Opens Claude Code in tmux
dux create 42 --droid            # Opens Droid (Factory AI) in tmux
dux create 42 --code --ready     # Opens VS Code, marks PR ready
dux create --new "Add dark mode" --claude
```

Factory AI Droid CLI can be installed via:

```bash
curl -fsSL https://app.factory.ai/cli | sh
```

### `dux status`

List all worktrees with their PR status, cleanliness, assigned ports, and active tmux sessions.

**Example output:**
```
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
dux init --install "npm ci" --run "npm start" --port 4000
# Creates .dux.yml in repo root
```

**Start working on an issue:**
```bash
# Create worktree for existing issue #123
dux create 123 --code

# Or create a new issue and worktree
dux create --new "Add OAuth login" --code
```

**Work in isolation:**
```bash
# Navigate to worktree (VS Code already opened if you used --code)
cd .wt/issue/123-add-oauth-login

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
# Shows:
# - Which worktrees exist
# - Their PR states (draft/open/merged)
# - Assigned ports
# - Whether working directory is clean
```

**After PR is merged:**
```bash
dux clean
# Automatically removes merged worktrees and branches
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
- Uses `droid exec --auto medium --skip-permissions-unsafe` for autonomous operation
- Installation: `curl -fsSL https://app.factory.ai/cli | sh`
- Documentation: [Factory AI Droid CLI](https://docs.factory.ai/cli/droid-exec/overview)

### Examples

**Single issue with AI assistant:**
```bash
dux create 123 --claude          # Opens Claude Code
dux create 123 --codex           # Opens Codex
dux create 123 --droid           # Opens Droid (Factory AI)
```

**Multiple issues with AI assistant:**
```bash
dux create 123,124,125 --claude  # Opens all in one tmux session with separate windows
```

**Combine with other flags:**
```bash
dux create 123 --droid --code    # Opens both Droid in tmux AND VS Code
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
