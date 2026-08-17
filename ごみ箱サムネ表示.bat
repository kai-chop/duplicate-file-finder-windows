@echo off
chcp 65001 >nul
setlocal
rem  No argument     : thumbnails of images/videos currently in the Recycle Bin
rem  Drop a .csv     : re-create thumbnails of files deleted by dedupe.py
rem  Type a keyword  : filter by original location
set "ARG=%~1"
where python >nul 2>&1 && (set "PY=python") || (set "PY=py -3")

if /I "%~x1"==".csv" (
  %PY% "%~dp0recycle_gallery.py" --from-csv "%ARG%" %2 %3 %4 %5
) else if not "%ARG%"=="" (
  %PY% "%~dp0recycle_gallery.py" --match "%ARG%" %2 %3 %4 %5
) else (
  %PY% "%~dp0recycle_gallery.py" %2 %3 %4 %5
)

echo.
pause
