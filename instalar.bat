@echo off
REM Instalador - Sistema de Encaminhamento de Alunos
REM DCLICK neste arquivo para instalar e rodar.

setlocal
cd "%~dp0"

REM Procura o Python: tenta py, depois python
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py -3
    goto rodar
)

where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
    goto rodar
)

echo.
echo   Python nao encontrado neste computador.
echo.
echo   Instale o Python 3.10 ou mais novo:
echo     https://www.python.org/downloads/
echo.
echo   No Windows, marque "Add Python to PATH" durante a instalacao.
echo.
pause
exit /b 1

:rodar
echo.
%PY% instalar.py %*
set ERRO=%errorlevel%

if not "%ERRO%"=="0" (
    echo.
    echo   A instalacao terminou com erro.
    echo   Leia a mensagem acima.
    echo.
    pause
)

endlocal