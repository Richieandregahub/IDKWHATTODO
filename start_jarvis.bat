@echo off
title Richie Jarvis Core
cd /d "%~dp0"
echo Starting Richie Jarvis core on http://localhost:8765 ...
start "" http://localhost:8765
python server.py
pause
