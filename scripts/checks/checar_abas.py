"""Confere o dispatch das abas em cada pagina."""
import ast
import pathlib
import re

print("1. Nenhum uso de st.tabs com index")
alvos = sorted(pathlib.Path("encaminhamento/ui/pages").glob("_*.py"))
problemas = []
for p in alvos:
    src = p.read_text(encoding="utf-8")
    for m in re.finditer(r"st\.tabs\(([^)]*)\)", src):
        args = m.group(1)
        if "index" in args:
            problemas.append(f"{p.name}: st.tabs({args[:50]})")
        print(f"   {p.name:<22} st.tabs({args[:40]})")

print()
if problemas:
    print("   PROBLEMAS:")
    for x in problemas:
        print("     " + x)
else:
    print("   OK - nenhuma aba usa index")

print()
print("2. Dispatch por indice")
for p in alvos:
    src = p.read_text(encoding="utf-8")
    if "seletor_abas" not in src:
        continue
    ifs = re.findall(r"if escolhida == (\d+):", src)
    elifs = re.findall(r"elif escolhida == (\d+):", src)
    tem_with = len(re.findall(r"with tab\d?:", src))
    todos = sorted({int(x) for x in ifs + elifs})
    print(f"   {p.stem:<22} indices {todos} | blocos 'with tab' restantes: {tem_with}")

print()
print("3. Import de seletor_abas")
for p in alvos:
    src = p.read_text(encoding="utf-8")
    usa = "seletor_abas(" in src
    importa = "seletor_abas" in src.split("\n\n")[0] or re.search(
        r"from encaminhamento\.ui\.components import[^\n]*seletor_abas", src, re.S
    )
    if usa:
        print(f"   {p.stem:<22} usa={usa} importa={bool(importa)}")
