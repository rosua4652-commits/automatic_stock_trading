@echo off
REM Korean Windows: console + Python stdout UTF-8 (log garbled text fix)
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
