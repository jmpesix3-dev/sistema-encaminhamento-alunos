"""
Cria os arquivos de teste das paginas.

O AppTest do Streamlit roda um arquivo, entao geramos um arquivo temporario
por pagina que apenas chama o render(). Isso evita versionar seis arquivos
com caminho fixo, que quebrariam em outro computador.
"""
import shutil
from pathlib import Path

RAIZ = Path(__file__).parent
PASTA = RAIZ / "_testes_paginas"

# nome de atalho -> modulo da pagina
PAGINAS = {
    "painel": "_01_Dashboard",
    "alunos": "_02_Alunos",
    "escolas": "_03_Escolas",
    "lotes": "_05_Batch_Management",
    "automacao": "_06_Automation",
    "alocacao": "_07_Auto_Allocation",
    "atualizacao": "_08_Atualizacao",
}

CONTEUDO = """import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from encaminhamento.ui.pages.{modulo} import render

render()
"""


def gerar():
    """(Re)cria os arquivos de teste. Devolve {atalho: caminho}."""
    PASTA.mkdir(exist_ok=True)
    caminhos = {}
    for atalho, modulo in PAGINAS.items():
        destino = PASTA / f"{atalho}.py"
        destino.write_text(CONTEUDO.format(modulo=modulo), encoding="utf-8")
        caminhos[atalho] = destino
    return caminhos


def limpar():
    """Remove os arquivos gerados."""
    shutil.rmtree(PASTA, ignore_errors=True)


if __name__ == "__main__":
    for atalho, caminho in gerar().items():
        print(f"{atalho:<10} {caminho}")