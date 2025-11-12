# Overwrite issue_wt.py to add stateless port allocation via per-worktree config + env scanning
import os
import re
import json
import argparse
import shutil
import shlex
import socket
import subprocess
from pathlib import Path

# ----------------
# ASCII Art
# ----------------

DUCK_ART = r"""
       _
     >(o )___
      ( ._> /
       `---'
"""

# ----------------
# Utilities
# ----------------

def run(cmd, cwd=None, check=True, capture=True):
    """Run a command (list form). Returns stdout when capture=True."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )
    if capture:
        return result.stdout.strip()
    return ""

def sh(cmd, cwd=None, check=True):
    """Run a shell string (uses /bin/sh)."""
    return subprocess.run(cmd, cwd=cwd, shell=True, check=check)

def require(bin_name):
    if shutil.which(bin_name) is None:
        raise SystemExit(f"Missing dependency: {bin_name} not found on PATH")


def repo_root():
    return run(["git", "rev-parse", "--show-toplevel"])


def get_default_branch() -> str:
    """Detect repo default branch from origin/HEAD or current branch."""
    # Try origin/HEAD first
    try:
        ref = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
        return ref.split("/")[-1]
    except Exception:
        pass

    # Try current branch
    try:
        current = run(["git", "branch", "--show-current"])
        if current:
            return current
    except Exception:
        pass

    # Check which common default branches exist on remote
    try:
        remote_branches = run(["git", "branch", "-r"])
        for candidate in ["dev", "develop", "main", "master"]:
            if f"origin/{candidate}" in remote_branches:
                return candidate
    except Exception:
        pass

    return "main"


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s or "work"


def ensure_base_up_to_date(base_branch: str):
    try:
        run(["git", "fetch", "origin", base_branch])
    except subprocess.CalledProcessError:
        # If fetch fails, branch might not exist on remote, just continue
        print(f"Warning: Could not fetch {base_branch} from origin")


def worktree_dir(root: str, branch: str) -> str:
    return str(Path(root) / ".wt" / branch)


def branch_exists(root: str, branch: str) -> bool:
    try:
        run(["git", "rev-parse", "--verify", branch], cwd=root)
        return True
    except subprocess.CalledProcessError:
        return False


def derive_context_branch(root: str, context: str, prefix: str = "work", word_limit: int = 5) -> str:
    words = context.strip().split()
    snippet = " ".join(words[:word_limit]) if words else ""
    slug = slugify(snippet)
    if not slug:
        slug = "work"

    base_branch = f"{prefix}/{slug}"
    candidate = base_branch
    suffix = 2
    while branch_exists(root, candidate) or Path(worktree_dir(root, candidate)).exists():
        candidate = f"{base_branch}-{suffix}"
        suffix += 1

    return candidate


def git_worktree_add(root: str, branch: str, dir_path: str, base_branch: str):
    Path(dir_path).parent.mkdir(parents=True, exist_ok=True)
    # Check if branch already exists locally
    try:
        run(["git", "rev-parse", "--verify", branch], cwd=root)
        branch_exists = True
    except subprocess.CalledProcessError:
        branch_exists = False

    if branch_exists:
        # Branch exists, just add worktree without forcing branch creation
        run(["git", "worktree", "add", dir_path, branch], cwd=root)
    else:
        # Branch doesn't exist, create it from base branch
        run(["git", "worktree", "add", "-b", branch, dir_path, f"origin/{base_branch}"], cwd=root)


def push_set_upstream(dir_path: str, branch: str):
    try:
        run(["git", "push", "-u", "origin", branch], cwd=dir_path)
    except subprocess.CalledProcessError:
        pass


def empty_commit_if_needed(dir_path: str, message: str):
    try:
        upstream = run(["git", "rev-parse", "@{upstream}"], cwd=dir_path)
        ahead = run(["git", "rev-list", "--count", f"{upstream}..HEAD"], cwd=dir_path)
        if ahead == "0":
            run(["git", "commit", "--allow-empty", "-m", message], cwd=dir_path)
            run(["git", "push"], cwd=dir_path)
    except Exception:
        pass


def gh_issue_create(title: str, body: str):
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    out = run(["gh", "issue", "create", "--title", title, "--body", body, "--json", "number,title,url,body"])  # noqa: E231
    return json.loads(out)


def gh_issue_view(number: str):
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    out = run(["gh", "issue", "view", str(number), "--json", "number,title,url,body"])  # noqa: E231
    return json.loads(out)


def gh_pr_view_by_head(branch: str):
    try:
        out = run(["gh", "pr", "view", "--head", branch, "--json", "url,state"])  # noqa: E231
        return json.loads(out)
    except subprocess.CalledProcessError:
        return None


def gh_pr_create(base_branch: str, head_branch: str, title: str, body: str, draft=True):
    args = ["gh", "pr", "create", "--base", base_branch, "--head", head_branch, "--title", title, "--body", body]
    if draft:
        args.append("--draft")
    out = run(args + ["--json", "url,state"])  # noqa: E231
    return json.loads(out)


def open_in_code(dir_path: str):
    if shutil.which("code"):
        try:
            run(["code", "-n", dir_path])
        except Exception:
            pass

def open_in_tmux(dir_path: str, session_name: str, command: str = None):
    """Open or attach to tmux session for worktree."""
    # Check if session already exists
    try:
        sessions_output = run(["tmux", "list-sessions", "-F", "#{session_name}"], check=False, capture=True)
        existing_sessions = sessions_output.split('\n') if sessions_output else []
    except subprocess.CalledProcessError:
        existing_sessions = []

    if session_name in existing_sessions:
        print(f"Error: tmux session '{session_name}' already exists")
        print(f"To attach: tmux attach -t {shlex.quote(session_name)}")
        print(f"To kill:   tmux kill-session -t {shlex.quote(session_name)}")
        return

    # Create new tmux session
    print(f"Creating tmux session: {session_name}")

    # Start new detached session
    run(["tmux", "new-session", "-d", "-s", session_name, "-c", dir_path], check=True)

    # Send command if provided
    if command:
        run(["tmux", "send-keys", "-t", session_name, command, "C-m"], check=True)

    # Attach to session (or switch if already in tmux)
    if os.environ.get("TMUX"):
        # Already inside tmux, switch client
        print(f"Switching to tmux session: {session_name}")
        run(["tmux", "switch-client", "-t", session_name], check=True)
    else:
        # Outside tmux, attach normally
        print(f"Attaching to tmux session: {session_name}")
        print(f"(Press Ctrl+b, then d to detach)")
        run(["tmux", "attach-session", "-t", session_name], check=True)

def compose_assistant_prompt(dir_path: str, branch: str, prompt: str, auto_start: bool) -> str:
    """Combine worktree context with the user-provided prompt and optional instructions."""
    worktree_prefix = f"""IMPORTANT: You are working in a git worktree at: {dir_path}

