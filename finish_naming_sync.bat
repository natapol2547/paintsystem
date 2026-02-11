@echo off
cd /d c:\Users\pinkn\Documents\PinkSystem1\paintsystem

REM Abort any stuck rebase
git rebase --abort 2>nul

REM Checkout Naming branch
git checkout Naming

REM Rebase with theirs strategy (accept pink-system versions)
git rebase origin/pink-system --strategy=theirs

REM Push the synced branch
git push origin Naming --force-with-lease

echo Naming branch sync complete!
pause
