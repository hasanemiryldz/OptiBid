@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ilk kurulum icin Kurulum.bat dosyasini calistirin.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -X utf8 baslat.py %*
if errorlevel 1 pause
