"""
Instalador do Sistema de Encaminhamento de Alunos.

Roda em Windows, macOS e Linux. Cria o ambiente virtual, instala as
dependencias e deixa o sistema pronto para uso.

Uso:
    python instalar.py            instala e pergunta se quer rodar
    python instalar.py --run      instala e roda direto
    python instalar.py --check    so verifica o que falta
"""
import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
VENV = RAIZ / "venv"
REQUISITOS = RAIZ / "requirements.txt"

VERSAO_MINIMA = (3, 10)

# executavel do python dentro do venv, por sistema operacional
if platform.system() == "Windows":
    PYTHON_VENV = VENV / "Scripts" / "python.exe"
else:
    PYTHON_VENV = VENV / "bin" / "python"

# O console do Windows usa cp1252 e nao aceita os simbolos abaixo.
# Se nao der para usar UTF-8, caimos para ASCII.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    SIMBOLOS = {"ok": "+", "erro": "x", "aviso": "!", "seta": "->"}
except (AttributeError, ValueError):
    SIMBOLOS = {"ok": "[ok]", "erro": "[erro]", "aviso": "[!]", "seta": "->"}


def cor(texto, codigo):
    """Cor no terminal (some se nao suportado)."""
    return f"\033[{codigo}m{texto}\033[0m"


def erro(mensagem):
    print(cor(f"{SIMBOLOS['erro']} {mensagem}", 31))


def aviso(mensagem):
    print(cor(f"{SIMBOLOS['aviso']} {mensagem}", 33))


def ok(mensagem):
    print(cor(f"{SIMBOLOS['ok']} {mensagem}", 32))


def info(mensagem):
    print(f"  {mensagem}")


def conferir_python():
    """Verifica se o Python instalado serve."""
    if sys.version_info < VERSAO_MINIMA:
        erro(f"Python {VERSAO_MINIMA[0]}.{VERSAO_MINIMA[1]}+ e necessario.")
        erro(f"Voce esta usando {sys.version_info.major}.{sys.version_info.minor}")
        print()
        print("  Instale o Python:")
        print("    Windows: https://www.python.org/downloads/")
        print("    Mac:     brew install python    (ou https://www.python.org/downloads/)")
        print("    Linux:   sudo apt install python3 python3-venv")
        return False
    return True


def criar_venv():
    """Cria o ambiente virtual se ainda nao existir."""
    if PYTHON_VENV.exists():
        info("Ambiente virtual ja existe.")
        return True

    info("Criando ambiente virtual...")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True,
        )
    except subprocess.CalledProcessError:
        erro("Falha ao criar o ambiente virtual.")
        aviso("No Ubuntu/Debian, instale: sudo apt install python3-venv")
        return False

    ok(f"Ambiente criado em {VENV}")
    return True


def instalar_dependencias():
    """Instala o que esta em requirements.txt."""
    if not REQUISITOS.exists():
        erro(f"requirements.txt nao encontrado em {REQUISITOS}")
        return False

    info("Instalando dependencias (pode demorar alguns minutos)...")
    try:
        subprocess.run(
            [str(PYTHON_VENV), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        aviso("Nao deu para atualizar o pip, seguindo mesmo assim.")

    try:
        resultado = subprocess.run(
            [str(PYTHON_VENV), "-m", "pip", "install", "-r", str(REQUISITOS)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        erro("Falha ao instalar as dependencias.")
        saida = getattr(exc, "stdout", "") or ""
        print(saida[-800:])
        return False

    ok("Dependencias instaladas.")
    return True


def conferir_versao_streamlit():
    """Confere se a versao instalada bate com a do requirements."""
    if not PYTHON_VENV.exists():
        aviso("Ambiente virtual ainda nao foi criado.")
        return False

    try:
        resultado = subprocess.run(
            [str(PYTHON_VENV), "-c",
             "import streamlit; print(streamlit.__version__)"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        aviso("Streamlit demorou demais para responder.")
        return False
    except subprocess.CalledProcessError as exc:
        erro("Nao consegui importar o Streamlit.")
        detalhe = (exc.stderr or "").strip().splitlines()
        if detalhe:
            print(f"  {detalhe[-1]}")
        return False
    except OSError as exc:
        erro(f"Falha ao executar o Python do ambiente: {exc}")
        return False

    versao = (resultado.stdout or "").strip()
    if versao:
        ok(f"Streamlit {versao}")
        return True

    aviso("Nao consegui ler a versao do Streamlit.")
    return False


def rodar():
    """Sobe o sistema."""
    url = "http://localhost:8501"
    print()
    print(cor("=" * 58, 36))
    print(cor("  SISTEMA DE ENCAMINHAMENTO DE ALUNOS", 36))
    print(cor("=" * 58, 36))
    print()
    ok(f"Iniciando... abra no navegador: {url}")
    print(cor("  Para encerrar, pressione Ctrl+C", 33))
    print()

    ambiente = os.environ.copy()
    subprocess.run(
        [str(PYTHON_VENV), "-m", "streamlit", "run",
         str(RAIZ / "encaminhamento" / "app.py"),
         "--server.port", "8501",
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        env=ambiente,
    )


def main():
    analisador = argparse.ArgumentParser(description="Instalador do sistema")
    analisador.add_argument("--run", action="store_true",
                            help="instala e ja inicia o sistema")
    analisador.add_argument("--check", action="store_true",
                            help="apenas verifica o que falta")
    args = analisador.parse_args()

    print()
    print(cor("Instalador - Sistema de Encaminhamento de Alunos", 36))
    print(cor("=" * 58, 36))
    print()
    info(f"Sistema  : {platform.system()} {platform.machine()}")
    info(f"Python   : {sys.version.split()[0]}")
    info(f"Pasta    : {RAIZ}")
    print()

    if not conferir_python():
        sys.exit(1)

    if not criar_venv():
        sys.exit(1)

    if args.check:
        if not PYTHON_VENV.exists():
            aviso("Falta instalar as dependencias.")
            sys.exit(1)
        if conferir_versao_streamlit():
            ok("Tudo pronto.")
            sys.exit(0)
        aviso("Rode a instalacao completa para corrigir.")
        sys.exit(1)

    if not instalar_dependencias():
        sys.exit(1)

    conferir_versao_streamlit()
    ok("Instalacao concluida!")

    if args.run:
        rodar()
        return

    print()
    try:
        resposta = input("Iniciar o sistema agora? (s/N) ").strip().lower()
    except EOFError:
        # Sem entrada interativa (instalacao automatizada)
        resposta = ""

    if resposta in ("s", "sim", "y", "yes"):
        rodar()
    else:
        print()
        info("Para iniciar depois, use:")
        if platform.system() == "Windows":
            info("  iniciar.bat")
        else:
            info("  bash iniciar.sh")


if __name__ == "__main__":
    main()