This is an isolated working directory for branch: {branch}

DO NOT navigate to parent directories or try to find the "repo root".
ALL your work should be done in the current directory: {dir_path}

---

"""
    full_prompt = worktree_prefix + prompt
    if not auto_start:
        full_prompt += "\n\nPlease review the context above and wait for explicit instructions before making changes."
    return full_prompt


def build_assistant_command(assistant: str, prompt: str) -> str | None:
    quoted = shlex.quote(prompt)
    if assistant == "claude":
        return f"claude --dangerously-skip-permissions {quoted}"
    if assistant == "codex":
        return f"codex --dangerously-bypass-approvals-and-sandbox {quoted}"
    if assistant == "droid":
        return f"droid exec --skip-permissions-unsafe {quoted}"
    return None


def tmux_window_name(label: str, fallback: str) -> str:
    cleaned = slugify(label)
    return cleaned or fallback


def open_with_ai_assistant(dir_path: str, assistant: str, prompt: str, branch: str, auto_start: bool):
    """Open tmux session with Claude Code, Codex, or Droid and pass the prepared prompt."""
    full_prompt = compose_assistant_prompt(dir_path, branch, prompt, auto_start)
    command = build_assistant_command(assistant, full_prompt)
    if not command:
        return

    session_name = branch
    print(f"Opening {assistant} for {branch}...")
    open_in_tmux(dir_path, session_name, command)


def open_multiple_with_ai_assistant(worktrees: list, assistant: str, auto_start: bool):
    """Open multiple worktrees in a single tmux session with separate windows."""
    if not worktrees:
        return

    import time

    session_name = f"dux-{int(time.time())}"

    try:
        sessions_output = run(["tmux", "list-sessions", "-F", "#{session_name}"], check=False, capture=True)
        existing_sessions = sessions_output.split('\n') if sessions_output else []
        if session_name in existing_sessions:
            print(f"Error: tmux session '{session_name}' already exists")
            return
    except subprocess.CalledProcessError:
        pass

    print(f"Creating tmux session with {len(worktrees)} windows...")

    first = worktrees[0]
    first_branch = first.get("branch", "N/A")
    first_prompt = compose_assistant_prompt(first["dir_path"], first_branch, first.get("assistant_prompt", ""), auto_start)
    command = build_assistant_command(assistant, first_prompt)
    if not command:
        return

    first_label = first.get("assistant_label") or first_branch or "worktree"
    window_name = tmux_window_name(first_label, "worktree")
    run(["tmux", "new-session", "-d", "-s", session_name, "-c", first["dir_path"], "-n", window_name], check=True)
    run(["tmux", "send-keys", "-t", f"{session_name}:0", command, "C-m"], check=True)
    print(f"  Window 1: {first_label}")

    for idx, wt in enumerate(worktrees[1:], start=1):
        wt_branch = wt.get("branch", "N/A")
        wt_prompt = compose_assistant_prompt(wt["dir_path"], wt_branch, wt.get("assistant_prompt", ""), auto_start)
        command = build_assistant_command(assistant, wt_prompt)
        if not command:
            continue

        wt_label = wt.get("assistant_label") or wt_branch or f"window-{idx + 1}"
        window_name = tmux_window_name(wt_label, f"window-{idx + 1}")
        run(["tmux", "new-window", "-t", session_name, "-c", wt["dir_path"], "-n", window_name], check=True)
        run(["tmux", "send-keys", "-t", f"{session_name}:{idx}", command, "C-m"], check=True)
        print(f"  Window {idx + 1}: {wt_label}")

    if os.environ.get("TMUX"):
        print(f"\nSwitching to tmux session: {session_name}")
        run(["tmux", "switch-client", "-t", session_name], check=True)
    else:
        print(f"\nAttaching to tmux session: {session_name}")
        print(f"(Press Ctrl+b, then d to detach)")
        print(f"(Press Ctrl+b, then n/p to navigate windows)")
        run(["tmux", "attach-session", "-t", session_name], check=True)
# .dux.yml handling (no external deps)
# ----------------

WT_FILENAME = ".dux.yml"

def write_wt_example(path: Path, force: bool):
    if path.exists() and not force:
        raise SystemExit(f"{WT_FILENAME} already exists. Use --force to overwrite.")
    content = """# .dux.yml
