@echo off
setlocal EnableExtensions
cd /d c:\Users\pinkn\Documents\PinkSystem1\paintsystem
if errorlevel 1 (
	echo Failed to enter repository directory.
	exit /b 1
)

git fetch origin
if errorlevel 1 (
	echo Failed to fetch from origin.
	exit /b 1
)

git diff --quiet
if errorlevel 1 (
	echo Working tree has uncommitted changes. Commit or stash first.
	exit /b 1
)

git diff --cached --quiet
if errorlevel 1 (
	echo Index has staged changes. Commit or stash first.
	exit /b 1
)

REM Abort any stuck rebase
git rebase --abort 2>nul

REM Checkout Naming branch
git checkout Naming
if errorlevel 1 (
	echo Failed to checkout Naming.
	exit /b 1
)

REM Rebase onto pink-system
git rebase origin/pink-system
if errorlevel 1 (
	echo Rebase failed. Aborting.
	git rebase --abort 2>nul
	exit /b 1
)

REM Push the synced branch
git push origin Naming --force-with-lease
if errorlevel 1 (
	echo Push failed.
	exit /b 1
)

echo Naming branch sync complete!
pause
