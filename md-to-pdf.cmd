@echo off
chcp 65001 >nul
setlocal

if "%~1"=="" (
  echo.
  echo   Перетащите .md или .docx на этот значок: рядом появится PDF в оформлении A2DATA.
  echo.
  pause
  exit /b 1
)

set "PYTHONPATH=%~dp0"

:loop
echo Собираю "%~nx1" ...
python -m a2pdf "%~f1"
if errorlevel 1 goto err
if exist "%~dpn1.pdf" start "" "%~dpn1.pdf"
shift
if not "%~1"=="" goto loop
exit /b 0

:err
echo.
echo   Не получилось. Нужен Python и один раз: pip install -r requirements.txt
echo.
pause
exit /b 1
