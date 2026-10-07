@echo off
cd /d "%~dp0.."
if "%~1"=="" (
  echo.
  echo Glissez un fichier Excel ou CSV sur verifier.bat
  echo.
  pause
  exit /b 1
)
python -m data_quality_simple.main "%~1"
if errorlevel 1 (
  echo.
  echo Le controle a echoue.
  pause
  exit /b 1
)
echo.
echo Termine. Le rapport .txt est a cote du fichier.
pause
