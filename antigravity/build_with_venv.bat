@echo off
echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate

echo Installing build tools...
python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller==6.10.0

echo Installing requirements...
rem Install CPU torch to avoid CUDA payload embedding
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

echo Building executable...
python build_exe.py

echo Build complete: dist\InterviewAssistant.exe
pause
