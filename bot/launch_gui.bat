@echo off
REM Launch Interview Assistant with GUI

echo Starting Interview Assistant GUI...
python main_gui.py

if errorlevel 1 (
    echo.
    echo Error: Failed to start application
    echo.
    echo Make sure Python is installed and all dependencies are available:
    echo   pip install -r ../requirements.txt
    echo.
    pause
)
