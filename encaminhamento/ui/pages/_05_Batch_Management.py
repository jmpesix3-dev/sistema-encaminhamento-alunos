import streamlit as st
from encaminhamento.utils.status import (
    opcoes_lote, para_valor_lote, rotulo_aluno, rotulo_lote,
)
from encaminhamento.utils.helpers import parse_email_list
from encaminhamento.ui.components import (
    sidebar_navigation, school_selector, render_batch_table, confirm_dialog,
    seletor_abas,
)
from encaminhamento.database import get_session
from encaminhamento.database.crud import (
    list_schools, list_students, list_batches,
    get_batch, get_students_for_batch, update_batch_status,
    create_batches_from_allocation,
)
from encaminhamento.database.models import (
    BatchStatus, Student, StudentStatus,
)
from encaminhamento.services.pdf_generator import generate_batch_pdf
from encaminhamento.services.status_tracker import auto_advance_batch_status


def render():
    sidebar_navigation()

    st.title("📦 Gestão de Lotes de Encaminhamento")
    st.caption("Crie e gerencie lotes de encaminhamento por escola de destino")

    # Filtro enviado pelo painel (etapa de lote)
    ir_status = st.session_state.pop("ir_lote_status", None)
    inicial = 0
    escolhida = seletor_abas(
        ["📋 Gerenciar Lotes"], inicial, chave="abas_lotes",
        forcar=bool(ir_status),
    )
    if ir_status:
        escolhida = inicial

    st.subheader("Lotes Existentes")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("Visualize e gerencie os lotes existentes.")
    with col2:
        with get_session() as session:
            qtd_alocados = session.query(Student).filter(
                Student.allocated_school_id.isnot(None)
            ).count()
        if qtd_alocados > 0 and st.button("📦 Criar Lotes da Alocação", use_container_width=True):
            with get_session() as session:
                res = create_batches_from_allocation(session, notes="Criado a partir da alocação automática")
            st.success(
                f"✅ {res['lotes_criados']} novo(s), "
                f"{res['lotes_atualizados']} atualizado(s), "
                f"{res['alunos_adicionados']} aluno(s)!"
            )
            st.rerun()

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_origin = school_selector("Origem", key="batch_filter_origin", is_origin=True, allow_new=False)
    with col2:
        filter_year = st.selectbox(
            "Ano", ["Todos"] + [str(a) for a in range(2020, 2031)],
            key="batch_filter_year",
        )
    with col3:
        # Se veio do painel, define o status antes de criar o widget
        # (o index= so valeria na primeira renderizacao)
        if ir_status in ("draft", "generated", "sent", "completed"):
            rotulo_ir = rotulo_lote(ir_status)
            if rotulo_ir in opcoes_lote():
                st.session_state["batch_filter_status"] = rotulo_ir
        filter_status = st.selectbox(
            "Status", ["Todos"] + opcoes_lote(), key="batch_filter_status"
        )

    if ir_status and ir_status in ("draft", "generated", "sent", "completed"):
        st.info(f"Mostrando lotes com status **{rotulo_lote(ir_status)}**.")

    with get_session() as session:
        batches = list_batches(
            session,
            origin_school_id=filter_origin["id"] if filter_origin else None,
            year=int(filter_year) if filter_year != "Todos" else None,
            status=para_valor_lote(filter_status),
        )
        # Extrai os rotulos dos lotes ainda dentro da sessao
        rotulos = {
            b.id: f"Lote #{b.id} - {b.destination_school.name if b.destination_school else '?'} "
                  f"({b.student_count} alunos)"
            for b in batches
        }

    if batches:
        render_batch_table(batches, show_actions=True)

        st.divider()

        # Batch details
        selected_batch_id = st.selectbox(
            "Ver detalhes do lote:",
            options=[b.id for b in batches],
            format_func=lambda x: rotulos.get(x, f"Lote #{x}"),
            key="selected_batch_detail"
        )
        
        if selected_batch_id:
            with get_session() as session:
                batch = get_batch(session, selected_batch_id)
                
                if batch:
                    # Extract all needed data while session is open
                    batch_info = {
                        "id": batch.id,
                        "origin_school": batch.origin_school.name if batch.origin_school else "",
                        "destination_school": batch.destination_school.name if batch.destination_school else "",
                        "destination_school_email": batch.destination_school.email if batch.destination_school else "",
                        "origin_class": batch.origin_class.name if batch.origin_class else "N/A",
                        "year": batch.year,
                        "student_count": batch.student_count,
                        # enum cru: as comparacoes com BatchStatus.value
                        # em diante dependem do valor, nao do rotulo
                        "status": batch.status,
                        "status_label": rotulo_lote(batch.status),
                        "notes": batch.notes,
                        "pdf_path": batch.pdf_path,
                    }
                    
                    students = get_students_for_batch(session, batch.id)
                    student_data = []
                    for idx, s in enumerate(students, 1):
                        student_data.append({
                            "Nº": idx,
                            "Nome": s.name,
                            "Endereço": s.full_address,
                            "Status": rotulo_aluno(s.status),
                        })
                    
                    # Store in session state for use outside session
                    st.session_state.batch_info = batch_info
                    st.session_state.batch_students = student_data
                    st.session_state.selected_batch_id = batch.id
                    st.session_state.batch_status = batch.status
                    st.session_state.batch_pdf_path = batch.pdf_path
                    st.session_state.batch_origin_class = batch.origin_class.name if batch.origin_class else ""
                    st.session_state.batch_destination_school = batch.destination_school.name if batch.destination_school else ""
                    st.session_state.batch_origin_school = batch.origin_school.name if batch.origin_school else ""
                
            # Render outside session
            if "batch_info" in st.session_state:
                batch_info = st.session_state.batch_info
                st.markdown(f"### Lote #{batch_info['id']}")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Escola Origem", batch_info["origin_school"])
                    st.metric("Turma", batch_info["origin_class"])
                with col2:
                    st.metric("Escola Destino", batch_info["destination_school"])
                    st.metric("Ano", batch_info["year"])
                with col3:
                    st.metric("Alunos", batch_info["student_count"])
                    st.markdown(f"Status: {batch_info['status_label'].upper()}")
                
                if batch_info["notes"]:
                    st.caption(f"Observações: {batch_info['notes']}")
                
                # Students in batch
                st.markdown("**Alunos neste Lote:**")
                if st.session_state.get("batch_students"):
                    st.dataframe(st.session_state.batch_students, use_container_width=True, hide_index=True)
                
                # Actions
                st.divider()
                st.markdown("**Ações:**")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if batch_info["status"] in [BatchStatus.DRAFT, BatchStatus.GENERATED]:
                        if st.button("📄 Gerar PDF", use_container_width=True, key=f"gen_pdf_{batch_info['id']}"):
                            try:
                                pdf_path = generate_batch_pdf(batch_info["id"])
                            except ValueError as exc:
                                st.error(str(exc))
                            else:
                                with get_session() as session:
                                    update_batch_status(session, batch_info["id"], BatchStatus.GENERATED, pdf_path)
                                    for s in get_students_for_batch(session, batch_info["id"]):
                                        from encaminhamento.services.status_tracker import transition_student_status
                                        transition_student_status(s.id, StudentStatus.SENT)
                                st.success("PDF gerado!")
                                st.rerun()
                
                with col2:
                    if batch.status == BatchStatus.GENERATED and batch.pdf_path:
                        if st.button("📤 Enviar por Email", use_container_width=True, key=f"send_email_{batch.id}"):
                            st.session_state[f"send_email_batch_{batch.id}"] = True
                            st.rerun()
                
                with col3:
                    if batch.status in [BatchStatus.GENERATED, BatchStatus.SENT]:
                        if st.button("✅ Marcar Como Enviado", use_container_width=True, key=f"mark_sent_{batch.id}"):
                            with get_session() as session:
                                update_batch_status(session, batch.id, BatchStatus.SENT)
                                # Update students
                                for s in students:
                                    from encaminhamento.services.status_tracker import transition_student_status
                                    transition_student_status(s.id, StudentStatus.SENT)
                            st.success("Lote marcado como enviado!")
                            st.rerun()
                
                with col4:
                    if batch.status == BatchStatus.SENT:
                        if st.button("🏁 Concluir", use_container_width=True, key=f"complete_{batch.id}"):
                            with get_session() as session:
                                update_batch_status(session, batch.id, BatchStatus.COMPLETED)
                                for s in get_students_for_batch(session, batch.id):
                                    from encaminhamento.services.status_tracker import transition_student_status
                                    transition_student_status(s.id, StudentStatus.CONFIRMED)
                            st.success("Lote concluído!")
                            st.rerun()
                
                # Email dialog
                if st.session_state.get(f"send_email_batch_{batch.id}"):
                    st.divider()
                    st.subheader("Enviar Email")
                    
                    school_email = batch_info.get("destination_school_email", "")
                    to_emails = st.text_area(
                        "Emails destinatários (um por linha ou separados por vírgula):",
                        key=f"email_to_{batch.id}",
                        value=school_email,
                        placeholder="diretor@escola.com\nsecretaria@escola.com"
                    )
                    
                    cc_emails = st.text_area(
                        "CC (opcional, um por linha ou separados por vírgula):",
                        key=f"email_cc_{batch.id}",
                        placeholder="coordenador@rede.edu.br"
                    )
                    
                    custom_msg = st.text_area(
                        "Mensagem personalizada:",
                        key=f"email_msg_{batch.id}"
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("📧 Enviar", key=f"confirm_send_{batch.id}"):
                            emails = parse_email_list(to_emails)
                            cc = parse_email_list(cc_emails) if cc_emails else None
                            if emails:
                                from encaminhamento.services.email_sender import send_batch_notification
                                result = send_batch_notification(
                                    batch.id, emails, batch.pdf_path, custom_msg, cc=cc
                                )
                                if result.success:
                                    st.success(result.message)
                                    st.session_state[f"send_email_batch_{batch.id}"] = False
                                    st.rerun()
                                else:
                                    st.error(f"Erro: {result.message} - {result.error}")
                            else:
                                st.error("Informe pelo menos um email válido")
                    with col2:
                        if st.button("❌ Cancelar", key=f"cancel_send_{batch.id}"):
                            st.session_state[f"send_email_batch_{batch.id}"] = False
                            st.rerun()
                
                # Delete batch
                if confirm_dialog("Excluir Lote", key=f"delete_batch_{batch.id}"):
                    with get_session() as session:
                        session.delete(batch)
                    st.success("Lote excluído!")
                    st.rerun()
    else:
        st.info("Nenhum lote encontrado. Os lotes são criados automaticamente pela alocação.")
