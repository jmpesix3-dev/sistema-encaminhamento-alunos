"""
Aplica migracoes no banco: adiciona colunas novas sem perder os dados existentes.
"""
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).parent))

from encaminhamento.database import init_db, engine


# Colunas novas por tabela: tabela -> [(coluna, tipo_sql)]
MIGRACOES = {
    "schools": [
        ("distrito", "VARCHAR(50)"),
        ("modalidade", "VARCHAR(100)"),
        ("contato", "VARCHAR(200)"),
    ],
    "students": [
        ("latitude", "FLOAT"),
        ("longitude", "FLOAT"),
        ("allocated_school_id", "INTEGER"),
        ("allocation_status", "VARCHAR(20) DEFAULT 'pending'"),
        ("allocation_priority", "INTEGER"),
    ],
    "classes": [
        ("shift", "VARCHAR(20)"),
    ],
}


def main():
    init_db()  # garante que tabelas novas existam

    insp = inspect(engine)
    tabelas = insp.get_table_names()

    with engine.begin() as conn:
        for tabela, colunas in MIGRACOES.items():
            if tabela not in tabelas:
                print(f"[pula] tabela '{tabela}' nao existe")
                continue

            existentes = {c["name"] for c in insp.get_columns(tabela)}

            for coluna, tipo in colunas:
                if coluna in existentes:
                    continue
                conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}"))
                print(f"[+] {tabela}.{coluna} ({tipo})")

    print("\nMigracao concluida.")


if __name__ == "__main__":
    main()
