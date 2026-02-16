@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d c:\Users\pinkn\Documents\PinkSystem1\paintsystem
if errorlevel 1 (
	echo Failed to enter repository directory.
	exit /b 1
)

echo Fetching latest from remote...
git fetch origin
if errorlevel 1 (
	echo Fetch failed.
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

call :sync_branch Remove-Auto-Uv
if errorlevel 1 exit /b 1

call :sync_branch quick-tools-
if errorlevel 1 exit /b 1

call :sync_branch Convert-to-PS
if errorlevel 1 exit /b 1

call :sync_branch Naming
if errorlevel 1 exit /b 1

call :sync_branch feature/uv-edit
if errorlevel 1 exit /b 1

echo.
echo ============================================
echo All branches re-synced with pink-system!
echo ============================================
exit /b 0

:sync_branch
set "TARGET_BRANCH=%~1"
echo.
echo Syncing !TARGET_BRANCH!...

git rebase --abort 2>nul

git checkout !TARGET_BRANCH!
if errorlevel 1 (
	echo Failed to checkout !TARGET_BRANCH!.
	exit /b 1
)

git rebase origin/pink-system
if errorlevel 1 (
	echo Rebase failed on !TARGET_BRANCH!. Aborting.
	git rebase --abort 2>nul
	exit /b 1
)

git push origin !TARGET_BRANCH! --force-with-lease
if errorlevel 1 (
	echo Push failed on !TARGET_BRANCH!.
	exit /b 1
)

echo !TARGET_BRANCH! synced!
exit /b 0
