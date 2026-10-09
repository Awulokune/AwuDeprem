@echo off
setlocal
py -3 -m pip install --upgrade pip
if errorlevel 1 goto failed
py -3 -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto failed
echo AwuDeprem kuruldu. run.bat dosyasi ile baslatin.
pause
exit /b 0
:failed
echo Kurulum basarisiz oldu. Python 3 ve internet baglantisini kontrol edin.
pause
exit /b 1
