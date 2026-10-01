#!/usr/bin/env bash
# Instalador - Sistema de Encaminhamento de Alunos
# macOS e Linux. DCLICK neste arquivo ou rode: bash instalar.sh

set -e

cd "$(dirname "$0")"

# Procura o Python
for candidato in python3 python; do
    if command -v "$candidato" >/dev/null 2>&1; then
        PY="$candidato"
        break
    fi
done

if [ -z "$PY" ]; then
    echo ""
    echo "  Python nao encontrado."
    echo ""
    echo "  Instale antes de continuar:"
    echo "    macOS  : brew install python"
    echo "    Ubuntu : sudo apt install python3 python3-venv"
    echo "    outros : https://www.python.org/downloads/"
    echo ""
    read -r -p "  Pressione ENTER para sair."
    exit 1
fi

echo ""
exec "$PY" instalar.py "$@"