@echo off
setlocal
cd /d "%~dp0"
start "LivingPQ R20 LOCAL SERVER" /min cmd /c "node server.cjs 4190"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:4190/"
exit /b 0
