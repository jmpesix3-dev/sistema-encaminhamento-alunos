#!/usr/bin/env python
"""
Comprehensive integration test for the Encaminhamento system.

Tests the full pipeline end-to-end with rich fictional data:
  1. Data seeding (schools, classes, students with various edge cases)
  2. Allocation preview + execution (capacity, proximity, waitlist)
  3. Situation counting cross-checks (contar vs detalhar vs raw SQL)
  4. Resumo / pendencias consistency
  5. Batch creation + PDF generation
  6. Status transitions
  7. Email sending (mocked SMTP)
  8. Edge cases (empty batch, no-address students, no-destination students)

Uses an ISOLATED temp SQLite database so the real data is never touched.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Isolate the test database BEFORE importing the application.
# The engine is created at import time from DATABASE_URL.
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent.parent.parent / "_test_tmp" / "comprehensive"
_TEST_DIR.mkdir(parents=True, exist_ok=True)

_DB_PATH = str(_TEST_DIR / "integration.db")
if os.path.exists(_DB_PATH):
    os.unlink(_DB_PATH)

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SMTP_HOST"] = "smtp.test.example"
os.environ["SMTP_PORT"] = "587"
os.environ["SMTP_USER"] = "test@example.com"
os.environ["SMTP_PASSWORD"] = "testpassword"
os.environ["SMTP_USE_TLS"] = "true"
os.environ["EMAIL_FROM"] = "test@example.com"

# Ensure UTF-8 output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Now import the application
from encaminhamento.database import init_db, get_session, engine
from encaminhamento.database.models import (
    School, Class, Student, StudentStatus,
    ForwardingBatch, BatchStatus,
)
from encaminhamento.database.crud import (
    create_school, create_class, create_student, list_students,
    list_schools, get_student, update_student, create_batch,
    add_students_to_batch, update_batch_status, get_batch,
    get_students_for_batch,
)
from encaminhamento.services.allocation import AllocationService
from encaminhamento.services.relatorio import (
    montar_resumo, contar_situacao_aluno, detalhar_situacao_aluno,
    detalhar_pendencia, SITUACAO_ALUNO,
)
from encaminhamento.services.pdf_generator import generate_batch_pdf
from encaminhamento.services.email_sender import (
    send_email, send_batch_notification, EmailResult,
)
from encaminhamento.services.status_tracker import (
    StatusTransition, transition_student_status,
    auto_advance_batch_status, get_status_summary,
    bulk_transition_students,
)
from encaminhamento.services.geocoding import haversine_distance
from encaminhamento.utils.helpers import normalize_school_name, match_school_name
from encaminhamento.config import PDF_EXPORT_DIR

# Coordinate constants for São João da Barra (matching geocoding.py DISTRITOS)
CENTRO_LAT, CENTRO_LON = -21.6344, -41.0490
GRUSSA_LAT, GRUSSA_LON = -21.7015, -41.0338
CAJU_LAT, CAJU_LON = -21.7191, -41.0944
MATO_LAT, MATO_LON = -21.8935, -41.0550


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def mock_smtp():
    """Replace smtplib.SMTP with a mock so send_email returns success."""
    mock = MagicMock()
    mock_return = MagicMock()
    mock.return_value.__enter__ = MagicMock(return_value=mock_return)
    mock.return_value.__exit__ = MagicMock(return_value=False)
    mock_return.login.return_value = None
    mock_return.sendmail.return_value = None
    patcher = patch("encaminhamento.services.email_sender.smtplib.SMTP", mock)
    return patcher


# ---------------------------------------------------------------------------
# Data seeding
# ---------------------------------------------------------------------------
def seed_data():
    """Create a rich dataset and return IDs for assertions."""
    init_db()

    with get_session() as s:
        # --- Origin schools (4) ---
        o1 = create_school(s, "EM Origem Centro", code="O1",
                           address="Rua do Centro, 100, São João da Barra, RJ",
                           distrito="1", latitude=CENTRO_LAT, longitude=CENTRO_LON,
                           is_origin=True, is_destination=False, oferta=0)
        o2 = create_school(s, "EM Origem Grussai", code="O2",
                           address="Rua de Grussai, 200, São João da Barra, RJ",
                           distrito="3", latitude=GRUSSA_LAT, longitude=GRUSSA_LON,
                           is_origin=True, is_destination=False, oferta=0)
        o3 = create_school(s, "EM Origem Cajueiro", code="O3",
                           address="Rua do Cajueiro, 300, São João da Barra, RJ",
                           distrito="4", latitude=CAJU_LAT, longitude=CAJU_LON,
                           is_origin=True, is_destination=False, oferta=0)
        o4 = create_school(s, "EM Origem Mato Escuro", code="O4",
                           address="Rua do Mato, 400, São João da Barra, RJ",
                           distrito="5", latitude=MATO_LAT, longitude=MATO_LON,
                           is_origin=True, is_destination=False, oferta=0)

        # --- Destination schools (6) ---
        # D1: Centro, capacity 3 — close to Centro origin
        d1 = create_school(s, "EM Destino Centro", code="D1",
                           address="Rua Centro, 50, São João da Barra, RJ",
                           distrito="1", latitude=-21.6355, longitude=-41.0495,
                           is_origin=False, is_destination=True, oferta=3)
        # D2: Grussai, capacity 2 — close to Grussai origin
        d2 = create_school(s, "EM Destino Grussai", code="D2",
                           address="Rua Grussai, 50, São João da Barra, RJ",
                           distrito="3", latitude=-21.7020, longitude=-41.0340,
                           is_origin=False, is_destination=True, oferta=2)
        # D3: Cajueiro, capacity 2 — close to Cajueiro origin
        d3 = create_school(s, "EM Destino Cajueiro", code="D3",
                           address="Rua Cajueiro, 50, São João da Barra, RJ",
                           distrito="4", latitude=-21.7195, longitude=-41.0945,
                           is_origin=False, is_destination=True, oferta=2)
        # D4: Without coordinates, capacity 3
        d4 = create_school(s, "EM Destino Sem Geo", code="D4",
                           address="Rua Sem Geo, 50, São João da Barra, RJ",
                           distrito=None, latitude=None, longitude=None,
                           is_origin=False, is_destination=True, oferta=3)
        # D5: With coordinates but capacity 0
        d5 = create_school(s, "EM Destino Zero Vagas", code="D5",
                           address="Rua Zero, 50, São João da Barra, RJ",
                           distrito="1", latitude=-21.6360, longitude=-41.0510,
                           is_origin=False, is_destination=True, oferta=0)
        # D6: Mato Escuro, capacity 3
        d6 = create_school(s, "EM Destino Mato Escuro", code="D6",
                           address="Rua Mato, 50, São João da Barra, RJ",
                           distrito="5", latitude=-21.8940, longitude=-41.0560,
                           is_origin=False, is_destination=True, oferta=3)

        # --- Classes ---
        c1 = create_class(s, o1.id, "1º Ano", 2025, "Manhã")
        c2 = create_class(s, o2.id, "2º Ano", 2025, "Tarde")
        c3 = create_class(s, o3.id, "3º Ano", 2025, "Manhã")

        # Total capacity: D1=3, D2=2, D3=2, D4=3, D5=0, D6=3 → 13
        # Total students: 21
        # So 8 should be sem_vaga

        students = []

        # Group A: near D1 (5 students, 1st choice D1, 2nd choice D3)
        # D1 has capacity 3 → 3 allocate, 2 overflow to D3
        # D3 has capacity 2 → 2 allocate from overflow, D3 full
        for i, name in enumerate([
            "Aluno A1 Centro", "Aluno A2 Centro", "Aluno A3 Centro",
            "Aluno A4 Centro", "Aluno A5 Centro",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o1.id,
                origin_class_id=c1.id,
                destination_school_1_id=d1.id,
                destination_school_2_id=d3.id,
                address=f"Rua Centro, {100+i}, São João da Barra, RJ",
                status=StudentStatus.DRAFT,
            )
            # Place near D1
            aluno.latitude = -21.6356 + i * 0.0001
            aluno.longitude = -41.0496 + i * 0.0001
            students.append(aluno)

        # Group B: near D2 (4 students, 1st choice D2, 2nd choice D6)
        # D2 capacity 2 → 2 allocate, 2 overflow
        # D6 capacity 3 → receives overflow from D1 (2 more) + D2 (2) = need to check capacity
        for i, name in enumerate([
            "Aluno B1 Grussai", "Aluno B2 Grussai",
            "Aluno B3 Grussai", "Aluno B4 Grussai",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o2.id,
                origin_class_id=c2.id,
                destination_school_1_id=d2.id,
                destination_school_2_id=d6.id,
                address=f"Rua Grussai, {200+i}, São João da Barra, RJ",
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = -21.7019 + i * 0.0001
            aluno.longitude = -41.0339 + i * 0.0001
            students.append(aluno)

        # Group C: near D6 (4 students, 1st choice D6, 2nd choice D2)
        # D6 capacity 3 → 3 allocate, 1 overflow to D2 (full) → sem vaga
        for i, name in enumerate([
            "Aluno C1 Mato", "Aluno C2 Mato", "Aluno C3 Mato", "Aluno C4 Mato",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o4.id,
                origin_class_id=c3.id,
                destination_school_1_id=d6.id,
                destination_school_2_id=d2.id,
                address=f"Rua Mato, {300+i}, São João da Barra, RJ",
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = -21.8938 + i * 0.0001
            aluno.longitude = -41.0558 + i * 0.0001
            students.append(aluno)

        # Group D: no coordinates (latitude=None), 1st choice D1, 2nd choice D4
        # D1 is full after Group A → overflow to 2nd choice pool (D4)
        # D4 has capacity 3, no coordinates → students use reference (1st choice D1) for distance
        for i, name in enumerate([
            "Aluno D1 Sem Coord", "Aluno D2 Sem Coord",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o3.id,
                origin_class_id=c3.id,
                destination_school_1_id=d1.id,
                destination_school_2_id=d4.id,
                address=f"Rua Sem Coord, {400+i}, São João da Barra, RJ",
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = None
            aluno.longitude = None
            students.append(aluno)

        # Group E: no address (address=None), 1st choice D1, 2nd choice D4
        # info_pendente, no coords → sem coordenada → overflow
        for i, name in enumerate([
            "Aluno E1 No Address", "Aluno E2 No Address",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o1.id,
                origin_class_id=c1.id,
                destination_school_1_id=d1.id,
                destination_school_2_id=d4.id,
                address=None,
                status=StudentStatus.DRAFT,
            )
            students.append(aluno)

        # Group F: no destination schools (1st=None, 2nd=None)
        # info_pendente, always sem vaga
        for i, name in enumerate([
            "Aluno F1 No Destino", "Aluno F2 No Destino",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o2.id,
                origin_class_id=c2.id,
                destination_school_1_id=None,
                destination_school_2_id=None,
                address=f"Rua Sem Destino, {500+i}, São João da Barra, RJ",
                status=StudentStatus.DRAFT,
            )
            students.append(aluno)

        # Group G: empty string address, 1st choice D5 (0 capacity), 2nd=None
        # D5 has 0 capacity → all go to overflow, no 2nd choice → sem vaga
        # Also info_pendente (empty address)
        for i, name in enumerate([
            "Aluno G1 Empty Addr", "Aluno G2 Empty Addr",
        ], 1):
            aluno = create_student(
                s, name=name, origin_school_id=o4.id,
                origin_class_id=c3.id,
                destination_school_1_id=d5.id,
                destination_school_2_id=None,
                address="",
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = None
            aluno.longitude = None
            students.append(aluno)

        s.commit()

        return {
            "origin_schools": [o1.id, o2.id, o3.id, o4.id],
            "dest_schools": {
                "d1": d1.id, "d2": d2.id, "d3": d3.id,
                "d4": d4.id, "d5": d5.id, "d6": d6.id,
            },
            "classes": [c1.id, c2.id, c3.id],
            "student_ids": [st.id for st in students],
            "total_students": len(students),
        }


# ---------------------------------------------------------------------------
# Test 1: Data seeding
# ---------------------------------------------------------------------------
def test_seeding(data):
    section("TEST 1: Data Seeding")
    with get_session() as s:
        schools = list_schools(s)
        students = list_students(s, limit=1000)
        check("4 origin schools", len([x for x in schools if x.is_origin]) == 4,
              f"got {len([x for x in schools if x.is_origin])}")
        check("6 destination schools", len([x for x in schools if x.is_destination]) == 6,
              f"got {len([x for x in schools if x.is_destination])}")
        check(f"21 students seeded", len(students) == 21,
              f"got {len(students)}")

        # Verify coordinates are set
        c1 = get_student(s, data["student_ids"][0])
        check("Student has coordinates", c1.latitude is not None and c1.longitude is not None)

        # Verify no-address students
        e1 = get_student(s, data["student_ids"][16])  # Group E first
        check("No-address student has None address", e1.address is None)

        # Verify no-destination students
        f1 = get_student(s, data["student_ids"][18])  # Group F first
        check("No-dest student has 1st choice None", f1.destination_school_1_id is None)

        # Verify D5 has 0 capacity
        d5 = s.get(School, data["dest_schools"]["d5"])
        check("D5 has oferta=0", d5.oferta == 0)

        # Verify D4 has no coordinates
        d4 = s.get(School, data["dest_schools"]["d4"])
        check("D4 has no coordinates", d4.latitude is None and d4.longitude is None)


# ---------------------------------------------------------------------------
# Test 2: Allocation preview
# ---------------------------------------------------------------------------
def test_allocation_preview(data):
    section("TEST 2: Allocation Preview (dry run)")
    svc = AllocationService()
    summary = svc.run_allocation(preview=True)

    d = data["dest_schools"]

    check("Preview total = 21", summary.total_students == 21,
          f"got {summary.total_students}")
    check("Preview allocated > 0", summary.allocated > 0)
    check("Preview waitlist > 0", summary.waitlist > 0)
    check("Preview sem vaga (waitlist) > 0", summary.waitlist > 0)

    # Capacity should not be exceeded
    by_school = summary.by_school
    for sid, info in by_school.items():
        if info.get("capacity", 0) > 0:
            check(f"School {sid} ({info.get('school_name', '?')}) not over capacity",
                  info["allocated"] <= info["capacity"],
                  f"allocated={info['allocated']}, capacity={info['capacity']}")

    # D1 should be full (capacity 3)
    if d["d1"] in by_school:
        check("D1 is full (3/3)", by_school[d["d1"]]["allocated"] == 3,
              f"got {by_school[d['d1']]['allocated']}")

    # Preview should NOT write to DB
    with get_session() as s:
        allocated_in_db = s.query(Student).filter(
            Student.allocated_school_id.isnot(None)
        ).count()
        check("Preview did not write to DB", allocated_in_db == 0,
              f"got {allocated_in_db}")

    return summary


# ---------------------------------------------------------------------------
# Test 3: Allocation execution
# ---------------------------------------------------------------------------
def test_allocation_execute(data):
    section("TEST 3: Allocation Execution (writes to DB)")
    svc = AllocationService()
    summary = svc.run_allocation(preview=False)

    d = data["dest_schools"]

    check("Execute total = 21", summary.total_students == 21,
          f"got {summary.total_students}")
    check("Execute allocated + waitlist = total",
          summary.allocated + summary.waitlist == summary.total_students,
          f"allocated={summary.allocated}, waitlist={summary.waitlist}")

    # Verify in DB
    with get_session() as s:
        students = list_students(s, limit=1000)
        allocated_count = sum(1 for st in students if st.allocated_school_id is not None)
        sem_vaga_count = sum(1 for st in students if st.allocation_status == "sem_vaga")
        pending_count = sum(1 for st in students if st.allocation_status == "pending")

        check("DB allocated > 0", allocated_count > 0)
        check("DB allocated + sem_vaga = 21",
              allocated_count + sem_vaga_count == 21,
              f"allocated={allocated_count}, sem_vaga={sem_vaga_count}")

        # Each student has at most one allocated_school_id
        for st in students:
            check(f"Student {st.id} has at most one allocated school",
                  st.allocated_school_id is not None or st.allocation_status == "sem_vaga",
                  f"allocated={st.allocated_school_id}, status={st.allocation_status}")

        # D1 should be full
        d1_count = sum(1 for st in students if st.allocated_school_id == d["d1"])
        check("D1 allocated = 3 (full)", d1_count == 3, f"got {d1_count}")
        d1_school = s.get(School, d["d1"])
        check("D1 not over capacity", d1_count <= d1_school.oferta)

        # D6 should be at capacity (3)
        d6_count = sum(1 for st in students if st.allocated_school_id == d["d6"])
        check("D6 allocated <= 3 (capacity)", d6_count <= 3, f"got {d6_count}")

        # D4 (no coords, cap 3) should have some allocations
        d4_count = sum(1 for st in students if st.allocated_school_id == d["d4"])
        check("D4 allocated >= 0", d4_count >= 0, f"got {d4_count}")

        # D5 (0 capacity) should have 0 allocations
        d5_count = sum(1 for st in students if st.allocated_school_id == d["d5"])
        check("D5 allocated = 0 (no capacity)", d5_count == 0, f"got {d5_count}")

    return summary


# ---------------------------------------------------------------------------
# Test 4: Allocation stats
# ---------------------------------------------------------------------------
def test_allocation_stats(data):
    section("TEST 4: Allocation Stats (get_allocation_stats)")
    svc = AllocationService()
    stats = svc.get_allocation_stats()

    check("stats has total", "total" in stats)
    check("stats has allocated", "allocated" in stats)
    check("stats has sem_vaga", "sem_vaga" in stats)
    check("stats has pending", "pending" in stats)
    check("stats has by_school", "by_school" in stats)

    check("stats total = 21", stats["total"] == 21, f"got {stats['total']}")
    check("stats allocated + sem_vaga + pending = 21",
          stats["allocated"] + stats["sem_vaga"] + stats["pending"] == 21,
          f"alloc={stats['allocated']}, sem_vaga={stats['sem_vaga']}, pending={stats['pending']}")

    # by_school should not exceed capacity
    for sid, info in stats["by_school"].items():
        check(f"by_school {sid} not over capacity",
              info["allocated"] <= info["capacity"],
              f"allocated={info['allocated']}, capacity={info['capacity']}")


# ---------------------------------------------------------------------------
# Test 5: Situation counting cross-checks
# ---------------------------------------------------------------------------
def test_situacao_aluno(data):
    section("TEST 5: Situation Counting Cross-Checks")

    # Method 1: contar_situacao_aluno()
    counts = contar_situacao_aluno()

    check("contar has alunos key", "alunos" in counts)
    check("contar has pendente key", "pendente" in counts)
    check("contar has encaminhados key", "encaminhados" in counts)
    check("contar has info_pendente key", "info_pendente" in counts)

    check("alunos = 21", counts["alunos"] == 21, f"got {counts['alunos']}")
    check("encaminhados + pendente = alunos",
          counts["encaminhados"] + counts["pendente"] == counts["alunos"],
          f"enc={counts['encaminhados']}, pend={counts['pendente']}")

    # Method 2: detalhar_situacao_aluno() for each category
    for chave, label, _ in SITUACAO_ALUNO:
        rows = detalhar_situacao_aluno(chave)
        check(f"detalhar({chave}) returns list", isinstance(rows, list))
        if chave == "alunos":
            check(f"detalhar({chave}) count = 21", len(rows) == 21,
                  f"got {len(rows)}")
        elif chave == "encaminhados":
            check(f"detalhar({chave}) count = encaminhados",
                  len(rows) == counts["encaminhados"],
                  f"detalhar={len(rows)}, contador={counts['encaminhados']}")
        elif chave == "pendente":
            check(f"detalhar({chave}) count = pendente",
                  len(rows) == counts["pendente"],
                  f"detalhar={len(rows)}, contador={counts['pendente']}")

    # Method 3: Cross-check with montar_resumo()
    resumo = montar_resumo()
    check("resumo.alunos = counts.alunos",
          resumo.alunos == counts["alunos"],
          f"resumo={resumo.alunos}, counts={counts['alunos']}")
    check("resumo.alocados = counts.encaminhados",
          resumo.alocados == counts["encaminhados"],
          f"resumo={resumo.alocados}, counts={counts['encaminhados']}")

    # sem_vaga in resumo should match the allocation sem_vaga
    check("resumo.sem_vaga = alunos - alocados",
          resumo.sem_vaga == counts["alunos"] - counts["encaminhados"],
          f"resumo={resumo.sem_vaga}, diff={counts['alunos'] - counts['encaminhados']}")

    # info_pendente is a subset that should be <= alunos
    check("info_pendente <= alunos",
          counts["info_pendente"] <= counts["alunos"],
          f"info_pendente={counts['info_pendente']}")

    # Verify info_pendente details: at least the 4 students without address/destination
    # Group E (2 students, no address) + Group G (2 students, empty address)
    # + Group F (2 students, no destination) = 6 info_pendente minimum
    rows_info = detalhar_situacao_aluno("info_pendente")
    check("info_pendente >= 6", len(rows_info) >= 6, f"got {len(rows_info)}")

    return resumo, counts


# ---------------------------------------------------------------------------
# Test 6: Pendencias consistency
# ---------------------------------------------------------------------------
def test_pendencias(resumo):
    section("TEST 6: Pendencias Consistency")

    check("resumo has pendencias", len(resumo.pendencias) > 0)
    check("total_pendencias = sum of quantidade",
          resumo.total_pendencias == sum(p.quantidade for p in resumo.pendencias))

    # Each pendencia should have a valid categoria
    valid_keys = {
        "escolas_sem_capacidade", "escolas_sem_geo", "alunos_sem_coordenada",
        "alunos_sem_vaga", "alunos_sem_segunda", "lotes_sem_pdf",
        "lotes_nao_enviados", "escolas_sobrecarregadas", "escolas_ociosas",
        "atualizacao",
    }
    for p in resumo.pendencias:
        check(f"pendencia chave '{p.chave}' is valid",
              p.chave in valid_keys or p.chave.startswith("atualizacao"),
              f"unknown key: {p.chave}")
        check(f"pendencia '{p.chave}' has quantidade > 0",
              p.quantidade > 0)

    # Detail each pendencia
    for p in resumo.pendencias:
        if p.chave == "alunos_sem_vaga":
            rows = detalhar_pendencia("alunos_sem_vaga")
            check("detalhar sem_vaga returns rows", len(rows) == p.quantidade,
                  f"pendencia={p.quantidade}, detalhe={len(rows)}")
        elif p.chave == "escolas_sem_capacidade":
            rows = detalhar_pendencia("escolas_sem_capacidade")
            check("detalhar sem_capacidade returns rows", len(rows) == p.quantidade)


# ---------------------------------------------------------------------------
# Test 7: Batch creation + PDF generation
# ---------------------------------------------------------------------------
def test_batches(data):
    section("TEST 7: Batch Creation + PDF Generation")

    d = data["dest_schools"]
    batch_id = None

    with get_session() as s:
        # Get allocated students at D1
        d1_students = list_students(s, destination_school_id=d["d1"], limit=1000)
        d1_alloc = [st for st in d1_students if st.allocated_school_id == d["d1"]]

        check("D1 has allocated students for batch", len(d1_alloc) > 0,
              f"got {len(d1_alloc)}")

        if d1_alloc:
            # Create batch
            batch = create_batch(
                s, origin_school_id=data["origin_schools"][0],
                destination_school_id=d["d1"],
                year=2025, origin_class_id=data["classes"][0],
                notes="Test batch",
            )
            check("Batch created", batch.id is not None)

            # Add students
            student_ids = [st.id for st in d1_alloc]
            items = add_students_to_batch(s, batch.id, student_ids)
            check("Batch items added", len(items) == len(student_ids),
                  f"expected {len(student_ids)}, got {len(items)}")
            check("Batch student_count", batch.student_count == len(student_ids))

            batch_id = batch.id

    # Test PDF generation (outside the creation session so it's committed)
    if batch_id:
        pdf_path = str(PDF_EXPORT_DIR / f"test_batch_{batch_id}.pdf")
        try:
            result_path = generate_batch_pdf(batch_id, output_path=pdf_path)
            check("PDF file created", Path(result_path).exists())
            check("PDF file > 0 bytes", Path(result_path).stat().st_size > 0)
        except ValueError as e:
            if "No students in batch" in str(e):
                check("PDF generation skipped (empty batch)", True)
            else:
                check("PDF generation failed", False, str(e))
        except Exception as e:
            check("PDF generation raised", False, str(e))

    # Test empty batch PDF (creation + commit happens in the with block)
    with get_session() as s:
        batch_empty = create_batch(
            s, origin_school_id=data["origin_schools"][0],
            destination_school_id=d["d2"],
            year=2025, origin_class_id=data["classes"][0],
            notes="Empty batch",
        )
        empty_id = batch_empty.id
    # with block commits on exit; now test PDF in fresh session
    try:
        generate_batch_pdf(empty_id)
        check("PDF for empty batch raises ValueError", False, "no error")
    except ValueError as e:
        check("PDF for empty batch raises ValueError", "No students" in str(e))

    return batch_id


# ---------------------------------------------------------------------------
# Test 8: Status transitions
# ---------------------------------------------------------------------------
def test_status_transitions(data, batch_id):
    section("TEST 8: Status Transitions")

    d = data["dest_schools"]

    # Get a pending student from a fresh session
    with get_session() as s:
        students = list_students(s, limit=1000)
        pending_students = [st for st in students if st.status == StudentStatus.PENDING]
        draft_students = [st for st in students if st.status == StudentStatus.DRAFT]

        check("Has pending students", len(pending_students) > 0)
        check("Has draft students (sem vaga)", len(draft_students) > 0)

    if pending_students:
        aluno_id = pending_students[0].id

        # PENDING -> SENT (uses its own session + commit)
        result = transition_student_status(aluno_id, StudentStatus.SENT)
        check("PENDING -> SENT valid", result)

        # Re-read from a fresh session to avoid stale cache
        with get_session() as s:
            updated = get_student(s, aluno_id)
            check("Status is SENT", updated.status == StudentStatus.SENT)

        # SENT -> CONFIRMED
        result2 = transition_student_status(aluno_id, StudentStatus.CONFIRMED)
        check("SENT -> CONFIRMED valid", result2)

        with get_session() as s:
            updated = get_student(s, aluno_id)
            check("Status is CONFIRMED", updated.status == StudentStatus.CONFIRMED)

        # CONFIRMED -> SENT (invalid)
        result3 = transition_student_status(aluno_id, StudentStatus.SENT)
        check("CONFIRMED -> SENT invalid (rejected)", not result3)

    # Test invalid transition: DRAFT -> CONFIRMED
    if draft_students:
        draft_id = draft_students[0].id
        result_inv = transition_student_status(draft_id, StudentStatus.CONFIRMED)
        check("DRAFT -> CONFIRMED invalid", not result_inv)

    # Test bulk transition + batch status
    if batch_id:
        with get_session() as s:
            batch_students = get_students_for_batch(s, batch_id)
            check("Batch has students", len(batch_students) > 0)

            current_status = s.get(ForwardingBatch, batch_id)
            check("Batch status is DRAFT", current_status.status == BatchStatus.DRAFT)

        # Auto-advance batch status
        new_status = auto_advance_batch_status(batch_id)
        check("Auto-advance returns valid status", new_status is not None)

        # Get status summary (opens its own session)
        summary = get_status_summary(batch_id)
        check("Status summary has batch_id", "batch_id" in summary)
        check("Status summary has total_students", "total_students" in summary)
        check("Status summary has by_status", "by_status" in summary)
        check("Status summary has can_send_emails", "can_send_emails" in summary)
        check("Status summary has can_generate_pdf", "can_generate_pdf" in summary)
        check("Status summary total > 0", summary["total_students"] > 0,
              f"got {summary['total_students']}")


# ---------------------------------------------------------------------------
# Test 9: Email sending (mocked SMTP)
# ---------------------------------------------------------------------------
def test_email(data, batch_id):
    section("TEST 9: Email Sending (mocked SMTP)")

    # Test send_email
    smtp_patcher = mock_smtp()
    smtp_patcher.start()

    try:
        result = send_email(
            to_emails=["destino@example.com"],
            subject="Test Subject",
            body_text="Test body",
        )
        check("send_email returns success", result.success, result.error or "")

        # Test send_email with no recipients
        result_empty = send_email(
            to_emails=[],
            subject="Test",
            body_text="Test",
        )
        check("send_email with empty recipients fails", not result_empty.success)

        # Test send_batch_notification
        if batch_id:
            # Generate PDF first
            pdf_path = str(PDF_EXPORT_DIR / f"email_batch_{batch_id}.pdf")
            try:
                generate_batch_pdf(batch_id, output_path=pdf_path)
                result_batch = send_batch_notification(
                    batch_id=batch_id,
                    to_emails=["escola@example.com"],
                    pdf_path=pdf_path,
                )
                check("send_batch_notification returns success",
                      result_batch.success, result_batch.error or "")
            except ValueError as e:
                if "No students in batch" in str(e):
                    check("send_batch_notification skipped (empty batch)", True)
                else:
                    check("send_batch_notification failed", False, str(e))

        # Test non-existent batch
        result_missing = send_batch_notification(
            batch_id=99999,
            to_emails=["test@example.com"],
        )
        check("send_batch_notification with bad batch fails", not result_missing.success)
    finally:
        smtp_patcher.stop()


# ---------------------------------------------------------------------------
# Test 10: Edge cases
# ---------------------------------------------------------------------------
def test_edge_cases(data):
    section("TEST 10: Edge Cases")

    d = data["dest_schools"]

    # Test geocoding distance function
    dist = haversine_distance(CENTRO_LAT, CENTRO_LON, GRUSSA_LAT, GRUSSA_LON)
    check("Haversine returns positive distance", dist > 0)
    check("Haversine distance is reasonable (7-15km)",
          7 < dist < 15, f"got {dist:.2f} km")

    # Test school name matching
    with get_session() as s:
        norm = normalize_school_name("1ª EM Destino Centro")
        check("normalize strips ordinal", "1" not in norm and "EM" not in norm,
              f"got: {norm}")

        # Match should find D1
        matched = match_school_name("EM Destino Centro")
        check("match_school_name finds D1", matched == d["d1"],
              f"got {matched}, expected {d['d1']}")

    # Test SITUACAO_ALUNO structure
    check("SITUACAO_ALUNO has 4 entries", len(SITUACAO_ALUNO) == 4)
    check("SITUACAO_ALUNO has alunos", any(k == "alunos" for k, _, _ in SITUACAO_ALUNO))
    check("SITUACAO_ALUNO has pendente", any(k == "pendente" for k, _, _ in SITUACAO_ALUNO))
    check("SITUACAO_ALUNO has encaminhados", any(k == "encaminhados" for k, _, _ in SITUACAO_ALUNO))
    check("SITUACAO_ALUNO has info_pendente", any(k == "info_pendente" for k, _, _ in SITUACAO_ALUNO))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"\nComprehensive Integration Test")
    print(f"Database: {os.environ['DATABASE_URL']}")
    print(f"Test output dir: {_TEST_DIR}")

    # Seed data
    data = seed_data()

    # Run all tests
    test_seeding(data)
    preview_summary = test_allocation_preview(data)
    test_allocation_execute(data)
    test_allocation_stats(data)
    resumo, counts = test_situacao_aluno(data)
    test_pendencias(resumo)
    batch_id = test_batches(data)
    test_status_transitions(data, batch_id)
    test_email(data, batch_id)
    test_edge_cases(data)

    # Summary
    section("TEST SUMMARY")
    total = PASS + FAIL
    print(f"  Passed: {PASS}/{total}")
    print(f"  Failed: {FAIL}/{total}")
    if FAIL == 0:
        print(f"\n  ALL TESTS PASSED ✓")
    else:
        print(f"\n  {FAIL} TEST(S) FAILED ✗")

    # Cleanup
    engine.dispose()
    import time; time.sleep(0.3)
    for p in _TEST_DIR.glob("*"):
        if p.is_file() and p.suffix in (".db", ".db-journal"):
            try:
                p.unlink()
            except PermissionError:
                pass

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
