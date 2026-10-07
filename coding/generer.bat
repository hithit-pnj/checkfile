@echo off
cd /d "%~dp0.."
if "%~1"=="" (
  echo.
  echo Glissez un fichier Excel ou CSV sur generer.bat
  echo.
  pause
  exit /b 1
)
python -m coding.generate_coding "%~1"
if errorlevel 1 (
  echo.
  echo La generation a echoue.
  pause
  exit /b 1
)
echo.
echo Termine. Le classeur _coding.xlsx est a cote du fichier.
pause
