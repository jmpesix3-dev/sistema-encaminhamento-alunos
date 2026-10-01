@echo off
REM Inicia o sistema (sem reinstalar) - Windows
REM Use se ja instalou antes com instalar.bat

setlocal
cd "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo.
    echo   Ainda nao instalado.
    echo   Rode instalar.bat primeiro.
    echo.
    pause
    exit /b 1
)

if /I "%1"=="reiniciar" goto reiniciar

echo Iniciando o sistema... abra http://localhost:8501
echo Para encerrar, pressione Ctrl+C
echo.
venv\Scripts\python.exe -m streamlit run encaminhamento\app.py ^
  --server.port 8501 ^
  --server.headless true ^
  --browser.gatherUsageStats false
goto fim

:reiniciar
taskkill /F /IM streamlit.exe /T 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 3 /nobreak >nul
cd "%~dp0"
cmd.exe /c "%~dp0run_server.bat"
goto fim

:fim
endlocal