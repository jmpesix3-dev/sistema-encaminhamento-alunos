"""
Roda cada pagina do app de verdade e reporta as excecoes.

Usa o AppTest do proprio Streamlit, que renderiza a pagina sem
precisar de navegador.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

import traceback

from streamlit.testing.v1 import AppTest

from gerar_arquivos_teste import gerar, limpar

ROTULOS = {
    "painel": "Painel",
    "alunos": "Alunos",
    "escolas": "Escolas",
    "lotes": "Lotes",
    "automacao": "Automacao",
    "alocacao": "Alocacao",
    "atualizacao": "Atualizacao",
}

falhas = 0
arquivos = gerar()

try:
    for atalho, rotulo in ROTULOS.items():
        print(f"--- {rotulo} ---")
        try:
            at = AppTest.from_file(str(arquivos[atalho]), default_timeout=60)
            at.run()

            if at.exception:
                falhas += 1
                for exc in at.exception:
                    print(f"   ERRO: {exc.value}")
                    print(f"   {exc.type}")
            else:
                print("   OK")
        except Exception as e:
            falhas += 1
            print(f"   ERRO ao rodar: {type(e).__name__}: {e}")
        print()
finally:
    limpar()

print(f"paginas com erro: {falhas}")