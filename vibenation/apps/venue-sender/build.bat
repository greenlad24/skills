@echo off
rem Builds dist\vibenation-sender\ (copy that folder to the venue laptop).
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
pip install -r requirements.txt || goto :err
if not exist ffmpeg.exe (
  powershell -Command "Invoke-WebRequest https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip -OutFile ffmpeg.zip; Expand-Archive ffmpeg.zip -DestinationPath ffmpeg-tmp -Force; Copy-Item (Get-ChildItem ffmpeg-tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName ."
)
pyinstaller --noconfirm --name vibenation-sender --console vibenation_sender.py || goto :err
copy /Y ffmpeg.exe dist\vibenation-sender\ && copy /Y sender.ini dist\vibenation-sender\
echo Done: dist\vibenation-sender
exit /b 0
:err
echo Build failed.
exit /b 1
