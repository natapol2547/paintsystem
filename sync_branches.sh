#!/usr/bin/env bash
set -euo pipefail

# sync_branches.sh
# Safely rebase the current branch onto the remote pink-system branch and push.
# Usage: ./sync_branches.sh [base-branch]

BASE_BRANCH="${1:-pink-system}"

git fetch origin

# Ensure clean working tree
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Uncommitted changes present. Commit or stash before running."
  exit 1
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Currently syncing branch: $CURRENT_BRANCH"
echo "Rebasing onto origin/$BASE_BRANCH..."

if git rebase origin/"$BASE_BRANCH"; then
  echo "Rebase successful. Pushing $CURRENT_BRANCH..."
  git push origin "$CURRENT_BRANCH" --force-with-lease
  echo "Branch $CURRENT_BRANCH is now in sync with $BASE_BRANCH."
else
  echo "Rebase conflicts detected. Aborting rebase."
  git rebase --abort || true
  echo "Please resolve conflicts manually and re-run the script."
  exit 1
fi

exit 0
