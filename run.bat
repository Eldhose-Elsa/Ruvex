@echo off
title Ruvex - RAW Image Converter
python "%~dp0main.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred running Ruvex.
    pause
)
