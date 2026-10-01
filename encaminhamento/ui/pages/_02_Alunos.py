import streamlit as st
import pandas as pd
from encaminhamento.ui.components import (
    sidebar_navigation, school_selector, file_uploader_with_preview, seletor_abas,
)
from encaminhamento.services.excel_import import parse_modeloupload_bytes
from encaminhamento.services.excel_export import export_students_to_excel, create_template_modeloupload
from encaminhamento.services.pdf_generator import generate_student_list_pdf
from encaminhamento.database import get_session
from encaminhamento.database.crud import (
    create_class, create_student, list_students, update_student,
    delete_student, get_school_by_name, list_classes,
)
from encaminhamento.database.models import StudentStatus, Class, School
from encaminhamento.utils.status import (
    opcoes_aluno, para_valor_aluno, rotulo_aluno,
)
from encaminhamento.utils.helpers import (
    format_student_name, get_or_create_school_from_name, parse_address_with_reference,
)


# ======================================================================
# ABA 1 - CARREGAR PLANILHA
# ======================================================================
def _aba_upload():
    st.subheader("Carregar planilha da escola (modeloupload.xlsx)")
    st.caption("A escola envia a planilha com a demanda. Revise os dados e salve no banco.")

    col_main, col_side = st.columns([3, 1])

    with col_side:
        st.write("")
        st.write("")
        st.write("")
        st.download_button(
            "📋 Baixar modelo em branco",
            open(create_template_modeloupload(), "rb").read(),
            file_name="modeloupload_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_main:
        uploaded = file_uploader_with_preview("Selecione a planilha", key="up_file")

    if not uploaded:
        st.info("Aguardando o envio de uma planilha.")
        return

    result = parse_modeloupload_bytes(uploaded.read())

    if not result.success:
        st.error("Não foi possível ler a planilha:")
        for err in result.errors:
            st.error(f"  - {err}")
        return

    for warn in result.warnings:
        st.warning(warn)

    st.success(f"**{len(result.students)} aluno(s) lido(s)**")

    # --- Escola e turma ---
    col_o, col_t = st.columns(2)

    with col_o:
        origin_school_id = None
        origin_name = result.origin_school
        if origin_name:
            with get_session() as session:
                school = get_school_by_name(session, origin_name)
                if not school:
                    school = create_school_from_name(session, origin_name)
                origin_school_id = school.id
            st.caption(f"Escola de origem: **{origin_name}**")
        else:
            st.warning("A planilha não informa a escola de origem.")

    with col_t:
        origin_class = st.text_input(
            "Turma de origem", value=result.origin_class or "", key="up_class"
        )

    # --- Tabela revisável ---
    rows = [{
        "Nome": s["name"],
        "Nome Civil": s.get("civil_name") or s["name"],
        "Endereço": s.get("address", ""),
        "Destino 1": s.get("destination_school_1_name", ""),
        "Destino 2": s.get("destination_school_2_name", ""),
        "Assinatura": bool(s.get("responsible_signature")),
    } for s in result.students]

    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={"Assinatura": st.column_config.CheckboxColumn("Assinatura")},
        key="up_editor",
    )

    st.caption("Corrija os dados na tabela se preciso. As escolas de destino são criadas automaticamente.")

    if not st.button("💾 Salvar alunos no banco", type="primary"):
        return

    if not origin_school_id:
        st.error("Escola de origem é obrigatória.")
        return

    saved = 0
    with get_session() as session:
        class_id = None
        if origin_class:
            existing = session.query(Class).filter_by(
                school_id=origin_school_id, name=origin_class
            ).first()
            class_id = existing.id if existing else create_class(
                session, origin_school_id, origin_class, 2025
            ).id

        for _, row in edited.iterrows():
            name = (row["Nome"] or "").strip()
            if not name:
                continue

            d1 = (row["Destino 1"] or "").strip()
            d2 = (row["Destino 2"] or "").strip()

            create_student(
                session,
                name=format_student_name(name),
                civil_name=format_student_name(row["Nome Civil"] or name),
                address=row["Endereço"] or "",
                reference_point="",
                origin_school_id=origin_school_id,
                origin_class_id=class_id,
                destination_school_1_id=get_or_create_school_from_name(d1, is_destination=True) if d1 else None,
                destination_school_2_id=get_or_create_school_from_name(d2, is_destination=True) if d2 else None,
                status=StudentStatus.DRAFT,
                responsible_signature=bool(row["Assinatura"]),
            )
            saved += 1

    st.success(f"**{saved} aluno(s) salvo(s).** Revise na aba *Editar Dados*.")


