@echo off
setlocal enabledelayedexpansion

cd /d c:\Users\pinkn\Documents\PinkSystem1\paintsystem

echo Fetching latest from remote...
git fetch origin

REM Sync Remove-Auto-Uv
echo.
echo Syncing Remove-Auto-Uv...
git checkout Remove-Auto-Uv
git rebase origin/pink-system
git push origin Remove-Auto-Uv --force-with-lease
echo Remove-Auto-Uv synced!

REM Sync quick-tools-
echo.
echo Syncing quick-tools-...
git checkout quick-tools-
git rebase origin/pink-system
git push origin quick-tools- --force-with-lease
echo quick-tools- synced!

REM Sync Convert-to-PS
echo.
echo Syncing Convert-to-PS...
git checkout Convert-to-PS
git rebase origin/pink-system
git push origin Convert-to-PS --force-with-lease
echo Convert-to-PS synced!

REM Sync Naming
echo.
echo Syncing Naming...
git checkout Naming
git rebase origin/pink-system -X theirs
git push origin Naming --force-with-lease
echo Naming synced!

REM Sync feature/uv-edit
echo.
echo Syncing feature/uv-edit...
git checkout feature/uv-edit
git rebase origin/pink-system
git push origin feature/uv-edit --force-with-lease
echo feature/uv-edit synced!

echo.
echo ============================================
echo All branches re-synced with pink-system!
echo ============================================
