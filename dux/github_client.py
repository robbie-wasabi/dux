"""GitHub CLI helpers."""

from __future__ import annotations

import json
import subprocess

from .utils import run


def gh_issue_create(title: str, body: str):
    """Create a GitHub issue via gh CLI and return its metadata."""
    out = run(
        ["gh", "issue", "create", "--title", title, "--body", body, "--json", "number,title,url,body"],
        capture=True,
    )
    return json.loads(out)


def gh_issue_view(number: str):
    """Fetch a GitHub issue payload for the given number."""
    out = run(
        ["gh", "issue", "view", str(number), "--json", "number,title,url,body"],
        capture=True,
    )
    return json.loads(out)


def gh_pr_view_by_head(branch: str):
    """Return PR details for the branch head, or None if not found."""
    try:
        out = run(["gh", "pr", "view", "--head", branch, "--json", "url,state"])
        return json.loads(out)
    except subprocess.CalledProcessError:
        return None


def gh_pr_create(base_branch: str, head_branch: str, title: str, body: str, draft: bool = True):
    """Create a PR for head_branch against base_branch and return its summary."""
    args = [
        "gh",
        "pr",
        "create",
        "--base",
        base_branch,
        "--head",
        head_branch,
        "--title",
        title,
        "--body",
        body,
    ]
    if draft:
        args.append("--draft")
    out = run(args + ["--json", "url,state"])
    return json.loads(out)