def create_school_from_name(session, name, is_destination=False, is_origin=True):
    from encaminhamento.database.crud import create_school
    return create_school(session, name, is_origin=is_origin, is_destination=is_destination)


# ======================================================================
# ABA 2 - CADASTRO MANUAL
# ======================================================================
def _aba_manual():
    st.subheader("Cadastrar aluno manualmente")
    st.caption("Para quando a demanda chegar fora da planilha, ou para incluir um aluno avulso.")

    col1, col2 = st.columns(2)

    with col1:
        origin = school_selector("Escola de origem *", key="mn_origin", is_origin=True, allow_new=True)

        class_id = None
        if origin:
            with get_session() as session:
                classes = list_classes(session, school_id=origin["id"])

            if classes:
                opts = {f"{c.name} ({c.year})": c.id for c in classes}
                opts["➕ Criar nova turma"] = "new"
                picked = st.selectbox("Turma de origem", options=list(opts), key="mn_class")

                if picked == "➕ Criar nova turma":
                    nome = st.text_input("Nome da nova turma", key="mn_new_class")
                    ano = st.number_input("Ano", 2020, 2030, 2025, key="mn_new_year")
                    if st.button("Criar turma", key="mn_btn_class"):
                        if not nome:
                            st.error("Informe o nome da turma.")
                        else:
                            with get_session() as session:
                                class_id = create_class(session, origin["id"], nome, ano).id
                            st.success(f"Turma '{nome}' criada.")
                            st.rerun()
                else:
                    class_id = opts[picked]
            else:
                st.caption("Nenhuma turma nesta escola.")
                nome = st.text_input("Nome da nova turma", key="mn_new_class_e")
                ano = st.number_input("Ano", 2020, 2030, 2025, key="mn_new_year_e")
                if nome and st.button("Criar turma", key="mn_btn_class_e"):
                    with get_session() as session:
                        class_id = create_class(session, origin["id"], nome, ano).id
                    st.success(f"Turma '{nome}' criada.")
                    st.rerun()

        dest1 = school_selector("Escola de destino (1ª) *", key="mn_d1", is_destination=True, allow_new=True)
        dest2 = school_selector("Escola de destino (2ª)", key="mn_d2", is_destination=True, allow_new=True)

    with col2:
        nome = st.text_input("Nome do aluno *", key="mn_nome", placeholder="Ex: João Silva Santos")
        civil = st.text_input("Nome civil", key="mn_civil", placeholder="Opcional")
        endereco = st.text_area(
            "Endereço completo *", key="mn_end",
            placeholder="Rua, número, bairro, cidade, CEP, ponto de referência...", height=110,
        )
        assinatura = st.checkbox("Responsável assinou o termo", key="mn_ass")

    addr, ref = parse_address_with_reference(endereco) if endereco else ("", "")
    if ref:
        st.caption(f"Referência detectada: {ref}")

    if not st.button("💾 Salvar aluno", type="primary"):
        return

    faltando = []
    if not (nome or "").strip():
        faltando.append("Nome do aluno")
    if not origin:
        faltando.append("Escola de origem")
    if not dest1:
        faltando.append("Escola de destino (1ª opção)")
    if not (endereco or "").strip():
        faltando.append("Endereço")

    if faltando:
        for f in faltando:
            st.error(f"{f} é obrigatório.")
        return

    with get_session() as session:
        create_student(
            session,
            name=format_student_name(nome),
            civil_name=format_student_name(civil) if civil else format_student_name(nome),
            address=addr,
            reference_point=ref,
            origin_school_id=origin["id"],
            origin_class_id=class_id,
            destination_school_1_id=dest1["id"],
            destination_school_2_id=dest2["id"] if dest2 else None,
            status=StudentStatus.DRAFT,
            responsible_signature=assinatura,
        )

    st.success(f"Aluno **{nome}** salvo.")
    st.rerun()


