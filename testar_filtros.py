"""Interage com os filtros de cada pagina para achar erro de runtime."""
from streamlit.testing.v1 import AppTest

print("=== Lotes: filtro de ano (lista com tipos mistos) ===")
at = AppTest.from_file("encaminhamento/ui/pages/_05_Batch_Management.py", default_timeout=60)
at.run()

ano = at.selectbox(key="batch_filter_year")
print(f"   opcoes: {ano.options}")
print(f"   tipos:  {[type(o).__name__ for o in ano.options]}")

try:
    ano.select(1)
    at.run()
    if at.exception:
        for exc in at.exception:
            print(f"   ERRO: {exc.value}")
    else:
        print("   OK ao selecionar 2020")
except Exception as e:
    print(f"   ERRO ao selecionar: {type(e).__name__}: {e}")

print()
print("=== Lotes: filtro de escola (dict vs objeto) ===")
at2 = AppTest.from_file("encaminhamento/ui/pages/_05_Batch_Management.py", default_timeout=60)
at2.run()
try:
    origem = at2.selectbox(key="batch_filter_origin")
    print(f"   opcoes: {len(origem.options)}")
    if len(origem.options) > 1:
        origem.select(1)
        at2.run()
        if at2.exception:
            for exc in at2.exception:
                print(f"   ERRO: {exc.value}")
        else:
            print("   OK ao selecionar escola de origem")
except Exception as e:
    print(f"   ERRO: {type(e).__name__}: {e}")
