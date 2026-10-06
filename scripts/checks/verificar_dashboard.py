"""Verifica se o painel esta lendo dados atualizados do DB real."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest

at = AppTest.from_file("encaminhamento/app.py", default_timeout=30)
at.run()

if at.exception:
    print(f"Exception: {at.exception}")
else:
    print("App loaded OK")

# Collect all string values
all_values = []
for elem in at:
    try:
        val = str(elem.value)
        all_values.append(val)
    except Exception:
        pass

combined = " ".join(all_values)

# Check for key indicators
checks = [
    ("107 students", "107" in combined),
    ("71 allocated", "71" in combined),
    ("36 sem vaga", "36" in combined),
    ("Painel de Controle title", "Painel de Controle" in combined),
    ("Pendencias section", "Pend" in combined),
]

for label, found in checks:
    status = "OK" if found else "MISSING"
    print(f"  [{status}] {label}")

if all(c[1] for c in checks):
    print("\nDashboard reads fresh data correctly after auto-update")
else:
    print(f"\nTotal elements: {len(all_values)}")
