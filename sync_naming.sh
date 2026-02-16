#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

git fetch origin

if ! git diff --quiet || ! git diff --cached --quiet; then
	echo "Uncommitted or staged changes detected. Commit or stash first."
	exit 1
fi

echo "Checking out Naming..."
git checkout Naming || exit 1

echo "Rebasing Naming onto origin/pink-system..."
if ! git rebase origin/pink-system; then
	echo "Rebase failed. Aborting."
	git rebase --abort || true
	exit 1
fi

echo "Pushing Naming..."
git push origin Naming --force-with-lease

echo "Done!"
