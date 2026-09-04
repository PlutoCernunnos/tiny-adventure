@echo off
REM Try to run with pythonw to hide console; fall back to python if not available
where pythonw >nul 2>&1
if %errorlevel%==0 (
  pythonw "%~dp0mane game.py"
) else (
  python "%~dp0mane game.py"
)
exit /b
