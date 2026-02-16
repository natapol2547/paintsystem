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

UPSTREAM_BRANCH="$(git rev-parse --abbrev-ref --symbolic-full-name "${CURRENT_BRANCH}@{upstream}" 2>/dev/null || true)"
PUSH_ARGS=()

if [[ -n "$UPSTREAM_BRANCH" ]]; then
  echo "Using upstream push target: $UPSTREAM_BRANCH"
  PUSH_REMOTE="${UPSTREAM_BRANCH%%/*}"
  UPSTREAM_REF="${UPSTREAM_BRANCH#*/}"
  PUSH_ARGS=("$PUSH_REMOTE" "$CURRENT_BRANCH:$UPSTREAM_REF")
elif git ls-remote --exit-code --heads origin "$CURRENT_BRANCH" >/dev/null 2>&1; then
  echo "No upstream configured. Using origin/$CURRENT_BRANCH"
  PUSH_ARGS=("origin" "$CURRENT_BRANCH")
else
  echo "No upstream configured for '$CURRENT_BRANCH' and no matching origin branch exists."
  echo "This is common for local PR checkouts (e.g. pr-<number>)."
  echo "Set tracking to the real source branch, then re-run:"
  echo "  git branch --set-upstream-to origin/<source-branch> $CURRENT_BRANCH"
  exit 1
fi

if git rebase origin/"$BASE_BRANCH"; then
  echo "Rebase successful. Pushing $CURRENT_BRANCH..."
  git push "${PUSH_ARGS[@]}" --force-with-lease
  echo "Branch $CURRENT_BRANCH is now in sync with $BASE_BRANCH."
else
  echo "Rebase conflicts detected. Aborting rebase."
  git rebase --abort || true
  echo "Please resolve conflicts manually and re-run the script."
  exit 1
fi

exit 0
