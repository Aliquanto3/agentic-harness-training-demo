@echo off
rem Installe et lance WaveStack en une commande (double-clic ou invite CMD).
rem Delegue a install.ps1, qui fait le vrai travail en PowerShell.
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
