@echo off
title JARVIS Setup
echo Installing voice/automation dependencies...
python -m pip install --upgrade pip
python -m pip install pyautogui psutil pillow pyaudiowpatch vosk
echo.
echo Done. Now run start_jarvis.bat
pause