# ======================================================================
# ABA 3 - EDITAR DADOS
# ======================================================================
def _aba_editar(filtro_status: str = None, filtro_destino: int = None):
    st.subheader("Editar alunos cadastrados")

    if filtro_status == "sem_vaga":
        st.info("Mostrando alunos **sem vaga** (nenhuma escola definida).")
    if filtro_destino:
        st.info("Mostrando alunos que apontaram para uma escola específica como destino.")

    col1, col2, col3 = st.columns(3)
    with col1:
        f_origem = school_selector("Escola de origem", key="ed_origem", is_origin=True, allow_new=False)
    with col2:
        f_dest = school_selector(
            "Escola de destino", key="ed_dest", is_destination=True,
            allow_new=False, filtro_id=filtro_destino,
        )
    with col3:
        f_status = st.selectbox(
            "Status", ["Todos"] + opcoes_aluno(), key="ed_status"
        )

    busca = st.text_input("Buscar por nome", key="ed_busca")

    with get_session() as session:
        if filtro_status == "sem_vaga":
            alunos = [
                a for a in list_students(
                    session,
                    origin_school_id=f_origem["id"] if f_origem else None,
                    destination_school_id=f_dest["id"] if f_dest else None,
                    limit=2000,
                )
                if a.allocated_school_id is None
            ]
        else:
            alunos = list_students(
                session,
                origin_school_id=f_origem["id"] if f_origem else None,
                destination_school_id=f_dest["id"] if f_dest else None,
                status=para_valor_aluno(f_status),
                search=busca or None,
                limit=1000,
            )
        rows = [{
            "ID": a.id,
            "Nome": a.name,
            "Nome Civil": a.civil_name or "",
            "Endereço": a.address or "",
            "Turma": a.origin_class.name if a.origin_class else "",
            "Destino 1": a.destination_school_1.name if a.destination_school_1 else "",
            "Destino 2": a.destination_school_2.name if a.destination_school_2 else "",
            "Status": rotulo_aluno(a.status),
            "Alocado em": a.allocated_school.name if a.allocated_school else "",
            "Assinatura": bool(a.responsible_signature),
        } for a in alunos]

    if not rows:
        st.info("Nenhum aluno encontrado com os filtros atuais.")
        return

    st.caption(f"{len(rows)} aluno(s)")

    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True),
            "Turma": st.column_config.TextColumn("Turma", disabled=True),
            "Alocado em": st.column_config.TextColumn("Alocado em", disabled=True),
            "Status": st.column_config.SelectboxColumn(
                "Status", options=opcoes_aluno(), required=True
            ),
            "Assinatura": st.column_config.CheckboxColumn("Assinatura"),
        },
        key="ed_grid",
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("💾 Salvar alterações", type="primary", use_container_width=True):
            mudancas = 0
            for _, row in edited.iterrows():
                sid = int(row["ID"])
                original = df[df["ID"] == sid].iloc[0]
                if row.equals(original):
                    continue

                d1 = (row["Destino 1"] or "").strip()
                d2 = (row["Destino 2"] or "").strip()

                with get_session() as session:
                    update_student(
                        session,
                        sid,
                        name=format_student_name(row["Nome"]),
                        civil_name=format_student_name(row["Nome Civil"]) if row["Nome Civil"] else None,
                        address=row["Endereço"],
                        destination_school_1_id=get_or_create_school_from_name(d1, is_destination=True) if d1 else None,
                        destination_school_2_id=get_or_create_school_from_name(d2, is_destination=True) if d2 else None,
                        status=para_valor_aluno(row["Status"]),
                        responsible_signature=bool(row["Assinatura"]),
                    )
                mudancas += 1

            st.success(f"{mudancas} aluno(s) atualizado(s)." if mudancas else "Nenhuma alteração.")
            if mudancas:
                st.rerun()

    with c2:
        excluir = st.multiselect(
            "Excluir aluno(s)",
            options=[r["ID"] for r in rows],
            format_func=lambda x: next(r["Nome"] for r in rows if r["ID"] == x),
            key="ed_excluir",
        )
        if excluir and st.button("🗑️ Excluir selecionados", use_container_width=True):
            with get_session() as session:
                for sid in excluir:
                    delete_student(session, sid)
            st.success(f"{len(excluir)} aluno(s) excluído(s).")
            st.rerun()


