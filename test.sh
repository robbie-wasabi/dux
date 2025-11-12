#!/bin/bash
set -e

echo "=== DUX Integration Test ==="

# Create temp test repo
TEST_DIR="/tmp/dux-test-$$"
echo "Creating test repo at $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Initialize git repo
git init
git config user.email "test@example.com"
git config user.name "Test User"

# Create initial commit on dev branch
git checkout -b dev
echo "# Test Project" > README.md
echo "PORT=3000" > .env.local
git add .
git commit -m "Initial commit"

# Add a fake remote
git remote add origin https://github.com/test/test-repo.git

echo ""
echo "=== Testing dux init ==="
dux init --env .env.local --install "echo 'installing'" --run "echo 'running'" --port 3000

echo ""
echo "=== Checking .dux.yml was created ==="
cat .dux.yml

echo ""
echo "=== Testing worktree creation (simulated) ==="
# We can't actually create a GitHub issue without auth, so let's test the worktree logic directly
BRANCH="issue/1-test-issue"
WORKTREE_DIR=".wt/issue/1-test-issue"

echo "Attempting to create worktree at $WORKTREE_DIR from dev branch"
mkdir -p .wt
git worktree add -b "$BRANCH" "$WORKTREE_DIR" dev

echo ""
echo "=== Worktree created successfully! ==="
git worktree list

echo ""
echo "=== Cleaning up ==="
git worktree remove "$WORKTREE_DIR"
cd /tmp
rm -rf "$TEST_DIR"

echo ""
echo "=== Test completed successfully! ==="