# Repo-local bootstrap configuration for worktrees.
# All fields are optional. Uncomment and configure as needed.

# Path to environment file to copy into worktrees
# env: .env.local

# Command to install dependencies
# install: pnpm install

# Command to run dev server
# run: pnpm dev

# Base port for automatic port allocation
# port: 3000
"""
    path.write_text(content, encoding="utf-8")
    return str(path)

def update_gitignore(root: str):
    """Add .wt to .gitignore if it exists and doesn't already contain it."""
    gitignore_path = Path(root) / ".gitignore"

    if not gitignore_path.exists():
        return None

    # Read existing .gitignore content
    content = gitignore_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Check if .wt is already in .gitignore
    for line in lines:
        stripped = line.strip()
        if stripped == ".wt" or stripped == "/.wt":
            return None  # Already exists

    # Add .wt to .gitignore
    if content and not content.endswith("\n"):
        # Ensure there's a newline before adding
        content += "\n"

    content += ".wt\n"
    gitignore_path.write_text(content, encoding="utf-8")
    return str(gitignore_path)

def parse_simple_yaml(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing {WT_FILENAME} at repo root.")
    cfg = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        cfg[k.strip()] = v.strip()

    # Validate port if provided
    if "port" in cfg and cfg["port"]:
        try:
            int(cfg["port"])
        except ValueError:
            raise SystemExit("port must be an integer")

    return cfg

# ----------------
# Port allocation without registry
# ----------------

def parse_worktrees(root: str):
    wt_output = run(["git", "worktree", "list", "--porcelain"], cwd=root)
    lines = wt_output.splitlines()
    worktrees = []
    current = {}
    for ln in lines:
        if ln.startswith("worktree "):
            if current:
                worktrees.append(current)
                current = {}
            current["path"] = ln.split(" ", 1)[1].strip()
        elif ln.startswith("branch "):
            current["branch"] = ln.split(" ", 1)[1].strip().replace("refs/heads/", "")
    if current:
        worktrees.append(current)
    return worktrees


def find_existing_worktree_path(root: str, branch: str, desired_path: str) -> str | None:
    desired = Path(desired_path)
    if desired.exists():
        return desired_path

    try:
        worktrees = parse_worktrees(root)
        for wt in worktrees:
            wt_path = wt.get("path")
            wt_branch = wt.get("branch")
            if not wt_path or not wt_branch:
                continue
            if Path(wt_path).exists() and (wt_path == desired_path or wt_branch == branch):
                return wt_path
    except Exception:
        pass

    return None

def read_worktree_port(path: str, env_key: str) -> int | None:
    # 1) explicit per-worktree git config
    try:
        val = run(["git", "-C", path, "config", "--worktree", "--get", "issuewt.port"]) or None
        if val:
            p = int(val)
            if 1 <= p <= 65535:
                return p
    except Exception:
        pass
    # 2) env file PORT=
    try:
        env_path = Path(path) / env_key.split("/")[-1]
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("PORT="):
                    p = int(line.split("=", 1)[1].strip())
                    if 1 <= p <= 65535:
                        return p
    except Exception:
        pass
    return None

def used_ports(root: str, env_key: str) -> set[int]:
    used = set()
    for wt in parse_worktrees(root):
        pth = wt.get("path")
        if not pth:
            continue
        p = read_worktree_port(pth, env_key)
        if p:
            used.add(p)
    # also add currently bound ports (best effort) in the typical app range 1024-65535? we will check candidates instead
    return used

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0

def stable_hash(s: str) -> int:
    # simple FNV-1a 32-bit
    h = 0x811C9DC5
    fnv_prime = 0x01000193
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * fnv_prime) & 0xFFFFFFFF
    return h

