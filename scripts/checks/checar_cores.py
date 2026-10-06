"""
Procura cores fixas no HTML/CSS que quebram quando o tema muda.

Texto com cor fixa sobre fundo desconhecido fica invisivel: foi o que
escondeu o nome do sistema e os cartoes de metrica.
"""
import re
from pathlib import Path

# cinzas claros que somem sobre fundo escuro
CINZAS_ESCUROS = re.compile(
    r"#(f0f2f6|eef1f6|e8eaed|f1f3f4|f5f6f8|eceff4|5a6472|6b7684|7d8797|8a94a6|98a2b3|a8b0bd)",
    re.IGNORECASE,
)

ARQUIVOS = sorted(
    list(Path("encaminhamento").rglob("*.py"))
    + list(Path(".").glob("*.py"))
)

achados = 0
for caminho in ARQUIVOS:
    if "venv" in str(caminho):
        continue
    try:
        src = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue

    for n, linha in enumerate(src.splitlines(), 1):
        txt = linha.strip()
        # comentario de linha (python) ou de bloco (css)
        if txt.startswith("#") or txt.startswith("*") or txt.startswith("/*"):
            continue
        if txt.endswith("*/") and "/*" not in txt:
            continue
        # linhas que comentam sobre o proprio problema sao ignoradas
        if "deixaria" in txt or "ex.:" in txt or "fixo" in txt:
            continue
        # o achado precisa estar em style="..." ou num bloco CSS real
        if "style=" not in linha and "{" not in txt:
            continue
        if CINZAS_ESCUROS.search(linha):
            print(f"  {caminho}:{n}  {txt[:88]}")
            achados += 1

print()
print(f"{achados} cor(es) fixa(s) suspeita(s) de sumir no tema escuro")
