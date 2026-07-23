@echo off
cd /d "%USERPROFILE%\.claude\coach"
python coach_sync.py >> sync.log 2>&1
