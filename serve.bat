@echo off
cd /d "%~dp0"
echo Starting Markets Watch on http://localhost:8182
start http://localhost:8182
python server.py
pause
