@echo off
rem VibeNation venue sender - one-time setup (no building needed).
rem Double-click this file. It needs Python 3.12 (64-bit) and an internet connection.
setlocal
cd /d "%~dp0"
title VibeNation sender setup
echo.
echo  VibeNation venue sender - setup
echo  ================================
echo.

if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
  echo  PROBLEM: this laptop runs 32-bit Windows. The sender needs 64-bit Windows 10 or 11.
  goto :fail
)

rem --- 1. Python 3.12 ---------------------------------------------------------
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) and sys.maxsize>2**32 else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  py -3.12 -c "import sys; sys.exit(0 if sys.maxsize>2**32 else 1)" >nul 2>&1 && set "PY=py -3.12"
)
if not defined PY (
  echo  PROBLEM: Python 3.12 is not installed, or not on PATH.
  echo.
  echo  1. Download and run this installer:
  echo       https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
  echo  2. On the FIRST installer screen, tick the box at the bottom:
  echo       [x] Add python.exe to PATH
  echo     then click "Install Now".
  echo  3. Close this window and double-click setup.bat again.
  echo.
  echo  Opening the download page for you...
  start "" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
  goto :fail
)
echo  [1/4] Python 3.12 found.

rem --- 2. Private Python environment (.venv) ---------------------------------
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :fail_venv
)
echo  [2/4] Python environment ready.

rem --- 3. Audio libraries ------------------------------------------------------
echo  [3/4] Installing audio libraries (1-2 minutes)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q sounddevice==0.5.1 soundfile==0.12.1 numpy==2.1.3 || goto :fail_pip

rem --- 4. ffmpeg.exe with SRT --------------------------------------------------
if exist ffmpeg.exe (
  ffmpeg.exe -hide_banner -protocols 2>nul | findstr /r /c:"^ *srt$" >nul && goto :ffmpeg_ok
  echo  The ffmpeg.exe here has no SRT support - replacing it.
  del /q ffmpeg.exe
)
echo  [4/4] Downloading ffmpeg (about 100 MB - can take up to 20 minutes on slow internet)...
rem gyan.dev "essentials" builds include libsrt (see https://www.gyan.dev/ffmpeg/builds/).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12';" ^
  "try { Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile ffmpeg.zip -UseBasicParsing }" ^
  "catch { Write-Host '  gyan.dev failed, trying GitHub...'; Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile ffmpeg.zip -UseBasicParsing }" ^
  "if (Test-Path ffmpeg-tmp) { Remove-Item ffmpeg-tmp -Recurse -Force }; Expand-Archive ffmpeg.zip -DestinationPath ffmpeg-tmp -Force;" ^
  "Copy-Item (Get-ChildItem ffmpeg-tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName ." || goto :fail_ffmpeg
rmdir /s /q ffmpeg-tmp >nul 2>&1
del /q ffmpeg.zip >nul 2>&1
ffmpeg.exe -hide_banner -protocols 2>nul | findstr /r /c:"^ *srt$" >nul || goto :fail_ffmpeg
:ffmpeg_ok
echo  [4/4] ffmpeg with SRT ready.

echo.
echo  Checking the sound card list...
".venv\Scripts\python.exe" vibenation_sender.py --list
echo.
echo  ======================================================
echo   SETUP DONE. Now double-click run.bat to start sending.
echo  ======================================================
echo.
pause
exit /b 0

:fail_venv
echo  PROBLEM: could not create the Python environment (.venv).
goto :fail
:fail_pip
echo  PROBLEM: could not install the audio libraries. Check the internet and run setup.bat again.
goto :fail
:fail_ffmpeg
echo  PROBLEM: could not download ffmpeg with SRT. Check the internet and run setup.bat again.
goto :fail
:fail
echo.
echo  Setup did NOT finish. Take a photo of this window and send it to Claude.
echo.
pause
exit /b 1
