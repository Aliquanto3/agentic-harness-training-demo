@echo off
rem Installe et lance WaveStack en une commande (double-clic ou invite CMD).
rem Delegue a install.ps1, qui fait le vrai travail en PowerShell.
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
rem Double-clic : garder la fenetre ouverte pour lire l'erreur.
if not "%EXIT_CODE%"=="0" pause
endlocal & exit /b %EXIT_CODE%
