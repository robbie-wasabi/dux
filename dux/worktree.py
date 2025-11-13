"""Worktree and port allocation helpers."""

from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path

from .config import WT_FILENAME
from .config import ensure_env_port
from .config import parse_simple_yaml
from .utils import run
from .utils import sh
from .utils import slugify


def worktree_dir(root: str, branch: str) -> str:
    """Return the expected on-disk path for a worktree branch."""
    return str(Path(root) / ".wt" / branch)


def branch_exists(root: str, branch: str) -> bool:
    """Check whether a branch ref already exists locally."""
    try:
        run(["git", "rev-parse", "--verify", branch], cwd=root)
        return True
    except subprocess.CalledProcessError:
        return False


def derive_context_branch(root: str, context: str, prefix: str = "work", word_limit: int = 5) -> str:
    """Derive a unique branch slug from a free-form context string."""
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
    """Create or attach a worktree for the branch rooted at base_branch."""
    Path(dir_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        run(["git", "rev-parse", "--verify", branch], cwd=root)
        branch_exists_locally = True
    except subprocess.CalledProcessError:
        branch_exists_locally = False

    if branch_exists_locally:
        run(["git", "worktree", "add", dir_path, branch], cwd=root)
    else:
        run(["git", "worktree", "add", "-b", branch, dir_path, f"origin/{base_branch}"], cwd=root)


def push_set_upstream(dir_path: str, branch: str):
    """Push the branch and set upstream, ignoring failures."""
    try:
        run(["git", "push", "-u", "origin", branch], cwd=dir_path)
    except subprocess.CalledProcessError:
        pass


def empty_commit_if_needed(dir_path: str, message: str):
    """Ensure the branch has at least one commit so PRs can be opened."""
    try:
        upstream = run(["git", "rev-parse", "@{upstream}"], cwd=dir_path)
        ahead = run(["git", "rev-list", "--count", f"{upstream}..HEAD"], cwd=dir_path)
        if ahead == "0":
            run(["git", "commit", "--allow-empty", "-m", message], cwd=dir_path)
            run(["git", "push"], cwd=dir_path)
    except Exception:
        pass


def parse_worktrees(root: str):
    """Parse `git worktree list --porcelain` output into a dict list."""
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
    """Return an existing worktree path matching branch or target directory."""
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
    """Inspect git config and env file to detect an assigned PORT value."""
    try:
        val = run(["git", "-C", path, "config", "--worktree", "--get", "issuewt.port"]) or None
        if val:
            p = int(val)
            if 1 <= p <= 65535:
                return p
    except Exception:
        pass

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
    """Collect all ports currently reserved by known worktrees."""
    used = set()
    for wt in parse_worktrees(root):
        pth = wt.get("path")
        if not pth:
            continue
        p = read_worktree_port(pth, env_key)
        if p:
            used.add(p)
    return used


def port_in_use(port: int) -> bool:
    """Check if localhost already has the port bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def stable_hash(value: str) -> int:
    """Compute a stable FNV-1a hash for branch-based port seeding."""
    h = 0x811C9DC5
    fnv_prime = 0x01000193
    for ch in value.encode("utf-8"):
        h ^= ch
        h = (h * fnv_prime) & 0xFFFFFFFF
    return h


def allocate_port(branch: str, base_port: int, used: set[int], span: int = 500) -> int:
    """Pick a free port deterministically relative to the branch name."""
    start = base_port + (stable_hash(branch) % span)
    for i in range(0, span * 2):
        p = start + i
        if p in used:
            continue
        if port_in_use(p):
            continue
        return p
    raise SystemExit("No free port found in probe window. Increase span.")


def set_worktree_port(dir_path: str, port: int):
    """Persist the assigned port in the per-worktree git config."""
    try:
        run(["git", "-C", dir_path, "config", "--worktree", "issuewt.port", str(port)])
    except Exception:
        pass


def bootstrap_worktree(dir_path: str, repo_root: str, assigned_port: int | None, run_dev_server: bool = False):
    """Run bootstrap steps such as env copy, install command, and optional dev server."""
    cfg = parse_simple_yaml(Path(repo_root) / WT_FILENAME)

    if cfg.get("env"):
        env_src = Path(repo_root) / cfg["env"]
        env_dst = Path(dir_path) / Path(cfg["env"]).name
        if env_src.exists():
            shutil.copy2(env_src, env_dst)
            print(f"env copied -> {env_dst}")
            if assigned_port:
                ensure_env_port(env_dst, assigned_port)
        else:
            print(f"warn: env file not found at {env_src}")

    if cfg.get("install"):
        print(f"install: {cfg['install']}")
        sh(cfg["install"], cwd=dir_path, check=True)

    if run_dev_server and cfg.get("run"):
        print(f"Starting dev server: {cfg['run']}")
        if assigned_port:
            print(f"Running on port: {assigned_port}")
        sh(cfg["run"], cwd=dir_path, check=False)
    elif cfg.get("run"):
        print(f"To start dev server, run: {cfg['run']}")
        if assigned_port:
            print(f"port: {assigned_port}")
