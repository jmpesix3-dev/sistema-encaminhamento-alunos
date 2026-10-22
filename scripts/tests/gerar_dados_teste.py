"""
Gera alunos fictícios no banco de dados para testar todos os cenários e visões do sistema.

Todos os alunos são inseridos SEM coordenadas (latitude=None, longitude=None),
refletindo a importação real onde a geolocalização e a alocação são executadas
pelo próprio sistema/interface.

Distribui alunos por TODAS as unidades de origem e destino cadastradas no banco,
gerando dados realistas para validar todos os cenários do sistema.

Cobre por unidade:
  1. Alunos normais (endereço completo + 2 opções + assinatura)
  2. Alunos sem 2ª opção de destino
  3. Alunos sem endereço
  4. Alunos sem 1ª opção de destino
  5. Alunos sem assinatura dos responsáveis
  6. Alunos apontando para escola sem capacidade definida
  7. Alunos apontando para escola sobrecarregada
  8. Alunos apontando para escola ociosa
  9. Aluno com registro totalmente vazio (edge case)

NÃO executa alocação automática e NÃO cria lotes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import func, select

from encaminhamento.database import init_db, get_session
from encaminhamento.database.crud import create_student, list_schools, update_school, create_class
from encaminhamento.database.models import Student, StudentStatus
from encaminhamento.utils.helpers import format_student_name


def get_school_info():
    """Mapeia escolas reais cadastradas no banco, organizadas por unidade."""
    with get_session() as s:
        schools = list_schools(s)
        origens = [x for x in schools if x.is_origin]
        destinos = [x for x in schools if x.is_destination]

        dest_com_capacidade = [x for x in destinos if (x.oferta or 0) > 0]
        dest_sem_capacidade = [x for x in destinos if (x.oferta or 0) == 0]

        # Mapeia classes existentes por escola de origem
        from encaminhamento.database.crud import list_classes
        classes_por_escola = {}
        for origem in origens:
            classes_por_escola[origem.id] = list_classes(s, school_id=origem.id)

        return {
            "origens": origens,
            "dest_com_cap": dest_com_capacidade,
            "dest_sem_cap": dest_sem_capacidade,
            "all_dest": destinos,
            "classes_por_escola": classes_por_escola,
        }


def set_capacidades():
    """Garante capacidades configuradas nas escolas de destino."""
    capacidades = {
        "E. M. Manoel Nunes Barreto": 12,
        "E. E. M. João Batista Alves": 10,
        "E. M. Amaro de Souza Paes": 8,
        "E. E. M. Luiz Gomes da Silva Neto": 10,
        "E. E. M. Manoel Ducas de Brito": 8,
        "E. E. M. Francisco Alves Toledo": 14,
        "EM Destino Centro": 15,
        "EM Destino Grussai": 12,
        "EM Destino Cajueiro": 10,
        "EM Destino Sem Geo": 12,
        "EM Destino Mato Escuro": 10,
    }
    with get_session() as s:
        schools = list_schools(s, is_destination=True)
        for escola in schools:
            if escola.name in capacidades:
                update_school(s, escola.id, oferta=capacidades[escola.name])


def gerar_alunos():
    info = get_school_info()
    origens = info["origens"]
    dest_com_cap = info["dest_com_cap"]
    escolas_sem_cap = info["dest_sem_cap"]
    classes_por_escola = info["classes_por_escola"]

    if not origens:
        print("Erro: Nenhuma escola de origem encontrada.")
        return 0

    if not dest_com_cap:
        print("Erro: Nenhuma escola de destino com capacidade encontrada.")
        return 0

    alunos_criados = 0
    ano_base = 2025

    with get_session() as s:
        for idx, origem in enumerate(origens):
            # Garante uma classe para esta escola de origem
            classes = classes_por_escola.get(origem.id, [])
            if not classes:
                classe = create_class(s, origem.id, f"Turma {origem.name}", ano_base, "Manhã")
            else:
                classe = classes[0]

            classe_id = classe.id if classe else None
            origem_id = origem.id

            # Seleciona 2 destinos com capacidade distintos para esta unidade
            d1_id = dest_com_cap[idx % len(dest_com_cap)].id
            d2_id = dest_com_cap[(idx + 1) % len(dest_com_cap)].id
            escola_sem_cap_id = escolas_sem_cap[0].id if escolas_sem_cap else d1_id

            sufixo = f"(Unidade {origem.name})"

            # 1. Caso normal: 5 alunos com endereço e duas opções e assinatura
            for i in range(5):
                create_student(
                    s, name=format_student_name(f"Normal {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua Normal, {100*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=d1_id,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 2. Sem 2ª opção: 3 alunos com apenas 1ª escolha
            for i in range(3):
                create_student(
                    s, name=format_student_name(f"Sem 2a Opcao {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua 2a Opcao, {200*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=d1_id,
                    destination_school_2_id=None,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 3. Sem endereço: 3 alunos sem endereço
            for i in range(3):
                create_student(
                    s, name=format_student_name(f"Sem Endereco {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=None,
                    destination_school_1_id=d1_id,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 4. Sem 1ª opção de destino: 2 alunos
            for i in range(2):
                create_student(
                    s, name=format_student_name(f"Sem 1a Opcao {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua 1a Opcao, {300*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=None,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 5. Sem assinatura dos responsáveis: 3 alunos
            for i in range(3):
                create_student(
                    s, name=format_student_name(f"Sem Assinatura {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua Sem Assinatura, {400*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=d1_id,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=False,
                )
                alunos_criados += 1

            # 6. Apontando para escola sem capacidade definida: 3 alunos
            for i in range(3):
                create_student(
                    s, name=format_student_name(f"Sem Cap Dest {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua Sem Cap, {500*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=escola_sem_cap_id,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 7. Apontando para escola sobrecarregada: 3 alunos (oferecem mais do que capacidade)
            for i in range(3):
                create_student(
                    s, name=format_student_name(f"Sobrecarregado {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua Sobrecarregada, {600*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=d1_id,
                    destination_school_2_id=d2_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 8. Apontando para escola ociosa: 2 alunos
            for i in range(2):
                create_student(
                    s, name=format_student_name(f"Ocioso {sufixo} {i+1}"),
                    origin_school_id=origem_id,
                    origin_class_id=classe_id,
                    address=f"Rua Ociosa, {700*(idx+1)+i}, São João da Barra, RJ",
                    destination_school_1_id=d2_id,
                    destination_school_2_id=d1_id,
                    status=StudentStatus.DRAFT,
                    responsible_signature=True,
                )
                alunos_criados += 1

            # 9. Registro totalmente vazio (apenas 1 por unidade)
            create_student(
                s, name=format_student_name(f"Edge Vazio {sufixo}"),
                origin_school_id=origem_id,
                origin_class_id=classe_id,
                address="",
                destination_school_1_id=None,
                destination_school_2_id=None,
                status=StudentStatus.DRAFT,
                responsible_signature=False,
            )
            alunos_criados += 1

        s.commit()

    print(f"\n{alunos_criados} alunos criados sem coordenadas (latitude=None, longitude=None).")
    print("Alunos distribuidos por todas as unidades de origem encontradas.")
    print("Todos os alunos inseridos como nao alocados (pendentes de alocacao no sistema).")
    return alunos_criados


def main():
    init_db()

    total_antes = 0
    with get_session() as s:
        total_antes = s.execute(select(func.count(Student.id))).scalar() or 0
    print(f"Alunos antes no banco: {total_antes}")

    set_capacidades()
    gerar_alunos()

    total_depois = 0
    with get_session() as s:
        total_depois = s.execute(select(func.count(Student.id))).scalar() or 0
    print(f"Alunos depois no banco: {total_depois}")
    print(f"Novos alunos adicionados: {total_depois - total_antes}")
    try:
        input("Pressione Enter para sair...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
