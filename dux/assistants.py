"""Integration helpers for coding assistants via tmux."""

from __future__ import annotations

import os
import shlex
import time
import shutil

from .utils import run
from .utils import slugify


def open_in_code(dir_path: str):
    """Launch VS Code in a new window for the given directory when available."""
    if shutil.which("code"):
        try:
            run(["code", "-n", dir_path])
        except Exception:
            pass


def open_in_tmux(dir_path: str, session_name: str, command: str | None = None):
    """Create a tmux session rooted in the worktree and optionally run a command."""
    try:
        sessions_output = run(["tmux", "list-sessions", "-F", "#{session_name}"], check=False, capture=True)
        existing_sessions = sessions_output.split("\n") if sessions_output else []
    except Exception:
        existing_sessions = []

    if session_name in existing_sessions:
        print(f"Error: tmux session '{session_name}' already exists")
        print(f"To attach: tmux attach -t {shlex.quote(session_name)}")
        print(f"To kill:   tmux kill-session -t {shlex.quote(session_name)}")
        return

    print(f"Creating tmux session: {session_name}")

    run(["tmux", "new-session", "-d", "-s", session_name, "-c", dir_path], check=True)

    if command:
        run(["tmux", "send-keys", "-t", session_name, command, "C-m"], check=True)

    if os.environ.get("TMUX"):
        print(f"Switching to tmux session: {session_name}")
        run(["tmux", "switch-client", "-t", session_name], check=True)
    else:
        print(f"Attaching to tmux session: {session_name}")
        print("(Press Ctrl+b, then d to detach)")
        run(["tmux", "attach-session", "-t", session_name], check=True)


def compose_assistant_prompt(dir_path: str, branch: str, prompt: str, auto_start: bool) -> str:
    worktree_prefix = f"""IMPORTANT: You are working in a git worktree at: {dir_path}

This is an isolated working directory for branch: {branch}

DO NOT navigate to parent directories or try to find the \"repo root\".
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
    """Open a single worktree in tmux with the selected assistant command."""
    full_prompt = compose_assistant_prompt(dir_path, branch, prompt, auto_start)
    command = build_assistant_command(assistant, full_prompt)
    if not command:
        return

    session_name = branch
    print(f"Opening {assistant} for {branch}...")
    open_in_tmux(dir_path, session_name, command)


def open_multiple_with_ai_assistant(worktrees: list, assistant: str, auto_start: bool):
    """Launch a shared tmux session with one window per worktree."""
    if not worktrees:
        return

    session_name = f"dux-{int(time.time())}"

    try:
        sessions_output = run(["tmux", "list-sessions", "-F", "#{session_name}"], check=False, capture=True)
        existing_sessions = sessions_output.split("\n") if sessions_output else []
        if session_name in existing_sessions:
            print(f"Error: tmux session '{session_name}' already exists")
            return
    except Exception:
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
        print("(Press Ctrl+b, then d to detach)")
        print("(Press Ctrl+b, then n/p to navigate windows)")
        run(["tmux", "attach-session", "-t", session_name], check=True)
