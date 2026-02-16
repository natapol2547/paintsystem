@echo off
setlocal EnableExtensions EnableDelayedExpansion

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

echo Aborting any stuck rebase...
git rebase --abort 2>nul

echo Checking out Naming branch...
git checkout Naming
if errorlevel 1 (
	echo Failed to checkout Naming.
	exit /b 1
)

echo Rebasing Naming onto origin/pink-system...
set GIT_EDITOR=true
git rebase origin/pink-system --no-edit
if errorlevel 1 (
	echo Rebase failed. Aborting.
	git rebase --abort 2>nul
	exit /b 1
)

echo Pushing Naming branch...
set "TARGET_BRANCH=Naming"
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
	echo Push failed.
	exit /b 1
)

echo.
echo Naming branch sync COMPLETED!
