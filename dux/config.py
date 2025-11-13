"""Configuration helpers for dux worktrees."""

from __future__ import annotations

from pathlib import Path


WT_FILENAME = ".dux.yml"


def write_wt_example(path: Path, force: bool):
    """Generate the template .dux.yml file, optionally overwriting an existing one."""
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

    content = gitignore_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped in {".wt", "/.wt"}:
            return None

    if content and not content.endswith("\n"):
        content += "\n"

    content += ".wt\n"
    gitignore_path.write_text(content, encoding="utf-8")
    return str(gitignore_path)


def parse_simple_yaml(path: Path) -> dict:
    """Read the lightweight .dux.yml format into a dict with minimal validation."""
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

    if "port" in cfg and cfg["port"]:
        try:
            int(cfg["port"])
        except ValueError:
            raise SystemExit("port must be an integer")

    return cfg


def ensure_env_port(env_file: Path, port: int):
    """Ensure the PORT entry in the copied env file matches the assigned port."""
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
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
