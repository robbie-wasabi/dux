# drop all tmux sessions and clear git worktrees
cleanup:
	tmux kill-session -a
	dux clean --all

install:
	pip install -e .

reinstall:
	pip install -e . --force-reinstall --no-deps