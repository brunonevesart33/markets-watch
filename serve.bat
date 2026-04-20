@echo off
cd /d "%~dp0"
echo Starting Markets Watch on http://localhost:8181
start http://localhost:8181
python -m http.server 8181
pause
