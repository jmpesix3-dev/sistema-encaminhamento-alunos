"""
Carrega o cenario de teste no sistema, do zero.

Passos:
  1. apaga os alunos e lotes de teste
  2. define a capacidade das escolas de destino
  3. importa a planilha modeloupload_teste.xlsx
  4. geolocaliza os alunos
  5. roda a alocacao e mostra o resultado

Uso:  python carregar_cenario.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import delete, func, select

from encaminhamento.config import DATA_DIR, EXCEL_IMPORT_DIR
from encaminhamento.database import init_db, get_session
from encaminhamento.database.crud import (
    get_school_by_name, list_schools, list_students, list_batches,
    create_class, create_student, update_school, update_student,
)
from encaminhamento.database.models import (
    BatchItem, Class, ForwardingBatch, Student, StudentStatus,
)
from encaminhamento.services.allocation import get_allocation_service
from encaminhamento.services.excel_import import parse_modeloupload
from encaminhamento.services.geocoding import get_geocoding_service
from encaminhamento.utils.helpers import format_student_name, get_or_create_school_from_name

PLANILHA = str(EXCEL_IMPORT_DIR / "modeloupload_teste.xlsx")

# Capacidade por escola de destino (escolhida para forcar lotacao em uma)
CAPACIDADES = {
    "E. M. Manoel Nunes Barreto": 12,
    "E. E. M. João Batista Alves": 10,
    "E. M. Amaro de Souza Paes": 8,
    "E. E. M. Luiz Gomes da Silva Neto": 10,
    "E. E. M. Manoel Ducas de Brito": 8,
    "E. E. M. Francisco Alves Toledo": 14,
    "Creche Municipal Floriano de Azeredo Siqueira": 6,
    "Creche Municipal Maria da Conceição dos Santos Campos": 6,
    "C. M. E. Aldair Coutinho Machado": 6,
}


def limpar():
    with get_session() as session:
        session.execute(delete(BatchItem))
        session.execute(delete(ForwardingBatch))
        session.execute(delete(Student))
        session.execute(delete(Class))
        for s in list_schools(session):
            update_school(session, s.id, oferta=0)
    print("1. Dados de teste anteriores removidos.")


def definir_capacidades():
    with get_session() as session:
        for nome, oferta in CAPACIDADES.items():
            escola = get_school_by_name(session, nome)
            if escola:
                update_school(session, escola.id, oferta=oferta)
    print(f"2. Capacidade definida em {len(CAPACIDADES)} escolas de destino.")


def importar():
    resultado = parse_modeloupload(PLANILHA)
    if not resultado.success:
        print(f"   Erro: {resultado.errors}")
        return 0

    with get_session() as session:
        fallback = list_schools(session)[0].id

    # Resolve fora de sessao aninhada para nao travar o SQLite
    preparacao = []
    for grupo in resultado.grupos:
        nome_origem = grupo["origin_school"]
        origem_id = (
            get_or_create_school_from_name(nome_origem, is_origin=True, is_destination=True)
            if nome_origem else fallback
        )

        turma_id = None
        if grupo["origin_class"]:
            with get_session() as s2:
                from encaminhamento.database.crud import list_classes
                existentes = list_classes(s2, school_id=origem_id)
                mesma = next((c for c in existentes if c.name == grupo["origin_class"]), None)
                if mesma:
                    turma_id = mesma.id
                else:
                    turma_id = create_class(
                        s2, origem_id, grupo["origin_class"], 2026
                    ).id

        alunos = []
        for a in grupo["students"]:
            d1 = (a.get("destination_school_1_name") or "").strip()
            d2 = (a.get("destination_school_2_name") or "").strip()
            alunos.append((
                a,
                get_or_create_school_from_name(d1, is_destination=True) if d1 else None,
                get_or_create_school_from_name(d2, is_destination=True) if d2 else None,
            ))

        preparacao.append((origem_id, turma_id, alunos))

    total = 0
    with get_session() as session:
        for origem_id, turma_id, alunos in preparacao:
            for a, d1_id, d2_id in alunos:
                create_student(
                    session,
                    name=format_student_name(a["name"]),
                    civil_name=format_student_name(a.get("civil_name") or a["name"]),
                    address=a.get("address", ""),
                    reference_point="",
                    origin_school_id=origem_id,
                    origin_class_id=turma_id,
                    destination_school_1_id=d1_id,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=bool(a.get("responsible_signature")),
                )
                total += 1

    print(f"3. {total} aluno(s) importado(s) de {PLANILHA} "
          f"({len(resultado.grupos)} escola(s) de origem)")
    for aviso in resultado.warnings:
        print(f"   aviso: {aviso}")
    return total


def geolocalizar_alunos():
    geo = get_geocoding_service()
    with get_session() as session:
        alvos = [
            {"id": a.id, "endereco": a.address or "", "nome": a.name}
            for a in list_students(session, status=StudentStatus.DRAFT, limit=5000)
            if a.latitude is None
        ]

    if not alvos:
        print("4. Todos os alunos ja tem coordenada.")
        return

    print(f"4. Geolocalizando {len(alvos)} aluno(s)...")
    resumo = geo.geocode_alunos(alvos)
    for a in alvos:
        if a.get("lat") is not None:
            with get_session() as session:
                update_student(session, a["id"], latitude=a["lat"], longitude=a["lon"])

    niveis = ", ".join(f"{k}: {v}" for k, v in resumo["por_nivel"].items() if v)
    print(f"   Precisao: {niveis}")


def alocar():
    svc = get_allocation_service()
    r = svc.run_allocation(preview=True)

    print("\n" + "=" * 72)
    print("PREVIA DA ALOCACAO")
    print("=" * 72)
    print(f"Alunos: {r.total_students}   Alocados: {r.allocated}   Sem vaga: {r.no_address}")

    print(f"\n{'Escola':<42}{'Alocados':>10}{'Vagas':>8}{'Livres':>8}")
    print("-" * 72)
    for sid, info in sorted(r.by_school.items(), key=lambda kv: -kv[1]['allocated']):
        nome = info.get('school_name', str(sid))[:40]
        print(f"{nome:<42}{info['allocated']:>10}{info['capacity']:>8}"
              f"{info['capacity'] - info['allocated']:>8}")

    primeira = [x for x in r.results if x.status == "allocated"
                and x.original_choice_1_id == x.allocated_school_id]
    segunda = [x for x in r.results if x.status == "allocated"
               and x.original_choice_2_id == x.allocated_school_id]

    print("-" * 72)
    print(f"Alocados na 1a opcao: {len(primeira)}")
    print(f"Alocados na 2a opcao: {len(segunda)}")

    dist = [x.distance_km for x in r.results if x.distance_km is not None]
    if dist:
        print(f"Distancia: menor {min(dist):.2f} km | maior {max(dist):.2f} km "
              f"| media {sum(dist)/len(dist):.2f} km")

    return r


def main():
    init_db()
    limpar()
    definir_capacidades()
    importar()
    geolocalizar_alunos()
    alocar()

    print("\n" + "=" * 72)
    print("Cenario pronto. Abra http://localhost:8501 e va em:")
    print("  Alunos > Editar Dados   (revisao)")
    print("  Alocacao Automatica     (previa e execucao)")
    print("=" * 72)


if __name__ == "__main__":
    main()
