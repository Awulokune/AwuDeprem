@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo HATA: Python Launcher bulunamadi. Python 3.10+ kurup PATH'e ekleyin.
  exit /b 1
)
set "CANDLE=work\wix3\candle.exe"
set "LIGHT=work\wix3\light.exe"
if not exist "%CANDLE%" (
  where candle.exe >nul 2>nul
  if not errorlevel 1 set "CANDLE=candle.exe"
)
if not exist "%LIGHT%" (
  where light.exe >nul 2>nul
  if not errorlevel 1 set "LIGHT=light.exe"
)
if not exist "%CANDLE%" (
  echo HATA: WiX candle.exe bulunamadi. WiX v3.14 komut satiri araclarini work\wix3 altina acin veya PATH'e ekleyin.
  echo Indirme: https://github.com/wixtoolset/wix3/releases
  exit /b 1
)
if not exist "%LIGHT%" (
  echo HATA: WiX light.exe bulunamadi. WiX v3.14 komut satiri araclarini work\wix3 altina acin veya PATH'e ekleyin.
  exit /b 1
)

py -3 -m pip --version >nul 2>nul
if errorlevel 1 (
  echo HATA: Python pip bulunamadi. Python kurulumunu pip bileseniyle onarin.
  exit /b 1
)
py -3 -m pip install -r requirements.txt -r build-requirements.txt
if errorlevel 1 (
  echo HATA: Python paketleri kurulamadi. Internet baglantisini ve pip hatasini kontrol edin.
  exit /b 1
)

if not exist dist mkdir dist
if not exist build mkdir build
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name AwuDeprem --add-data "%CD%\city_coordinates.json;." --distpath dist --workpath build\pyinstaller --specpath build app.py
if errorlevel 1 (
  echo HATA: PyInstaller EXE olusturamadi; yukaridaki hata ciktisini inceleyin.
  exit /b 1
)
if not exist "dist\AwuDeprem.exe" (
  echo HATA: PyInstaller basarili gorundu ancak dist\AwuDeprem.exe bulunamadi.
  exit /b 1
)

"%CANDLE%" -nologo -dAppExe="%CD%\dist\AwuDeprem.exe" -out "build\installer.wixobj" installer.wxs
if errorlevel 1 (
  echo HATA: WiX candle derleme adimi basarisiz oldu; yukaridaki ciktisini inceleyin.
  exit /b 1
)
del /q "dist\AwuDeprem-Setup.msi" "dist\AwuDeprem-Setup.wixpdb" "dist\cab1.cab" 2>nul
"%LIGHT%" -nologo -out "dist\AwuDeprem-Setup.msi" "build\installer.wixobj"
if errorlevel 1 (
  echo HATA: WiX light MSI olusturamadi; yukaridaki ciktisini inceleyin.
  exit /b 1
)
if not exist "dist\AwuDeprem-Setup.msi" (
  echo HATA: Derleme tamamlandi bildirildi ancak MSI dosyasi bulunamadi.
  exit /b 1
)
if exist "dist\cab1.cab" (
  echo HATA: MSI disinda cab1.cab bulundu. Tek dosyali kurulum icin WiX kaynak dosyasindaki EmbedCab ayarini kontrol edin.
  exit /b 1
)
echo MSI basariyla olusturuldu: %CD%\dist\AwuDeprem-Setup.msi
exit /b 0
