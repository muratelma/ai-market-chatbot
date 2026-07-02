@echo off
chcp 65001 > nul

set ROOT=C:\Users\Ahmet\DOCUME~1\BITIRM~1\AI-MAR~1
set BACKEND=%ROOT%\backend
set FRONTEND=%ROOT%\frontend

echo [1/3] Docker baslatiliyor...
docker compose --project-directory %ROOT% up -d

echo [2/3] Backend baslatiliyor...
start "AI-Market Backend" cmd /k "cd /d %BACKEND% && .venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo [3/3] Frontend baslatiliyor...
start "AI-Market Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

echo.
echo Hazir!
echo   Backend  -^>  http://localhost:8000
echo   Frontend -^>  http://localhost:5173
echo.
pause
