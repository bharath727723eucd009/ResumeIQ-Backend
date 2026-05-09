@echo off
echo Installing backend dependencies...
pip install -r requirements.txt

echo.
echo Starting backend server...
uvicorn app.main:app --reload --port 8000
