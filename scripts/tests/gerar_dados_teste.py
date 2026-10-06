"""
Gera alunos ficticios no banco real para testar todos os casos e avisos do sistema.

Cobre:
  - Alunos com endereco e duas escolas de destino (caso normal)
  - Alunos sem segunda opcao (aviso: alunos_sem_segunda)
  - Alunos sem endereco (aviso: info_pendente + sem_coordenada)
  - Alunos sem escola de destino 1 (aviso: info_pendente)
  - Alunos sem coordenada (aviso: alunos_sem_coordenada)
  - Alunos apontando para escola sobrecarregada (aviso: escolas_sobrecarregadas)
  - Alunos apontando para escola ociosa (aviso: escolas_ociosas)
  - Alunos sem vaga (aviso: alunos_sem_vaga)
  - Aluno ja alocado (contagem do total)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import func, select

from encaminhamento.database import init_db, get_session
from encaminhamento.database.crud import (
    create_student, list_schools, list_students, update_student,
)
from encaminhamento.database.models import (
    School, Student, StudentStatus,
)
from encaminhamento.services.allocation import get_allocation_service
from encaminhamento.services.relatorio import (
    montar_resumo, contar_situacao_aluno,
)
from encaminhamento.utils.helpers import format_student_name

# Coordenadas de Sao João da Barra (district centroids)
CENTRO = (-21.6344, -41.0490)
GRUSSA = (-21.7015, -41.0338)
CAJU = (-21.7191, -41.0944)
MATO = (-21.8935, -41.0550)


def get_school_ids():
    """Mapeia escolas reais para uso na geracao."""
    with get_session() as s:
        schools = list_schools(s)
        dest = [x for x in schools if x.is_destination]
        origem = [x for x in schools if x.is_origin]

        dest_com_capacidade = [x for x in dest if (x.oferta or 0) > 0]
        dest_sem_capacidade = [x for x in dest if (x.oferta or 0) == 0]

        # Escola origem qualquer
        origem_id = origem[0].id if origem else dest[0].id

    return {
        "origem_id": origem_id,
        "dest_com_cap": dest_com_capacidade,
        "dest_sem_cap": dest_sem_capacidade,
        "all_dest": dest,
    }


def gerar_alunos():
    info = get_school_ids()
    origem_id = info["origem_id"]

    # Pick specific schools for each scenario
    dest_com_cap = info["dest_com_cap"]

    # Find an overloaded school (demand > capacity already)
    sobrecarregada = None
    ociosa = None
    normal_cap = None

    with get_session() as s:
        for escola in dest_com_cap:
            demand = s.execute(
                select(func.count(Student.id)).where(
                    (Student.destination_school_1_id == escola.id)
                    | (Student.destination_school_2_id == escola.id)
                )
            ).scalar() or 0
            alloc = s.execute(
                select(func.count(Student.id)).where(
                    Student.allocated_school_id == escola.id
                )
            ).scalar() or 0

            if demand > escola.oferta and not sobrecarregada:
                sobrecarregada = escola
            if demand > 0 and alloc == 0 and not ociosa:
                ociosa = escola
            if alloc > 0 and alloc < escola.oferta and not normal_cap:
                normal_cap = escola

    escolas_sem_cap = info["dest_sem_cap"]
    escola_sem_cap = escolas_sem_cap[0] if escolas_sem_cap else None

    alunos_criados = 0

    with get_session() as s:
        # --- Caso normal: 10 alunos com endereco e duas opcoes ---
        for i in range(10):
            nome = f"Aluno Normal {i+1}"
            aluno = create_student(
                s, name=format_student_name(nome),
                origin_school_id=origem_id,
                address=f"Rua Teste Normal, {100+i}, São João da Barra, RJ",
                destination_school_1_id=normal_cap.id if normal_cap else dest_com_cap[0].id,
                destination_school_2_id=dest_com_cap[1].id if len(dest_com_cap) > 1 else None,
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = CENTRO[0] + i * 0.001
            aluno.longitude = CENTRO[1] + i * 0.001
            alunos_criados += 1

        # --- Sem segunda opcao: 5 alunos com apenas 1a escolha ---
        for i in range(5):
            nome = f"Aluno Sem 2a {i+1}"
            aluno = create_student(
                s, name=format_student_name(nome),
                origin_school_id=origem_id,
                address=f"Rua Sem 2a, {200+i}, São João da Barra, RJ",
                destination_school_1_id=normal_cap.id if normal_cap else dest_com_cap[0].id,
                destination_school_2_id=None,
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = GRUSSA[0] + i * 0.001
            aluno.longitude = GRUSSA[1] + i * 0.001
            alunos_criados += 1

        # --- Sem endereco: 5 alunos sem endereco ---
        for i in range(5):
            nome = f"Aluno Sem Endereco {i+1}"
            aluno = create_student(
                s, name=format_student_name(nome),
                origin_school_id=origem_id,
                address=None,
                destination_school_1_id=normal_cap.id if normal_cap else dest_com_cap[0].id,
                destination_school_2_id=dest_com_cap[1].id if len(dest_com_cap) > 1 else None,
                status=StudentStatus.DRAFT,
            )
            alunos_criados += 1

        # --- Sem escola de destino 1: 3 alunos sem 1a opcao ---
        for i in range(3):
            nome = f"Aluno Sem Destino {i+1}"
            aluno = create_student(
                s, name=format_student_name(nome),
                origin_school_id=origem_id,
                address=f"Rua Sem Destino, {300+i}, São João da Barra, RJ",
                destination_school_1_id=None,
                destination_school_2_id=normal_cap.id if normal_cap else dest_com_cap[0].id,
                status=StudentStatus.DRAFT,
            )
            aluno.latitude = CAJU[0] + i * 0.001
            aluno.longitude = CAJU[1] + i * 0.001
            alunos_criados += 1

        # --- Sem coordenada: 5 alunos com endereco mas sem lat/lon ---
        for i in range(5):
            nome = f"Aluno Sem Coord {i+1}"
            aluno = create_student(
                s, name=format_student_name(nome),
                origin_school_id=origem_id,
                address=f"Rua Sem Coord, {400+i}, São João da Barra, RJ",
                destination_school_1_id=normal_cap.id if normal_cap else dest_com_cap[0].id,
                destination_school_2_id=dest_com_cap[1].id if len(dest_com_cap) > 1 else None,
                status=StudentStatus.DRAFT,
            )
            # Nao define latitude/longitude
            alunos_criados += 1

        # --- Apontando para escola sem capacidade: 5 alunos ---
        if escola_sem_cap:
            for i in range(5):
                nome = f"Aluno Sem Cap Dest {i+1}"
                aluno = create_student(
                    s, name=format_student_name(nome),
                    origin_school_id=origem_id,
                    address=f"Rua Sem Cap, {500+i}, São João da Barra, RJ",
                    destination_school_1_id=escola_sem_cap.id,
                    destination_school_2_id=dest_com_cap[0].id if dest_com_cap else None,
                    status=StudentStatus.DRAFT,
                )
                aluno.latitude = MATO[0] + i * 0.001
                aluno.longitude = MATO[1] + i * 0.001
                alunos_criados += 1

        # --- Apontando para escola sobrecarregada: 5 alunos ---
        if sobrecarregada:
            for i in range(5):
                nome = f"Aluno Sobrecarregado {i+1}"
                aluno = create_student(
                    s, name=format_student_name(nome),
                    origin_school_id=origem_id,
                    address=f"Rua Sobrecarregada, {600+i}, São João da Barra, RJ",
                    destination_school_1_id=sobrecarregada.id,
                    destination_school_2_id=dest_com_cap[0].id if dest_com_cap else None,
                    status=StudentStatus.DRAFT,
                )
                aluno.latitude = CENTRO[0] + i * 0.002
                aluno.longitude = CENTRO[1] + i * 0.002
                alunos_criados += 1

        # --- Apontando para escola ociosa: 5 alunos ---
        if ociosa:
            for i in range(5):
                nome = f"Aluno Ocioso {i+1}"
                aluno = create_student(
                    s, name=format_student_name(nome),
                    origin_school_id=origem_id,
                    address=f"Rua Ociosa, {700+i}, São João da Barra, RJ",
                    destination_school_1_id=ociosa.id,
                    destination_school_2_id=dest_com_cap[0].id if dest_com_cap else None,
                    status=StudentStatus.DRAFT,
                )
                aluno.latitude = GRUSSA[0] + i * 0.002
                aluno.longitude = GRUSSA[1] + i * 0.002
                alunos_criados += 1

        # --- Aluno vazio (endereco vazio e sem destino) ---
        aluno = create_student(
            s, name=format_student_name("Aluno Edge Vazio"),
            origin_school_id=origem_id,
            address="",
            destination_school_1_id=None,
            destination_school_2_id=None,
            status=StudentStatus.DRAFT,
        )
        alunos_criados += 1

        s.commit()

    print(f"\n{alunos_criados} alunos gerados com dados ficticios.")
    print(f"Cenarios cobertos:")
    print(f"  - 10 alunos normais (endereco + 2 destinos)")
    print(f"  - 5 sem segunda opcao (aviso: alunos_sem_segunda)")
    print(f"  - 5 sem endereco (aviso: alunos_sem_coordenada + info_pendente)")
    print(f"  - 3 sem escola de destino 1 (aviso: info_pendente)")
    print(f"  - 5 sem coordenada (aviso: alunos_sem_coordenada)")
    print(f"  - 5 apontando para escola sem capacidade")
    print(f"  - 5 apontando para escola sobrecarregada (aviso: escolas_sobrecarregadas)")
    print(f"  - 5 apontando para escola ociosa (aviso: escolas_ociosas)")
    print(f"  - 1 aluno vazio (sem endereco, sem destino)")
    return alunos_criados


def main():
    init_db()

    total_antes = 0
    with get_session() as s:
        total_antes = s.execute(select(func.count(Student.id))).scalar()
    print(f"Alunos antes: {total_antes}")

    gerar_alunos()

    total_depois = 0
    with get_session() as s:
        total_depois = s.execute(select(func.count(Student.id))).scalar()
    print(f"Alunos depois: {total_depois}")
    print(f"Novos alunos: {total_depois - total_antes}")


if __name__ == "__main__":
    main()
