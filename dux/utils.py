"""Shared utility helpers for dux."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


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
    """Exit with error when the given executable is not on PATH."""
    if shutil.which(bin_name) is None:
        raise SystemExit(f"Missing dependency: {bin_name} not found on PATH")


def repo_root() -> str:
    """Return the absolute path to the git repository root."""
    return run(["git", "rev-parse", "--show-toplevel"])


def get_default_branch() -> str:
    """Detect repo default branch from origin/HEAD or current branch."""
    try:
        ref = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
        return ref.split("/")[-1]
    except Exception:
        pass

    try:
        current = run(["git", "branch", "--show-current"])
        if current:
            return current
    except Exception:
        pass

    try:
        remote_branches = run(["git", "branch", "-r"])
        for candidate in ["dev", "develop", "main", "master"]:
            if f"origin/{candidate}" in remote_branches:
                return candidate
    except Exception:
        pass

    return "main"


def slugify(text: str) -> str:
    """Normalize text into a lowercase, hyphen-separated slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s or "work"


def ensure_base_up_to_date(base_branch: str):
    """Attempt to fetch the designated base branch from origin, warning on failure."""
    try:
        run(["git", "fetch", "origin", base_branch])
    except subprocess.CalledProcessError:
        print(f"Warning: Could not fetch {base_branch} from origin")
