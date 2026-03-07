@echo off
REM Build Interview Assistant using virtual environment

echo ============================================================
echo Building Interview Assistant with Virtual Environment
echo ============================================================

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at .venv
    echo Please create it first: python -m venv .venv
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check if PyInstaller is installed in venv
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found in venv. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Show Python version
echo.
echo Using Python:
python --version
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
