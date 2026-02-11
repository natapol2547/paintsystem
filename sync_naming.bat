@echo off
setlocal enabledelayedexpansion

cd /d c:\Users\pinkn\Documents\PinkSystem1\paintsystem

echo Aborting any stuck rebase...
git rebase --abort 2>nul

echo Checking out Naming branch...
git checkout Naming

echo Rebasing with theirs strategy...
set GIT_EDITOR=true
git rebase origin/pink-system --strategy=theirs --no-edit

echo Pushing Naming branch...
git push origin Naming --force-with-lease

echo.
echo Naming branch sync COMPLETED!
