@echo off
chcp 65001 >nul
setlocal
set "TARGET=%~1"
if "%TARGET%"=="" set /p "TARGET=Folder path (or drag a folder onto this .bat): "
if "%TARGET%"=="" goto :end

where python >nul 2>&1 && (set "PY=python") || (set "PY=py -3")
%PY% "%~dp0dedupe.py" "%TARGET%" --ask %2 %3 %4

:end
echo.
pause
