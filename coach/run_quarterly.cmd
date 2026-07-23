@echo off
cd /d "%USERPROFILE%\.claude\coach"
python coach_blindspot.py >> quarterly.log 2>&1
