"""CLI parser wiring for dux."""

from __future__ import annotations

import argparse

from .commands import cmd_clean
from .commands import cmd_create
from .commands import cmd_init
from .commands import cmd_status
from .commands import cmd_view
from .utils import get_default_branch
from .utils import require


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="Issue-centric Git worktree manager with GitHub PR automation."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser(
        "init",
        help="Create .dux.yml template in repo root with commented examples",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing file")
    p_init.set_defaults(func=cmd_init)

    p_create = sub.add_parser(
        "create",
        help="Create a worktree from context with optional GitHub issue linkage",
    )
    p_create.add_argument("context", nargs="*", help="Short description or context for the worktree")
    p_create.add_argument("--issue", help="Comma-separated GitHub issue number(s) to link to this worktree")
    p_create.add_argument("--new", metavar="TITLE", help="Create a new issue with this title")
    p_create.add_argument(
        "--base",
        default=get_default_branch(),
        help="Base branch (auto-detected; override)",
    )
    p_create.add_argument("--ready", action="store_true", help="Open PR as ready (not draft)")
    p_create.add_argument("--code", action="store_true", help="Open in VS Code")
    p_create.add_argument("--claude", action="store_true", help="Open Claude Code in tmux with issue description")
    p_create.add_argument("--codex", action="store_true", help="Open Codex in tmux with issue description")
    p_create.add_argument("--droid", action="store_true", help="Open Factory AI Droid in tmux with issue description")
    p_create.add_argument("--run", action="store_true", help="Start dev server after setup")
    p_create.add_argument("--no-bootstrap", action="store_true", help="Skip .dux.yml bootstrap steps")
    p_create.add_argument("--start", action="store_true", help="Automatically start the chosen coding assistant")
    p_create.set_defaults(func=cmd_create)

    p_status = sub.add_parser("status", help="List worktrees with PR status and assigned ports")
    p_status.set_defaults(func=cmd_status)

    p_clean = sub.add_parser("clean", help="Remove worktrees/branches whose PRs are merged")
    p_clean.add_argument("--all", action="store_true", help="Remove ALL worktrees (not just merged)")
    p_clean.set_defaults(func=cmd_clean)

    p_view = sub.add_parser("view", help="Open the current branch's PR in the browser")
    p_view.set_defaults(func=cmd_view)

    return parser


def main(argv: list[str] | None = None):
    """CLI entrypoint invoked by console script or module run."""
    require("git")
    require("gh")
    require("tmux")

    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
