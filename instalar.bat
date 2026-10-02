@echo off
REM ===========================================================================
REM  Instalador - Sistema de Encaminhamento de Alunos (Windows)
REM
REM  Este script instala o Python se faltar, cria o ambiente virtual,
REM  instala as dependencias e sobe o sistema.
REM
REM  DCLICK neste arquivo.
REM ===========================================================================

setlocal
cd "%~dp0"

echo.
echo ==============================================================
echo   SISTEMA DE ENCAMINHAMENTO DE ALUNOS
echo   Instalacao
echo ==============================================================
echo.

REM --------------------------------------------------------------------------
REM  Garante o Python
REM --------------------------------------------------------------------------
call "%~dp0obter_python.bat"
set PY_OK=%errorlevel%

if not "%PY_OK%"=="0" (
    echo.
    echo   Instale o Python e rode instalar.bat de novo.
    echo.
    pause
    endlocal & exit /b 1
)

REM --------------------------------------------------------------------------
REM  Descobre o executavel do Python
REM --------------------------------------------------------------------------
set PY_CMD=
if exist "%~dp0PYTHON_ENCONTRADO.txt" (
    set /p PY_CMD=< "%~dp0PYTHON_ENCONTRADO.txt"
)

if not defined PY_CMD (
    where py >nul 2>nul && set PY_CMD=py -3
)
if not defined PY_CMD (
    where python >nul 2>nul && set PY_CMD=python
)

if not defined PY_CMD (
    echo.
    echo   Nao consegui localizar o Python depois da instalacao.
    echo   Reinicie o computador e tente de novo.
    echo.
    pause
    endlocal & exit /b 1
)

REM --------------------------------------------------------------------------
REM  Instala o sistema
REM --------------------------------------------------------------------------
%PY_CMD% instalar.py %*
set ERRO=%errorlevel%

if not "%ERRO%"=="0" (
    echo.
    echo   A instalacao terminou com erro.
    echo   Leia a mensagem acima.
    echo.
    pause
)

endlocal
