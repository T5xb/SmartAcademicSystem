@echo off
rem Keeps this folder in sync with GitHub while the window stays open:
rem every 30 seconds it uploads your saved changes and downloads teammates' changes.
rem Close the window (or press Ctrl+C) to stop syncing.
cd /d "%~dp0"
title Auto-Sync - SmartAcademicSystem
echo Auto-sync is running. Saved changes upload every 30 seconds. Close this window to stop.
echo.

:loop
git add -A >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
  git commit -q -m "Auto-sync: changes from %COMPUTERNAME%"
  echo [%time:~0,8%] Committed your changes.
)

git pull -q --rebase --autostash >nul 2>&1
if errorlevel 1 (
  git rebase --abort >nul 2>&1
  echo [%time:~0,8%] [!] Conflict with a teammate's change - fix it manually, then restart this window.
  pause
  exit /b 1
)

git push -q >nul 2>&1
if errorlevel 1 echo [%time:~0,8%] [!] Push failed - check your internet or GitHub login.

timeout /t 30 /nobreak >nul
goto loop
