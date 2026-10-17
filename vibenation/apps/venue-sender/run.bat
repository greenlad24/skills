@echo off
rem VibeNation venue sender - double-click to send the MR18 to the show server.
rem   run.bat          start sending (uses sender.ini)
rem   run.bat --list   list the sound cards
setlocal
cd /d "%~dp0"
title VibeNation sender - keep this window open
if not exist ".venv\Scripts\python.exe" (
  echo  Setup has not been run yet. Double-click setup.bat first.
  pause
  exit /b 1
)
if not exist ffmpeg.exe (
  echo  ffmpeg.exe is missing. Double-click setup.bat first.
  pause
  exit /b 1
)
rem Keep the laptop awake while sending.
powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change monitor-timeout-ac 0 >nul 2>&1
".venv\Scripts\python.exe" vibenation_sender.py %*
echo.
if "%~1"=="--list" (
  echo  Put part of the MR18 name from this list after "device =" in sender.ini if it is not found.
) else (
  echo  The sender STOPPED. Read the message above, fix it, then double-click run.bat again.
)
pause
