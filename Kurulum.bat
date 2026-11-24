@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 goto fail
:install
echo OptiBid, MCP ve PDF okuma bagimliliklari kuruluyor...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Kurulum tamamlandi. Baslat.bat dosyasini acin.
pause
exit /b 0
:fail
echo Kurulum tamamlanamadi. Python 3.12 ve internet baglantisini kontrol edin.
pause
exit /b 1
