@echo off
rem Starts the chatbot API used by the GP2 web pages (chatbot-page).
rem Keep this window open while using the chat; close it to stop the server.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [!] .venv is missing. Run:  python -m uv sync
  pause
  exit /b 1
)

rem Embeddings need Ollama (bge-m3). Start it if it isn't running yet.
curl -s http://127.0.0.1:11434/api/version >nul 2>&1
if errorlevel 1 (
  echo Starting Ollama...
  start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
  timeout /t 5 /nobreak >nul
)

echo Starting Academic AI API on http://localhost:8000 ...
".venv\Scripts\python.exe" fastapi_app.py
pause
