#!/usr/bin/env bash
# Inicia o sistema (sem reinstalar) - macOS e Linux
# Rode: bash iniciar.sh    ou    ./iniciar.sh

cd "$(dirname "$0")"

# Dentro do venv se existir
if [ -x "venv/bin/python" ]; then
    PY="venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    PY="python"
fi

if [ ! -x "venv/bin/python" ]; then
    echo ""
    echo "  Ainda nao instalado."
    echo "  Rode: bash instalar.sh"
    echo ""
    exit 1
fi

echo ""
echo "  Iniciando... abra http://localhost:8501"
echo "  Para encerrar, pressione Ctrl+C"
echo ""

exec "$PY" -m streamlit run encaminhamento/app.py \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false