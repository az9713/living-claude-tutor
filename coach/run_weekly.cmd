@echo off
cd /d "%USERPROFILE%\.claude\coach"
python coach_weekly.py >> weekly.log 2>&1
