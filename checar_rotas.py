"""
Confere que toda chave ir_* gerada no painel e lida na pagina de destino.

As chamadas ir_para(pagina, **estado) usam variaveis, entao as chaves sao
resolvidas lendo PASSOS e Pendencia.estado.
"""
import importlib
import pathlib
import re

print("1. ir_para aplica o prefixo")
comp = pathlib.Path("encaminhamento/ui/components.py").read_text(encoding="utf-8")
print(f"   usa f\"ir_{{chave}}\": {bool(re.search(r'f.ir_.chave.', comp))}")
print()

# ----------------------------------------------------------------------
# Chaves geradas
# ----------------------------------------------------------------------
geradas = {}

rel = importlib.import_module("encaminhamento.services.relatorio")
resumo = rel.montar_resumo()

for p in resumo.pendencias:
    for chave in p.estado:
        geradas.setdefault(f"ir_{chave}", set()).add(f"{p.pagina} (pendencia: {p.chave})")

dash = pathlib.Path("encaminhamento/ui/pages/_01_Dashboard.py").read_text(encoding="utf-8")
mod = importlib.import_module("encaminhamento.ui.pages._01_Dashboard")

for numero, titulo, desc, pagina, estado in mod.PASSOS:
    for chave in estado:
        geradas.setdefault(f"ir_{chave}", set()).add(f"{pagina} (passo {numero})")

# chamadas literais: ir_para("Escolas", dados=True)
for m in re.finditer(r'ir_para\(\s*"(\w+)"\s*,\s*(\w+)\s*=', dash):
    pagina, chave = m.group(1), m.group(2)
    geradas.setdefault(f"ir_{chave}", set()).add(f"{pagina} (direto)")

print("2. Chaves geradas no painel")
for chave, origens in sorted(geradas.items()):
    print(f"   {chave:<20} {', '.join(sorted(origens))}")

# ----------------------------------------------------------------------
# Chaves lidas
# ----------------------------------------------------------------------
lidas = {}
for p in sorted(pathlib.Path("encaminhamento/ui/pages").glob("_*.py")):
    for chave in re.findall(r'pop\("(ir_\w+)"', p.read_text(encoding="utf-8")):
        lidas.setdefault(chave, set()).add(p.stem)

print()
print("3. Chaves lidas no destino")
for chave, paginas in sorted(lidas.items()):
    print(f"   {chave:<20} {', '.join(sorted(paginas))}")

# ----------------------------------------------------------------------
print()
print("4. Conference")
nao_lidas = sorted(set(geradas) - set(lidas))
nao_geradas = sorted(set(lidas) - set(geradas))

print(f"   geradas: {len(geradas)} | lidas: {len(lidas)}")
print(f"   geradas e nao lidas: {nao_lidas if nao_lidas else 'nenhuma'}")
print(f"   lidas e nao geradas: {nao_geradas if nao_geradas else 'nenhuma'}")
print()
print("   OK - todas as rotas fecham" if not nao_lidas and not nao_geradas
      else "   DIVERGENCIA")
