#!/bin/bash
cd c:\\Users\\pinkn\\Documents\\PinkSystem1\\paintsystem

echo "Checking out Naming..."
git checkout Naming || exit 1

echo "Merging pink-system with theirs strategy..."
git merge origin/pink-system -X theirs -m "Sync with pink-system"

echo "Pushing Naming..."
git push origin Naming --force-with-lease

echo "Done!"
