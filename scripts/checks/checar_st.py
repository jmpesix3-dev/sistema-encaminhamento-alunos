"""
Confere se as APIs do Streamlit usadas nas paginas existem nesta versao.
"""
import ast
import inspect
import pathlib
import re

import streamlit as st

print(f"Streamlit {st.__version__}\n")

# Metodos/widgets do Streamlit citados nas paginas
alvos = sorted(pathlib.Path("encaminhamento/ui/pages").glob("_*.py"))

metodos = set()
for p in alvos:
    src = p.read_text(encoding="utf-8")
    for m in re.finditer(r"\bst\.(\w+)\(", src):
        metodos.add(m.group(1))

print("1. Widgets usados e se existem")
faltando = []
for nome in sorted(metodos):
    existe = hasattr(st, nome)
    if not existe:
        faltando.append(nome)
    print(f"   {'OK  ' if existe else 'FALHA'} st.{nome}")

print()
print("2. Parametros usados")
# casos conhecidos que quebram entre versoes
casos = {
    "tabs": ["index"],
    "progress": ["color"],
    "dataframe": ["use_container_width", "hide_index", "column_config"],
    "data_editor": ["use_container_width", "hide_index", "column_config"],
    "button": ["use_container_width", "type"],
    "selectbox": ["format_func", "key"],
    "text_input": ["type", "placeholder", "key"],
    "metric": ["delta", "delta_color", "help"],
    "download_button": ["use_container_width", "mime"],
    "segmented_control": ["default", "selection_mode", "label_visibility", "key"],
    "expander": ["expanded"],
    "map": ["size", "latitude", "longitude"],
}

# so checa o parametro se ele realmente aparece na pagina
print("2. Parametros usados (só os que aparecem no codigo)")
problemas_param = []
for widget, params in casos.items():
    fn = getattr(st, widget, None)
    if fn is None:
        continue
    try:
        assinatura = inspect.signature(fn)
    except (TypeError, ValueError):
        continue
    aceita_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in assinatura.parameters.values()
    )
    for param in params:
        usado = False
        for p in alvos:
            if re.search(rf"st\.{widget}\([^)]*\b{param}\s*=", p.read_text(encoding="utf-8"), re.S):
                usado = True
                break
        if not usado:
            continue
        ok = param in assinatura.parameters or aceita_kwargs
        if not ok:
            problemas_param.append(f"st.{widget}({param}=...)")
        print(f"   {'OK  ' if ok else 'FALHA'} st.{widget}(... {param}=...)")

print()
print("3. Resumo")
if faltando:
    print("   Widgets inexistentes: " + ", ".join(faltando))
else:
    print("   Todos os widgets usados existem.")
if problemas_param:
    print("   Parametros incompatíveis: " + ", ".join(problemas_param))
else:
    print("   Todos os parametros usados sao aceitos.")
