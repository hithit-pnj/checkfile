@echo off
cd /d "%~dp0.."
if "%~1"=="" (
  echo.
  echo Glissez le fichier original sur remplacer.bat
  echo Le classeur _coding.xlsx doit etre a cote de lui.
  echo.
  pause
  exit /b 1
)
if "%~2"=="" (
  python -m coding.generate_coded_file "%~1"
) else (
  python -m coding.generate_coded_file "%~1" "%~2"
)
if errorlevel 1 (
  echo.
  echo Le remplacement a echoue.
  pause
  exit /b 1
)
echo.
echo Termine. Le fichier _coded.xlsx est a cote du fichier original.
pause
