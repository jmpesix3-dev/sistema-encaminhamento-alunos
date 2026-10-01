"""
Mescla escolas duplicadas: reaponta os alunos para a escola oficial e remove a duplicata.
Uso: python mesclar_duplicadas.py            (apenas mostra o que sera feito)
     python mesclar_duplicadas.py --aplicar  (executa)
"""
import itertools
import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).parent))

from encaminhamento.database import init_db, get_session
from encaminhamento.database.crud import list_schools
from encaminhamento.database.models import School, Student, ForwardingBatch, Class
from encaminhamento.utils.helpers import normalize_school_name


def apenas_nome(nome):
    """Normaliza o nome, ignorando o que vier de(prefixo) ou sufixo(parentese)."""
    import re
    base = str(nome or "").split("(")[0]
    return normalize_school_name(base)


def encontrar_duplicadas():
    with get_session() as session:
        escolas = [
            {"id": e.id, "nome": e.name, "norm": apenas_nome(e.name)}
            for e in list_schools(session)
        ]

    pares = []
    for a, b in itertools.combinations(escolas, 2):
        na, nb = a["norm"], b["norm"]
        if not na or not nb:
            continue
        if na == nb or na in nb or nb in na:
            # Mantem a que tem mais dados preenchidos
            pares.append((a, b))
    return pares


def main():
    aplicar = "--aplicar" in sys.argv
    init_db()

    pares = encontrar_duplicadas()

    if not pares:
        print("Nenhuma duplicada encontrada.")
        return

    print(f"{len(pares)} par(es) de duplicadas:\n")

    for a, b in pares:
        with get_session() as session:
            alunos_a = session.execute(
                select(func.count(Student.id)).where(
                    (Student.destination_school_1_id == a["id"]) | (Student.destination_school_2_id == a["id"])
                )
            ).scalar() or 0
            alunos_b = session.execute(
                select(func.count(Student.id)).where(
                    (Student.destination_school_1_id == b["id"]) | (Student.destination_school_2_id == b["id"])
                )
            ).scalar() or 0
            escola_a = session.get(School, a["id"])
            school_b = session.get(School, b["id"])
            dados_a = sum(1 for v in [escola_a.address, escola_a.distrito, escola_a.modalidade, escola_a.email] if v)
            dados_b = sum(1 for v in [school_b.address, school_b.distrito, school_b.modalidade, school_b.email] if v)

        # Mantem a escola com mais dados cadastrais
        if dados_b > dados_a:
            manter, remover = b, a
            alunos_remover, alunos_manter = alunos_a, alunos_b
        else:
            manter, remover = a, b
            alunos_remover, alunos_manter = alunos_b, alunos_a

        print(f"  manter  #{manter['id']} {manter['nome']}  (dados={max(dados_a, dados_b)}, alunos={alunos_manter})")
        print(f"  remover #{remover['id']} {remover['nome']}  (alunos={alunos_remover})")
        print(f"    motivo: mesmo nome normalizado -> '{remover['norm']}'\n")

        if not aplicar:
            continue

        with get_session() as session:
            # Reaponta os alunos
            session.execute(
                Student.__table__.update()
                .where(Student.destination_school_1_id == remover["id"])
                .values(destination_school_1_id=manter["id"])
            )
            session.execute(
                Student.__table__.update()
                .where(Student.destination_school_2_id == remover["id"])
                .values(destination_school_2_id=manter["id"])
            )
            session.execute(
                Student.__table__.update()
                .where(Student.allocated_school_id == remover["id"])
                .values(allocated_school_id=manter["id"])
            )
            session.execute(
                Student.__table__.update()
                .where(Student.origin_school_id == remover["id"])
                .values(origin_school_id=manter["id"])
            )
            session.execute(
                ForwardingBatch.__table__.update()
                .where(ForwardingBatch.destination_school_id == remover["id"])
                .values(destination_school_id=manter["id"])
            )
            session.execute(
                ForwardingBatch.__table__.update()
                .where(ForwardingBatch.origin_school_id == remover["id"])
                .values(origin_school_id=manter["id"])
            )
            session.execute(
                Class.__table__.update()
                .where(Class.school_id == remover["id"])
                .values(school_id=manter["id"])
            )

            # Preserva oferta e coordenadas que faltarem na escola mantida
            atual = session.get(School, manter["id"])
            removida = session.get(School, remover["id"])
            if removida:
                if not atual.oferta and removida.oferta:
                    atual.oferta = removida.oferta
                if atual.latitude is None and removida.latitude is not None:
                    atual.latitude = removida.latitude
                    atual.longitude = removida.longitude

                session.delete(removida)

        print(f"    -> mesclado em #{manter['id']}\n")

    if not aplicar:
        print("Rode novamente com --aplicar para executar.")
    else:
        with get_session() as session:
            total = session.execute(select(func.count(School.id))).scalar()
        print(f"Concluido. Total de escolas: {total}")


if __name__ == "__main__":
    main()
