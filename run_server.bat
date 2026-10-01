@echo off
REM Sistema de Encaminhamento - Executavel Robusto
REM Executa Streamlit com auto-restart e sem hot-reload

:START
echo Iniciando Sistema de Encaminhamento...
echo URL: http://localhost:8501
echo Pressione Ctrl+C para parar
echo.

set PYTHONPATH=%CD%
call venv\Scripts\activate.bat

REM Desabilita hot-reload (causa desconexoes) e file watcher
streamlit run encaminhamento/app.py ^
  --server.port 8501 ^
  --server.headless true ^
  --server.enableCORS false ^
  --server.enableXsrfProtection false ^
  --server.runOnSave false ^
  --browser.gatherUsageStats false ^
  --global.developmentMode false

echo.
echo Servidor parou. Reiniciando em 5 segundos...
timeout /t 5 /nobreak >nul
goto START
