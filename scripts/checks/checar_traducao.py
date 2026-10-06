"""Confere que nenhum status em ingles aparece na tela."""
import re
import pathlib

INGLES = [
    "draft", "pending", "sent", "confirmed", "cancelled",
    "generated", "completed",
]

print("1. Arquivos que ainda podem exibir status cru\n")

alvos = sorted(pathlib.Path("encaminhamento/ui").rglob("*.py"))
problemas = []

for caminho in alvos:
    src = caminho.read_text(encoding="utf-8")
    for n, linha in enumerate(src.splitlines(), 1):
        # procura .value ou .upper() de status
        for padrao in [r"status\.value", r"\.status\.value", r"\{s\.value\}",
                       r"\[s\.value for s in", r"status\.value\.upper"]:
            if re.search(padrao, linha):
                problemas.append(f"{caminho.name}:{n}  {linha.strip()[:78]}")
                break

if problemas:
    for p in problemas:
        print("   " + p)
else:
    print("   Nenhum uso direto de .value de status.")

print()
print("2. Funcao de traducao")
sys_mod = pathlib.Path("encaminhamento/utils/status.py")
if sys_mod.exists():
    src = sys_mod.read_text(encoding="utf-8")
    for fn in ["rotulo_aluno", "rotulo_lote", "para_valor_aluno", "para_valor_lote",
               "opcoes_aluno", "opcoes_lote"]:
        print(f"   {'OK  ' if f'def {fn}' in src else 'FALHA'} {fn}")
else:
    print("   FALHA: utils/status.py nao existe")

print()
print("3. Testando a traducao")
import sys
sys.path.insert(0, ".")
from encaminhamento.utils.status import (
    rotulo_aluno, rotulo_lote, para_valor_aluno, para_valor_lote,
    opcoes_aluno, opcoes_lote, ORDEM_ALUNO, ORDEM_LOTE,
)

for v in ORDEM_ALUNO:
    r = rotulo_aluno(v)
    b = para_valor_aluno(r)
    print(f"   aluno {v:<10} -> {r:<12} -> volta: {b.value if b else None}")

print()
for v in ORDEM_LOTE:
    r = rotulo_lote(v)
    b = para_valor_lote(r)
    print(f"   lote  {v:<10} -> {r:<12} -> volta: {b.value if b else None}")

print()
print(f"   opcoes_aluno(): {opcoes_aluno()}")
print(f"   opcoes_lote():  {opcoes_lote()}")
