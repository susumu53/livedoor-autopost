@echo off
chcp 65001 > nul
cd /d "%~dp0"
python update_bigirl_rss.py
echo.
pause

