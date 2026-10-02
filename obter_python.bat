@echo off
REM ===========================================================================
REM  Garante que exista um Python 3.10 ou mais novo no computador.
REM
REM  Ordem de tentativa:
REM    1. Python ja instalado no computador
REM    2. winget (Windows 10 ou mais novo) - rapido e limpo
REM    3. Instalador oficial do python.org em modo usuario (sem admin)
REM
REM  Escreve o caminho do executavel em PYTHON_ENCONTRADO.txt se achar.
REM ===========================================================================

setlocal EnableDelayedExpansion
cd "%~dp0"

REM Versao do Python a baixar na ultima etapa (a do winget e sempre a mais nova)
set VERSAO=3.12
set ARQUIVO=python-%VERSAO%-amd64.exe
set URL=https://www.python.org/ftp/python/%VERSAO%.10/%ARQUIVO%

echo.
echo   Procurando Python...
echo.

REM --------------------------------------------------------------------------
REM  1. Python ja instalado?
REM --------------------------------------------------------------------------
call :checar_python
if defined PYTHON_ENCONTRADO (
    echo   Python encontrado em %PYTHON_ENCONTRADO%
    call :salvar
    endlocal & exit /b 0
)

echo   Nenhum Python encontrado.
echo.

REM --------------------------------------------------------------------------
REM  2. winget
REM --------------------------------------------------------------------------
where winget >nul 2>nul
if %errorlevel%==0 (
    echo   Tentando instalar pelo winget...
    echo.
    winget install --id Python.Python.%VERSAO% -e ^
        --accept-source-agreements ^
        --accept-package-agreements ^
        --silent
    echo.

    call :checar_python
    if defined PYTHON_ENCONTRADO (
        echo   Python instalado pelo winget.
        call :salvar
        endlocal & exit /b 0
    )

    echo   O winget nao conseguiu. Baizando direto do python.org...
    echo.
) else (
    echo   winget nao existe neste computador.
    echo   Baixando direto do python.org...
    echo.
)

REM --------------------------------------------------------------------------
REM  3. Instalador do python.org, modo usuario (sem pedir administrador)
REM --------------------------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue';" ^
    "try {" ^
    "  Write-Host '   Baixando instalador (~25 MB)...';" ^
    "  Invoke-WebRequest -Uri '%URL%' -OutFile '%TEMP%\%ARQUIVO%';" ^
    "  Write-Host '   Instalando (pode levar alguns minutos)...';" ^
    "  Start-Process -FilePath '%TEMP%\%ARQUIVO%' -ArgumentList " ^
    "'/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=0','Include_test=0','AssociateFiles=0','Shortcuts=0' -Wait;" ^
    "  Remove-Item '%TEMP%\%ARQUIVO%' -Force -ErrorAction SilentlyContinue;" ^
    "  Write-Host '   Concluido.';" ^
    "} catch { Write-Host ('   Falha: ' + `$_.Exception.Message); exit 1 }"
echo.

call :checar_python
if defined PYTHON_ENCONTRADO (
    echo   Python instalado pelo python.org.
    call :salvar
    endlocal & exit /b 0
)

REM --------------------------------------------------------------------------
REM  Nao deu
REM --------------------------------------------------------------------------
echo   Nao foi possivel instalar o Python automaticamente.
echo.
echo   Instale manualmente em:
echo     https://www.python.org/downloads/
echo.
echo   Na instalacao, marque a opcao "Add Python to PATH".
echo   Depois rode instalar.bat de novo.
echo.
endlocal & exit /b 1


REM ===========================================================================
REM  Procura o Python em varios lugares (inclusive onde o winget instala)
REM ===========================================================================
:checar_python
set PYTHON_ENCONTRADO=

REM  Launchers do Windows
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -c "import sys" >nul 2>nul
    if %errorlevel%==0 set PYTHON_ENCONTRADO=py -3
)

if not defined PYTHON_ENCONTRADO (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python -c "import sys" >nul 2>nul
        if %errorlevel%==0 set PYTHON_ENCONTRADO=python
    )
)

REM  Caminhos comuns (winget e instalador em modo usuario)
if not defined PYTHON_ENCONTRADO (
    for %%P in (
        "%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        "%LOCALAPPDATA%\Programs\Python"
        "%ProgramFiles%\Python*"
    ) do (
        for /f "delims=" %%F in ('dir /b /s "%%~P\python.exe" 2^>nul') do (
            if not defined PYTHON_ENCONTRADO (
                echo %%F | find "Scripts" >nul || set PYTHON_ENCONTRADO=%%F
            )
        )
    )
)

goto :eof


REM ===========================================================================
REM  Grava o caminho num arquivo, para o instalar.bat ler
REM ===========================================================================
:salvar
> "%~dp0PYTHON_ENCONTRADO.txt" echo %PYTHON_ENCONTRADO%
goto :eof