def allocate_port(branch: str, base_port: int, used: set[int], span: int = 500) -> int:
    start = base_port + (stable_hash(branch) % span)
    # probe up to 2*span to be safe
    for i in range(0, span * 2):
        p = start + i
        if p in used:
            continue
        if port_in_use(p):
            continue
        return p
    raise SystemExit("No free port found in probe window. Increase span.")

def set_worktree_port(dir_path: str, port: int):
    try:
        run(["git", "-C", dir_path, "config", "--worktree", "issuewt.port", str(port)])
    except Exception:
        pass

def ensure_env_port(env_file: Path, port: int):
    lines = []
    found = False
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            if raw.startswith("PORT="):
                lines.append(f"PORT={port}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"PORT={port}")
    env_file.write_text("\\n".join(lines) + "\\n", encoding="utf-8")

# ----------------
# Bootstrap
# ----------------

def bootstrap_worktree(dir_path: str, repo_root: str, assigned_port: int | None, run_dev_server: bool = False):
    cfg = parse_simple_yaml(Path(repo_root) / WT_FILENAME)

    # Copy env file into the new worktree (keep same filename) - if configured
    if cfg.get("env"):
        env_src = Path(repo_root) / cfg["env"]
        env_dst = Path(dir_path) / Path(cfg["env"]).name
        if env_src.exists():
            shutil.copy2(env_src, env_dst)
            print(f"env copied -> {env_dst}")
            # If allocator provided a port, write it
            if assigned_port:
                ensure_env_port(env_dst, assigned_port)
        else:
            print(f"warn: env file not found at {env_src}")

    # Install deps - if configured
    if cfg.get("install"):
        print(f"install: {cfg['install']}")
        sh(cfg["install"], cwd=dir_path, check=True)

    # Run dev server if requested - if configured
    if run_dev_server and cfg.get("run"):
        print(f"Starting dev server: {cfg['run']}")
        if assigned_port:
            print(f"Running on port: {assigned_port}")
        sh(cfg["run"], cwd=dir_path, check=False)
    elif cfg.get("run"):
        print(f"To start dev server, run: {cfg['run']}")
        if assigned_port:
            print(f"port: {assigned_port}")

# ----------------
# Commands
# ----------------

def cmd_init(args):
    root = repo_root()
    path = Path(root) / WT_FILENAME
    written = write_wt_example(path=path, force=args.force)
    print(f"Wrote {written}")

    # Update .gitignore to include .wt directory
    gitignore_updated = update_gitignore(root)
    if gitignore_updated:
        print(f"Updated {gitignore_updated} to include .wt")


def process_single_issue(issue_num, root, base, args, context: str, issue_data=None):
    """Process a single GitHub issue and create or reuse its worktree."""
    try:
        issue = issue_data or gh_issue_view(issue_num)
        num = issue["number"]
        title = issue["title"]
        issue_url = issue["url"]
        body = issue.get("body", "")
        title_words = title.strip().split()
        limited_title = " ".join(title_words[:5]) if title_words else ""
        limited_slug = slugify(limited_title) if limited_title else ""
        full_slug = slugify(title)
        branch_slug = limited_slug or full_slug
        branch = f"issue/{num}-{branch_slug}"
        dir_path = worktree_dir(root, branch)

        existing_path = find_existing_worktree_path(root, branch, dir_path)

        if not existing_path and full_slug and branch_slug != full_slug:
            legacy_branch = f"issue/{num}-{full_slug}"
            legacy_path = worktree_dir(root, legacy_branch)
            legacy_existing = find_existing_worktree_path(root, legacy_branch, legacy_path)
            if legacy_existing:
                branch = legacy_branch
                dir_path = worktree_dir(root, branch)
                existing_path = legacy_existing

        assistant_prompt = f"Issue #{num}: {title}\n\n{body}\n\nIssue URL: {issue_url}"
        if context:
            assistant_prompt += f"\n\nAdditional context from request:\n{context}"

        label = f"Issue #{num}"

        if existing_path:
            return {
                "issue_num": num,
                "status": "exists",
                "branch": branch,
                "dir_path": existing_path,
                "issue_url": issue_url,
                "assistant_prompt": assistant_prompt,
                "assistant_label": label,
            }

        git_worktree_add(root, branch, dir_path, base)
        push_set_upstream(dir_path, branch)
        empty_commit_if_needed(dir_path, f"chore: start {branch} (#{num})")

        pr = gh_pr_view_by_head(branch)
        if not pr:
            try:
                pr = gh_pr_create(
                    base_branch=base,
                    head_branch=branch,
                    title=f"[#{num}] {title}",
                    body=f"Tracking {issue_url}\n\nCloses #{num}",
                    draft=not args.ready,
                )
            except subprocess.CalledProcessError:
                pr = gh_pr_view_by_head(branch)
                if not pr:
                    pr = {"url": "N/A", "state": "unknown"}

        cfg = parse_simple_yaml(Path(root) / WT_FILENAME)
        assigned_port = None
        if cfg.get("port"):
            base_port = int(cfg["port"])
            env_key = cfg.get("env", "")
            used = used_ports(root, env_key)
            assigned_port = allocate_port(branch, base_port, used)
            set_worktree_port(dir_path, assigned_port)

        if not args.no_bootstrap:
            bootstrap_worktree(dir_path, root, assigned_port, run_dev_server=args.run)

        pr_url = pr.get("url") if isinstance(pr, dict) else pr

        return {
            "issue_num": num,
            "status": "created",
            "branch": branch,
            "dir_path": dir_path,
            "issue_url": issue_url,
            "pr_url": pr_url,
            "port": assigned_port,
            "assistant_prompt": assistant_prompt,
            "assistant_label": label,
        }
    except Exception as e:
        return {
            "issue_num": issue_num,
            "status": "error",
            "error": str(e),
            "assistant_label": f"Issue #{issue_num}",
        }


def create_context_worktree(context: str, root: str, base: str, args):
    branch = derive_context_branch(root, context)
    dir_path = worktree_dir(root, branch)
    assistant_prompt = f"Task context:\n{context}\n\nThere is no linked GitHub issue for this worktree."
    label = branch

    existing_path = find_existing_worktree_path(root, branch, dir_path)
    if existing_path:
        return {
            "status": "exists",
            "branch": branch,
            "dir_path": existing_path,
            "assistant_prompt": assistant_prompt,
            "assistant_label": label,
        }

    try:
        git_worktree_add(root, branch, dir_path, base)
        push_set_upstream(dir_path, branch)
        empty_commit_if_needed(dir_path, f"chore: start {branch}")

        cfg = parse_simple_yaml(Path(root) / WT_FILENAME)
        assigned_port = None
        if cfg.get("port"):
            base_port = int(cfg["port"])
            env_key = cfg.get("env", "")
            used = used_ports(root, env_key)
            assigned_port = allocate_port(branch, base_port, used)
            set_worktree_port(dir_path, assigned_port)

        if not args.no_bootstrap:
            bootstrap_worktree(dir_path, root, assigned_port, run_dev_server=args.run)

        return {
            "status": "created",
            "branch": branch,
            "dir_path": dir_path,
            "port": assigned_port,
            "assistant_prompt": assistant_prompt,
            "assistant_label": label,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "branch": branch,
            "assistant_label": label,
        }


def open_requested_tools(entries: list, args, auto_start: bool):
    ready = [entry for entry in entries if entry.get("status") in ("created", "exists")]
    if not ready:
        return

    if args.code:
        for entry in ready:
            open_in_code(entry["dir_path"])

    def _open_single(entry, tool: str):
        open_with_ai_assistant(
            entry["dir_path"],
            tool,
            entry.get("assistant_prompt", ""),
            entry.get("branch", "worktree"),
            auto_start,
        )

    def _open_many(tool: str):
        open_multiple_with_ai_assistant(ready, tool, auto_start)

    if args.claude:
        if len(ready) == 1:
            _open_single(ready[0], "claude")
        else:
            _open_many("claude")

    if args.codex:
        if len(ready) == 1:
            _open_single(ready[0], "codex")
        else:
            _open_many("codex")

    if args.droid:
        if len(ready) == 1:
            _open_single(ready[0], "droid")
        else:
            _open_many("droid")


def handle_single_result(result: dict, args, auto_start: bool):
    status = result.get("status")
    if status == "error":
        raise SystemExit(f"Error: {result.get('error', 'unknown error')}")

    if status == "exists":
        print(f"Worktree already exists at: {result['dir_path']}")
        print("Branch:  ", result["branch"])
        if result.get("issue_url"):
            print("Issue:   ", result["issue_url"])
        open_requested_tools([result], args, auto_start)
        return

    if status == "created":
        print(DUCK_ART)
        print("Worktree:", result["dir_path"])
        print("Branch:  ", result["branch"])
        if result.get("issue_url"):
            print("Issue:   ", result["issue_url"])
        if result.get("pr_url"):
            print("PR:      ", result["pr_url"])
        if result.get("port"):
            print("Assigned port:", result["port"])
        open_requested_tools([result], args, auto_start)
        return

    raise SystemExit("Unexpected result state")


def handle_multi_results(results: list, args, auto_start: bool):
    print(DUCK_ART)
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    created = [r for r in results if r.get("status") == "created"]
    exists = [r for r in results if r.get("status") == "exists"]
    errors = [r for r in results if r.get("status") == "error"]

    if created:
        print(f"\n✓ Created {len(created)} worktree(s):")
        for r in created:
            label = r.get("assistant_label", r.get("branch", "worktree"))
            print(f"  {label}: {r['dir_path']}")
            print(f"    Branch: {r['branch']}")
            if r.get("issue_url"):
                print(f"    Issue:  {r['issue_url']}")
            if r.get("pr_url"):
                print(f"    PR:     {r['pr_url']}")
            if r.get("port"):
                print(f"    Port:   {r['port']}")

    if exists:
        print(f"\n○ Already exists ({len(exists)}):")
        for r in exists:
            label = r.get("assistant_label", r.get("branch", "worktree"))
            print(f"  {label}: {r['dir_path']}")

    if errors:
        print(f"\n✗ Errors ({len(errors)}):")
        for r in errors:
            label = r.get("assistant_label", r.get("branch", "worktree"))
            print(f"  {label}: {r.get('error', 'unknown error')}")

    open_requested_tools(created + exists, args, auto_start)

    if errors:
        print("\nOne or more worktrees failed. See errors above.")


def cmd_create(args):
    root = repo_root()
    base = args.base or get_default_branch()
    ensure_base_up_to_date(base)

    try:
        run(["git", "worktree", "prune"], cwd=root, check=False)
    except Exception:
        pass

    context_words = getattr(args, "context", [])
    context = " ".join(context_words).strip()

    if args.new and args.issue:
        raise SystemExit("--new cannot be used together with --issue")

    if not context:
        if args.new:
            context = args.new.strip()
        elif args.issue:
            context = ""
        else:
            raise SystemExit("Context is required for `create` when no issue is specified.")

    issue_numbers = []
    prefetched = {}

    if args.new:
        issue = gh_issue_create(args.new, context or "Auto-created for worktree.")
        issue_number = str(issue["number"])
        issue_numbers = [issue_number]
        prefetched[issue_number] = issue
    elif args.issue:
        issue_numbers = [num.strip() for num in args.issue.split(",") if num.strip()]
        if not issue_numbers:
            raise SystemExit("--issue requires at least one issue number")

    auto_start = bool(args.start)

    if issue_numbers:
        if len(issue_numbers) == 1:
            issue_num = issue_numbers[0]
            issue_data = prefetched.get(issue_num)
            result = process_single_issue(issue_num, root, base, args, context, issue_data=issue_data)
            handle_single_result(result, args, auto_start)
            return

        print(f"Processing {len(issue_numbers)} issues...")
        results = []
        for issue_num in issue_numbers:
            issue_data = prefetched.get(issue_num)
            result = process_single_issue(issue_num, root, base, args, context, issue_data=issue_data)
            results.append(result)

            label = result.get("assistant_label", f"Issue #{issue_num}")
            status = result.get("status")
            if status == "created":
                print(f"✓ {label}: Created worktree at {result['dir_path']}")
            elif status == "exists":
                print(f"○ {label}: Worktree already exists at {result['dir_path']}")
            else:
                print(f"✗ {label}: Error - {result.get('error', 'unknown error')}")

        handle_multi_results(results, args, auto_start)
        return

    result = create_context_worktree(context, root, base, args)
    handle_single_result(result, args, auto_start)


def cmd_clean(args):
    root = repo_root()
    for wt in parse_worktrees(root):
        path = wt.get("path")
        branch = wt.get("branch", "")
        if not path or not branch:
            continue
        if branch in ("main", "master"):
            continue

        should_remove = False

        if args.all:
            # Remove all worktrees regardless of PR status
            should_remove = True
            print(f"Removing {branch}")
        else:
            # Only remove merged PRs
            try:
                pr = gh_pr_view_by_head(branch)
                if pr and pr.get("state", "").lower() == "merged":
                    should_remove = True
                    print(f"Pruning {branch} (merged)")
            except Exception as e:
                print(f"Skip {branch}: {e}")
                continue

        if should_remove:
            try:
                run(["git", "worktree", "remove", "--force", path], cwd=root)
                try:
                    run(["git", "branch", "-D", branch], cwd=root)
                except subprocess.CalledProcessError:
                    pass
                try:
                    run(["git", "push", "origin", "--delete", branch], cwd=root)
                except subprocess.CalledProcessError:
                    pass
            except Exception as e:
                print(f"Error removing {branch}: {e}")

def cmd_view(_args):
    try:
        branch = run(["git", "branch", "--show-current"])
    except subprocess.CalledProcessError:
        raise SystemExit("Error: not inside a git repository")

    if not branch:
        raise SystemExit("Error: unable to determine current branch")

    pr = gh_pr_view_by_head(branch)
    if not pr or not pr.get("url"):
        raise SystemExit(f"No GitHub PR found for branch '{branch}'. Create one with 'gh pr create' or 'dux create'.")

    print(f"Opening PR for branch '{branch}' -> {pr['url']}")
    try:
        run(["gh", "pr", "view", "--web", "--head", branch], capture=False)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Failed to open PR for branch '{branch}': {exc}") from exc

def cmd_status(_args):
    root = repo_root()
    cfg = None
    try:
        cfg = parse_simple_yaml(Path(root) / WT_FILENAME)
    except SystemExit:
        pass

    # Get active tmux sessions
    try:
        tmux_sessions = run(["tmux", "list-sessions", "-F", "#{session_name}"], check=False, capture=True)
        active_sessions = set(tmux_sessions.split('\n')) if tmux_sessions else set()
    except Exception:
        active_sessions = set()

    for wt in parse_worktrees(root):
        path = wt.get("path")
        branch = wt.get("branch")
        if not path or not branch:
            continue
        pr = gh_pr_view_by_head(branch)
        pr_url = pr.get("url") if pr else "-"
        pr_state = pr.get("state") if pr else "none"
        dirty = "dirty" if run(["git", "status", "--porcelain"], cwd=path) else "clean"
        port = read_worktree_port(path, cfg.get("env", "")) if cfg else "-"

        # Check if tmux session exists for this branch
        tmux_indicator = "tmux" if branch in active_sessions else "-"

        print(f"{branch:40} {dirty:6} {pr_state:8} {str(port):>5} {tmux_indicator:4} {pr_url}")
        print(f"  {path}")

# ----------------
# CLI
# ----------------

def main():
    require("git")
    require("gh")
    require("tmux")

    parser = argparse.ArgumentParser(description="Issue-centric Git worktree manager with GitHub PR automation.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # init
    p_init = sub.add_parser("init", help=f"Create {WT_FILENAME} template in repo root with commented examples")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing file")
    p_init.set_defaults(func=cmd_init)

    # create
    p_create = sub.add_parser("create", help="Create a worktree from context with optional GitHub issue linkage")
    p_create.add_argument("context", nargs="*", help="Short description or context for the worktree")
    p_create.add_argument("--issue", help="Comma-separated GitHub issue number(s) to link to this worktree")
    p_create.add_argument("--new", metavar="TITLE", help="Create a new issue with this title")
    p_create.add_argument("--base", default=get_default_branch(), help="Base branch (auto-detected; override)")
    p_create.add_argument("--ready", action="store_true", help="Open PR as ready (not draft)")
    p_create.add_argument("--code", action="store_true", help="Open in VS Code")
    p_create.add_argument("--claude", action="store_true", help="Open Claude Code in tmux with issue description")
    p_create.add_argument("--codex", action="store_true", help="Open Codex in tmux with issue description")
    p_create.add_argument("--droid", action="store_true", help="Open Factory AI Droid in tmux with issue description")
    p_create.add_argument("--run", action="store_true", help="Start dev server after setup")
    p_create.add_argument("--no-bootstrap", action="store_true", help="Skip .dux.yml bootstrap steps")
    p_create.add_argument("--start", action="store_true", help="Automatically start the chosen coding assistant")
    p_create.set_defaults(func=cmd_create)

    # status
    p_status = sub.add_parser("status", help="List worktrees with PR status and assigned ports")
    p_status.set_defaults(func=cmd_status)

    # clean
    p_clean = sub.add_parser("clean", help="Remove worktrees/branches whose PRs are merged")
    p_clean.add_argument("--all", action="store_true", help="Remove ALL worktrees (not just merged)")
    p_clean.set_defaults(func=cmd_clean)

    # view
    p_view = sub.add_parser("view", help="Open the current branch's PR in the browser")
    p_view.set_defaults(func=cmd_view)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
