@echo off
REM Buduje instalator dla Windows 7 (Python 3.8 + starsze biblioteki).
REM Wymaga: venv-win7 (utworzony przez: py -3.8 -m venv venv-win7)
REM          venv-win7\Scripts\pip install -r requirements-win7.txt

setlocal
call venv-win7\Scripts\activate
pyinstaller --clean --noconfirm newsreader-win7.spec
if errorlevel 1 exit /b 1
"C:\Program Files (x86)\NSIS\makensis.exe" NewsReader-win7.nsi
endlocal