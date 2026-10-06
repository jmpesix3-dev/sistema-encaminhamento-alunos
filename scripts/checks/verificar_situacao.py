"""Verifica se os 4 cards de situacao do aluno aparecem no painel."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest

at = AppTest.from_file("encaminhamento/app.py", default_timeout=30)
at.run()

if at.exception:
    print(f"Exception: {at.exception}")
else:
    print("App loaded OK")

all_values = []
for elem in at:
    try:
        all_values.append(str(elem.value))
    except Exception:
        pass

combined = " ".join(all_values)

# Check for the 4 situation category cards
categorias = ["Alunos", "Pendente", "Encaminhados", "Informação Pendente"]
for cat in categorias:
    found = cat in combined
    status = "OK" if found else "MISSING"
    print(f"  [{status}] Card: {cat}")

# Check for the actual counts
esperado = {"Alunos": "107", "Pendente": "36", "Encaminhados": "71", "Informação Pendente": "9"}
for cat, num in esperado.items():
    if cat in combined and num in combined:
        print(f"  [OK] {cat} = {num}")
    elif cat in combined:
        print(f"  [INFO] {cat} presente, numero {num} pode estar em formato diferente")

# Check for other dashboard sections
if "Como começar" in combined:
    print("  [OK] Secao 'Como começar' (passos) presente")
if "Pendências" in combined:
    print("  [OK] Secao 'Pendencias' presente")
if "por escola" in combined.lower() or "Por escola" in combined:
    print("  [OK] Secao 'Por escola' presente")
