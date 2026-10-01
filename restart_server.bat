@echo off
REM Reinicia o servidor. Usa o caminho desta pasta, entao funciona
REM em qualquer computador, desde que este arquivo seja chamado de dentro dela.

taskkill /F /IM streamlit.exe /T 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 3 /nobreak >nul

REM %~dp0 devolve o caminho desta pasta, com barra no fim
cd "%~dp0"
cmd.exe /c "%~dp0run_server.bat"