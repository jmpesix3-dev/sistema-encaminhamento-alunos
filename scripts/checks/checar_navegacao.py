"""Verifica importacao e as rotas de navegacao do painel."""
import ast
import importlib
import pathlib

print("1. Importando paginas...")
for p in sorted(pathlib.Path("encaminhamento/ui/pages").glob("_*.py")):
    nome = p.stem
    try:
        importlib.import_module(f"encaminhamento.ui.pages.{nome}")
        print(f"   OK   {nome}")
    except Exception as e:
        print(f"   FALHA {nome}: {type(e).__name__}: {e}")

print()
print("2. Verificando rotas de navegacao...")
comp = importlib.import_module("encaminhamento.ui.components")

# ir_para existe?
print(f"   ir_para: {callable(getattr(comp, 'ir_para', None))}")

# school_selector aceita filtro_id?
import inspect
sig = inspect.signature(comp.school_selector)
print(f"   school_selector tem filtro_id: {'filtro_id' in sig.parameters}")

# paginas leem as chaves ir_*?
esperadas = {
    "_01_Dashboard": [],
    "_02_Alunos": ["ir_aba", "ir_aluno_status", "ir_destino"],
    "_03_Escolas": ["ir_capacidade", "ir_localizacao", "ir_dados", "ir_mapa_escola"],
    "_05_Batch_Management": ["ir_lote_status"],
    "_06_Automation": ["ir_email"],
    "_07_Auto_Allocation": ["ir_alocacao"],
}
for nome, chaves in esperadas.items():
    src = pathlib.Path(f"encaminhamento/ui/pages/{nome}.py").read_text(encoding="utf-8")
    faltando = [c for c in chaves if c not in src]
    estado = "OK" if not faltando else f"faltando {faltando}"
    print(f"   {nome:<22} {estado}")

print()
print("3. Verificando o painel...")
dash = pathlib.Path("encaminhamento/ui/pages/_01_Dashboard.py").read_text(encoding="utf-8")
for item in ["_passos", "_pendencias", "_indicadores", "_situacao", "_escolas_atencao", "_exportar"]:
    print(f"   {item:<20} {'OK' if item in dash else 'AUSENTE'}")

print()
print("4. Verificando o relatorio...")
rel = pathlib.Path("encaminhamento/services/relatorio.py").read_text(encoding="utf-8")
print(f"   9 pendencias definidas: {rel.count('Pendencia(') >= 9}")
print(f"   exportacao: {'exportar_resumo' in rel}")
