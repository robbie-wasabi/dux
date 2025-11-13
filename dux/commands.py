"""Command implementations for the dux CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .assistants import open_in_code
from .assistants import open_multiple_with_ai_assistant
from .assistants import open_with_ai_assistant
from .config import WT_FILENAME
from .config import parse_simple_yaml
from .config import update_gitignore
from .config import write_wt_example
from .github_client import gh_issue_create
from .github_client import gh_issue_view
from .github_client import gh_pr_create
from .github_client import gh_pr_view_by_head
from .utils import ensure_base_up_to_date
from .utils import get_default_branch
from .utils import repo_root
from .utils import run
from .utils import slugify
from .worktree import allocate_port
from .worktree import bootstrap_worktree
from .worktree import derive_context_branch
from .worktree import empty_commit_if_needed
from .worktree import find_existing_worktree_path
from .worktree import git_worktree_add
from .worktree import parse_worktrees
from .worktree import push_set_upstream
from .worktree import read_worktree_port
from .worktree import set_worktree_port
from .worktree import used_ports
from .worktree import worktree_dir


DUCK_ART = r"""
       _
     >(o )___
      ( ._> /
       `---'
"""


def cmd_init(args):
    """Initialize .dux.yml and ensure .wt is ignored."""
    root = repo_root()
    path = Path(root) / WT_FILENAME
    written = write_wt_example(path=path, force=args.force)
    print(f"Wrote {written}")

    gitignore_updated = update_gitignore(root)
    if gitignore_updated:
        print(f"Updated {gitignore_updated} to include .wt")


def open_requested_tools(entries: list, args, auto_start: bool):
    """Open any requested editors or assistants for created worktrees."""
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


def process_single_issue(issue_num, root, base, args, context: str, issue_data=None):
    """Create a worktree tied to a specific GitHub issue if it doesn't exist."""
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
    """Create or reuse a worktree based on free-form context."""
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


def handle_single_result(result: dict, args, auto_start: bool):
    """Format and display the outcome for a single worktree request."""
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
    """Summarize multiple worktree operations and launch requested tools."""
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
    """Entry point for `dux create`, handling issues or ad-hoc contexts."""
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
    """Remove worktrees whose branches are merged, or everything with --all."""
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
            should_remove = True
            print(f"Removing {branch}")
        else:
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
    """Open the GitHub PR associated with the current branch in the browser."""
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
    """List current worktrees with cleanliness, PR info, ports, and tmux state."""
    root = repo_root()
    cfg = None
    try:
        cfg = parse_simple_yaml(Path(root) / WT_FILENAME)
    except SystemExit:
        pass

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

        tmux_indicator = "tmux" if branch in active_sessions else "-"

        print(f"{branch:40} {dirty:6} {pr_state:8} {str(port):>5} {tmux_indicator:4} {pr_url}")
        print(f"  {path}")
