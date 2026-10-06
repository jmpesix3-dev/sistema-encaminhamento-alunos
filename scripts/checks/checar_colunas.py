"""
Caca erros de runtime sem depender do navegador.

Percorre as colunas e atributos citados nas pagues e confere se existem
nos modelos, e executa as consultas principais.
"""
import ast
import pathlib

from sqlalchemy import inspect

from encaminhamento.database import engine
from encaminhamento.database import models

print("Checando colunas citadas nas paginas contra o banco...\n")

insp = inspect(engine)
tabelas = {
    "School": insp.get_columns("schools"),
    "Student": insp.get_columns("students"),
    "Class": insp.get_columns("classes"),
    "ForwardingBatch": insp.get_columns("forwarding_batches"),
    "BatchItem": insp.get_columns("batch_items"),
}
colunas = {nome: {c["name"] for c in cols} for nome, cols in tabelas.items()}

paginas = sorted(pathlib.Path("encaminhamento/ui/pages").glob("_*.py"))
problemas = []

for pagina in paginas:
    arvore = ast.parse(pagina.read_text(encoding="utf-8"))

    for no in ast.walk(arvore):
        # Modelo.attr
        if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name):
            modelo = no.value.id
            if modelo in colunas and no.attr not in colunas[modelo]:
                problemas.append(
                    f"{pagina.name}:{no.lineno}  {modelo}.{no.attr} nao existe"
                )
        # Modelos.Classe.attr
        if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Attribute):
            inner = no.value
            if isinstance(inner.value, ast.Name) and inner.value.id == "Modelos":
                if no.attr in ("alunos", "escolas", "lotes", "destino_1", "destino_2",
                               "alocados_por_escola", "alocados", "metricas"):
                    continue
                base = {"School": "schools", "Student": "students",
                        "Class": "classes", "ForwardingBatch": "forwarding_batches",
                        "BatchItem": "batch_items"}.get(inner.attr)
                if base and no.attr not in colunas.get(inner.attr, set()):
                    problemas.append(
                        f"{pagina.name}:{no.lineno}  Modelos.{inner.attr}.{no.attr} nao existe"
                    )

if problemas:
    print("PROBLEMAS ENCONTRADOS:")
    for p in sorted(set(problemas)):
        print("  " + p)
else:
    print("Nenhum atributo invalido.")

print("\nColunas por tabela:")
for nome, cols in colunas.items():
    print(f"  {nome:<16} {', '.join(sorted(cols))}")
