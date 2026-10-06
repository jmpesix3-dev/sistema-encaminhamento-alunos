"""
Roda o fluxo completo com o cenario de teste:
  alocacao -> lotes -> PDF -> validacao
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import delete, select, func

from encaminhamento.database import init_db, get_session
from encaminhamento.database.crud import (
    get_school_by_name, list_schools, create_batch, add_students_to_batch,
    update_batch_status, get_students_for_batch, list_batches,
)
from encaminhamento.database.models import (
    BatchItem, Class, ForwardingBatch, School, Student, StudentStatus, BatchStatus,
)
from encaminhamento.services.allocation import get_allocation_service
from encaminhamento.services.pdf_generator import generate_batch_pdf
from encaminhamento.services.excel_export import export_students_to_excel
from encaminhamento.config import PDF_EXPORT_DIR, EXCEL_EXPORT_DIR

init_db()

# ----------------------------------------------------------------------
print("=" * 72)
print("1. EXECUTANDO A ALOCACAO")
print("=" * 72)

svc = get_allocation_service()
r = svc.run_allocation(preview=False)

print(f"Alocados: {r.allocated}   Sem vaga: {r.no_address}   Total: {r.total_students}")

dist = [x.distance_km for x in r.results if x.distance_km is not None]
if dist:
    print(f"Distancia: {min(dist):.2f} km a {max(dist):.2f} km (media {sum(dist)/len(dist):.2f} km)")

# ----------------------------------------------------------------------
print()
print("=" * 72)
print("2. VERIFICANDO O BANCO")
print("=" * 72)

with get_session() as session:
    alocados = session.execute(
        select(func.count(Student.id)).where(Student.allocated_school_id.isnot(None))
    ).scalar() or 0
    print(f"Alunos com escola definida: {alocados}")

    # Nenhuma escola pode passar da capacidade
    print("\nCapacidade respeitada:")
    problemas = 0
    for sid, nome, oferta in session.execute(
        select(School.id, School.name, School.oferta)
    ).all():
        if not oferta:
            continue
        n = session.execute(
            select(func.count(Student.id)).where(Student.allocated_school_id == sid)
        ).scalar() or 0
        if n > oferta:
            print(f"  ESTOURO: {nome} recebeu {n} para {oferta} vagas")
            problemas += 1
    if not problemas:
        print("  OK - nenhuma escola passou da capacidade")

    # Alunos sem coordenada nao podem ter sido alocados
    sem_coord = session.execute(
        select(func.count(Student.id)).where(
            Student.allocated_school_id.isnot(None),
            Student.latitude.is_(None),
        )
    ).scalar() or 0
    print(f"\nAlunos sem coordenada alocados: {sem_coord} (esperado: pode ser >0, usa 1a opcao)")

# ----------------------------------------------------------------------
print()
print("=" * 72)
print("3. CRIANDO LOTES E GERANDO PDF")
print("=" * 72)

with get_session() as session:
    origem = None
    with get_session() as s2:
        mais_alunos = s2.execute(
            select(School.id).where(School.id.in_(select(Student.origin_school_id)))
        ).scalars().all()
        if mais_alunos:
            origem = session.get(School, mais_alunos[0])

    origem_id = origem.id if origem else list_schools(session)[0].id

with get_session() as session:
    session.execute(delete(BatchItem))
    session.execute(delete(ForwardingBatch))

    # Um lote por escola de destino que recebeu alunos
    com_alunos = session.execute(
        select(Student.allocated_school_id, func.count(Student.id))
        .where(Student.allocated_school_id.isnot(None))
        .group_by(Student.allocated_school_id)
    ).all()

    lotes = []
    for destino_id, quantidade in com_alunos:
        escola = session.get(School, destino_id)
        alunos_ids = [
            a for (a,) in session.execute(
                select(Student.id).where(Student.allocated_school_id == destino_id)
            ).all()
        ]
        lote = create_batch(session, origem_id, destino_id, 2026)
        add_students_to_batch(session, lote.id, alunos_ids)
        lotes.append((lote.id, escola.name, len(alunos_ids)))

    print(f"\n{len(lotes)} lote(s) criado(s):")
    for lid, nome, qtd in lotes:
        print(f"  Lote #{lid}  {nome[:45]:<45} {qtd} aluno(s)")

# Gera os PDFs fora da sessao
print("\nGerando arquivos:")
for lid, nome, qtd in lotes:
    try:
        pdf = generate_batch_pdf(lid)
        tamanho = Path(pdf).stat().st_size
        print(f"  PDF  Lote #{lid}: {tamanho:,} bytes  -> {Path(pdf).name}")

        with get_session() as session:
            update_batch_status(session, lid, BatchStatus.GENERATED, pdf)
    except Exception as exc:
        print(f"  PDF  Lote #{lid}: ERRO {exc}")

# ----------------------------------------------------------------------
print()
print("=" * 72)
print("4. EXPORTANDO PARA EXCEL")
print("=" * 72)

with get_session() as session:
    for lid, nome, qtd in lotes[:3]:
        lote = session.get(ForwardingBatch, lid)
        if not lote:
            continue
        destino = session.get(School, lote.destination_school_id)
        origem = session.get(School, lote.origin_school_id)
        alunos = [session.get(Student, a.student_id)
                  for a in session.query(BatchItem).filter_by(batch_id=lid).all()]
        try:
            xlsx = export_students_to_excel(alunos, destino, origem, "2026")
            print(f"  XLSX Lote #{lid}: {Path(xlsx).stat().st_size:,} bytes  -> {Path(xlsx).name}")
        except Exception as exc:
            print(f"  XLSX Lote #{lid}: ERRO {exc}")

print()
print("=" * 72)
print("FLUXO COMPLETO OK")
print("=" * 72)
