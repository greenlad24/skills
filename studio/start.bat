@echo off
title Vibration Poster Studio
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Node.js is not installed. Please install the LTS version from:
  echo   https://nodejs.org
  echo.
  pause
  exit /b 1
)

start "" http://localhost:5713
node server.js
pause
