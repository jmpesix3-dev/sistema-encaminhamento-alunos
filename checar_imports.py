"""Lista imports nao usados nos arquivos ja alterados."""
import ast
import pathlib

ALVOS = [
    "encaminhamento/services/status_tracker.py",
    "encaminhamento/services/relatorio.py",
    "encaminhamento/ui/components.py",
    "encaminhamento/services/allocation.py",
    "encaminhamento/services/excel_export.py",
    "encaminhamento/utils/helpers.py",
    "encaminhamento/database/crud.py",
    "encaminhamento/utils/status.py",
    "encaminhamento/utils/geo.py",
    "encaminhamento/services/geocoding.py",
    "encaminhamento/services/pdf_generator.py",
    "encaminhamento/services/excel_import.py",
]

for alvo in ALVOS:
    caminho = pathlib.Path(alvo)
    if not caminho.exists():
        print(f"{caminho.name:<24} ARQUIVO NAO EXISTE")
        continue

    src = caminho.read_text(encoding="utf-8")
    arvore = ast.parse(src)

    importados = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            for x in no.names:
                importados[x.asname or x.name] = no.lineno
        elif isinstance(no, ast.Import):
            for x in no.names:
                nome = (x.asname or x.name).split(".")[0]
                importados[nome] = no.lineno

    usados = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
    usados |= {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
    usados |= {
        n.value.id for n in ast.walk(arvore)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
    }

    mortos = [
        f"{nome}(linha {linha})"
        for nome, linha in sorted(importados.items(), key=lambda kv: kv[1])
        if nome not in usados
    ]
    print(f"{caminho.name:<24} {mortos if mortos else 'nenhum'}")
