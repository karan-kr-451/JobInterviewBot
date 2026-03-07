@echo off
REM Build Interview Assistant executable using PyInstaller

echo ============================================================
echo Building Interview Assistant Executable
echo ============================================================

REM Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found
    echo Using system Python - this may cause missing module errors
    echo.
)

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Show Python info
echo.
echo Using Python:
python --version
python -c "import sys; print(f'Location: {sys.executable}')"
echo.

REM Run build script
echo Running build script...
python build_exe.py

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Build completed successfully!
echo ============================================================
echo.
echo Executable location: dist\InterviewAssistant.exe
echo.
pause