# ======================================================================
# ABA 4 - EXPORTAR
# ======================================================================
def _aba_exportar():
    st.subheader("Exportar encaminhamento")

    col1, col2, col3 = st.columns(3)
    with col1:
        e_origem = school_selector("Escola de origem", key="ex_origem", is_origin=True, allow_new=False)
    with col2:
        e_dest = school_selector("Escola de destino", key="ex_dest", is_destination=True, allow_new=False)
    with col3:
        e_status = st.selectbox(
            "Status", ["Todos"] + opcoes_aluno(), key="ex_status"
        )

    with get_session() as session:
        alunos = list_students(
            session,
            origin_school_id=e_origem["id"] if e_origem else None,
            destination_school_id=e_dest["id"] if e_dest else None,
            status=para_valor_aluno(e_status),
            limit=2000,
        )

        if not alunos:
            st.info("Nenhum aluno para exportar com os filtros atuais.")
            return

        origem = session.get(School, e_origem["id"]) if e_origem else (
            alunos[0].origin_school if alunos[0].origin_school else None
        )
        destino = session.get(School, e_dest["id"]) if e_dest else (
            alunos[0].destination_school_1 if alunos[0].destination_school_1 else None
        )
        turma = alunos[0].origin_class.name if alunos[0].origin_class else ""

        if not (origem and destino):
            st.warning("Selecione a escola de origem e destino para exportar.")
            return

        st.caption(f"{len(alunos)} aluno(s) — destino: {destino.name}")

        c1, c2 = st.columns(2)
        with c1:
            xlsx = export_students_to_excel(alunos, destino, origem, turma)
            st.download_button(
                "📊 Baixar Excel (modelodownload)",
                open(xlsx, "rb").read(),
                file_name=f"encaminhamento_{destino.name}_{len(alunos)}alunos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c2:
            pdf = generate_student_list_pdf(alunos, destino, origem, turma)
            st.download_button(
                "📄 Baixar PDF",
                open(pdf, "rb").read(),
                file_name=f"encaminhamento_{destino.name}_{len(alunos)}alunos.pdf",
                mime="application/pdf",
                use_container_width=True,
            )


# ======================================================================
# PÁGINA
# ======================================================================
def render():
    sidebar_navigation()

    st.title("📥 Alunos")
    st.caption("Carregue planilhas, cadastre manualmente, revise e exporte o encaminhamento")

    # Filtros enviados pelo painel: abrem a aba certa ja filtrada
    ir_aba = st.session_state.pop("ir_aba", None)
    ir_status = st.session_state.pop("ir_aluno_status", None)

    if ir_status == "sem_vaga":
        ir_aba = "editar"

    abas = ["📤 Carregar Planilha", "✏️ Cadastro Manual", "📝 Editar Dados", "📊 Exportar"]
    if ir_aba in abas:
        inicial = abas.index(ir_aba)
    else:
        inicial = 0

    escolhida = seletor_abas(abas, inicial, chave="abas_alunos")

    if escolhida == 0:
        _aba_upload()
    elif escolhida == 1:
        _aba_manual()
    elif escolhida == 2:
        _aba_editar(filtro_status=ir_status)
    else:
        _aba_exportar()
