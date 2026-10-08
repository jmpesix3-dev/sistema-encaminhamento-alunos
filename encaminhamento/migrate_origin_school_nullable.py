"""
Migration: torna origin_school_id nullable em forwarding_batches.

Uso (servidor parado):
    python migrate_origin_school_nullable.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, text
from encaminhamento.config import DATA_DIR

db_path = DATA_DIR / "encaminhamento.db"
engine = create_engine(f"sqlite:///{db_path}", pool_pre_ping=True)

print(f"Migrando banco: {db_path}")

with engine.connect() as conn:
    conn.execute(text("PRAGMA foreign_keys=off"))
    conn.execute(text("BEGIN TRANSACTION"))

    conn.execute(text("ALTER TABLE forwarding_batches RENAME TO forwarding_batches_old"))

    conn.execute(text("""
        CREATE TABLE forwarding_batches (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            origin_school_id INTEGER NULL,
            destination_school_id INTEGER NOT NULL,
            origin_class_id INTEGER NULL,
            year INTEGER NOT NULL,
            student_count INTEGER DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            pdf_path VARCHAR(500) NULL,
            sent_at DATETIME NULL,
            notes TEXT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(origin_school_id) REFERENCES schools (id),
            FOREIGN KEY(destination_school_id) REFERENCES schools (id),
            FOREIGN KEY(origin_class_id) REFERENCES classes (id)
        )
    """))

    conn.execute(text("""
        INSERT INTO forwarding_batches
        (id, origin_school_id, destination_school_id, origin_class_id, year,
         student_count, status, pdf_path, sent_at, notes, created_at, updated_at)
        SELECT id, origin_school_id, destination_school_id, origin_class_id, year,
               student_count, status, pdf_path, sent_at, notes, created_at, updated_at
        FROM forwarding_batches_old
    """))

    conn.execute(text("DROP TABLE forwarding_batches_old"))
    conn.execute(text("COMMIT"))
    conn.execute(text("PRAGMA foreign_keys=on"))

print("Migration aplicada com sucesso.")
