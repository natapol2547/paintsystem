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

set "UPSTREAM_BRANCH="
set "PUSH_REMOTE="
set "PUSH_SPEC="
set "UPSTREAM_REF="

for /f "delims=" %%U in ('git rev-parse --abbrev-ref --symbolic-full-name "!TARGET_BRANCH!@{upstream}" 2^>nul') do set "UPSTREAM_BRANCH=%%U"

if defined UPSTREAM_BRANCH (
	echo Using upstream push target: !UPSTREAM_BRANCH!
	for /f "tokens=1* delims=/" %%A in ("!UPSTREAM_BRANCH!") do (
		set "PUSH_REMOTE=%%A"
		set "UPSTREAM_REF=%%B"
	)
	if not defined UPSTREAM_REF (
		echo Failed to parse upstream target for !TARGET_BRANCH!.
		exit /b 1
	)
	set "PUSH_SPEC=!TARGET_BRANCH!:!UPSTREAM_REF!"
) else (
	git ls-remote --exit-code --heads origin !TARGET_BRANCH! >nul 2>nul
	if errorlevel 1 (
		echo No upstream configured for !TARGET_BRANCH! and no matching origin branch exists.
		echo This is common for local PR checkouts.
		echo Set tracking to the real source branch, then re-run:
		echo   git branch --set-upstream-to origin/^<source-branch^> !TARGET_BRANCH!
		exit /b 1
	)
	echo No upstream configured. Using origin/!TARGET_BRANCH!
	set "PUSH_REMOTE=origin"
	set "PUSH_SPEC=!TARGET_BRANCH!"
)

git push !PUSH_REMOTE! !PUSH_SPEC! --force-with-lease
if errorlevel 1 (
	echo Push failed on !TARGET_BRANCH!.
	exit /b 1
)

echo !TARGET_BRANCH! synced!
exit /b 0
