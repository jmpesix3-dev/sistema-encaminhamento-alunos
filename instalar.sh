#!/usr/bin/env bash
# ===========================================================================
#  Instalador - Encaminhamento Escolar de Alunos (macOS e Linux)
#
#  Este script cria o ambiente virtual, instala as dependencias e
#  sobe o sistema.
#
#  DCLICK neste arquivo, ou rode:  bash instalar.sh
#
#  O Python NAO e instalado automaticamente aqui: no Mac e no Linux a
#  instalacao pede a senha de administrador. Se faltar, o script mostra
#  o comando exato para o seu sistema.
# ===========================================================================

set -e

cd "$(dirname "$0")"

echo ""
echo "=============================================================="
echo "  SISTEMA DE ENCAMINHAMENTO DE ALUNOS"
echo "  Instalacao"
echo "=============================================================="
echo ""

# Procura um Python 3.10 ou mais novo
PY=""
for candidato in python3.12 python3.13 python3.14 python3 python; do
    if command -v "$candidato" >/dev/null 2>&1; then
        if "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            PY="$candidato"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "  Python 3.10 ou mais novo nao encontrado."
    echo ""
    echo "  Instale antes de continuar:"
    echo ""
    if [ "$(uname)" = "Darwin" ]; then
        echo "    Homebrew (recomendado):  brew install python"
        echo "    Ou baixe em:             https://www.python.org/downloads/"
    else
        echo "    Ubuntu/Debian:  sudo apt install python3 python3-venv"
        echo "    Fedora/RHEL:    sudo dnf install python3"
        echo "    Ou baixe em:    https://www.python.org/downloads/"
    fi
    echo ""
    read -r -p "  Pressione ENTER para sair."
    exit 1
fi

echo "  Python encontrado: $($PY --version 2>&1)"
echo ""

exec "$PY" instalar.py "$@"