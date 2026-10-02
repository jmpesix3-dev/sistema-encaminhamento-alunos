import streamlit as st
from encaminhamento.utils.status import (
    opcoes_lote, para_valor_lote, rotulo_aluno, rotulo_lote,
)
from encaminhamento.ui.components import (
    sidebar_navigation, school_selector, render_batch_table, confirm_dialog,
    seletor_abas,
)
from encaminhamento.database import get_session
from encaminhamento.database.crud import (
    list_schools, list_students, list_batches, create_batch,
    get_batch, add_students_to_batch,
    get_students_for_batch, update_batch_status,
)
from encaminhamento.database.models import BatchStatus, StudentStatus
from encaminhamento.services.pdf_generator import generate_batch_pdf
from encaminhamento.services.status_tracker import auto_advance_batch_status


def render():
    sidebar_navigation()

    st.title("📦 Gestão de Lotes de Encaminhamento")
    st.caption("Crie e gerencie lotes de encaminhamento por escola de destino")

    # Filtro enviado pelo painel (etapa de lote)
    ir_status = st.session_state.pop("ir_lote_status", None)
    inicial = 1
    escolhida = seletor_abas(
        ["➕ Criar Lote", "📋 Gerenciar Lotes"], inicial, chave="abas_lotes"
    )
    # O widget guarda a aba antiga; nesta renderizacao a do filtro vale
    if ir_status:
        escolhida = inicial

    if escolhida == 0:
        st.subheader("Novo Lote de Encaminhamento")
        
        col1, col2 = st.columns(2)
        
        with col1:
            origin_school = school_selector(
                "Escola de Origem *",
                key="batch_origin_school",
                is_origin=True,
                allow_new=False
            )
            
            year = st.number_input("Ano Letivo *", value=2025, min_value=2020, max_value=2030, key="batch_year")
            
            if origin_school:
                origin_school_id = origin_school["id"]
                with get_session() as session:
                    from encaminhamento.database.crud import list_classes
                    classes = list_classes(session, school_id=origin_school_id)
                
                if classes:
                    class_options = {f"{c.name} ({c.year})": c for c in classes}
                    class_options["(Sem turma específica)"] = None
                    
                    selected_class = st.selectbox(
                        "Turma de Origem",
                        options=list(class_options.keys()),
                        key="batch_origin_class"
                    )
                    origin_class = class_options[selected_class]
                else:
                    origin_class = None
                    st.info("Nenhuma turma cadastrada")
        
        with col2:
            dest_school = school_selector(
                "Escola de Destino *",
                key="batch_dest_school",
                is_destination=True,
                allow_new=False
            )
            
            notes = st.text_area("Observações", key="batch_notes", placeholder="Observações opcionais sobre este lote")
        
        # Select students
        st.markdown("**Selecionar Alunos**")
        
        if origin_school and dest_school:
            origin_school_id = origin_school["id"]
            dest_school_id = dest_school["id"]
            
            with get_session() as session:
                # Get students from origin school going to this destination
                available_students = list_students(
                    session,
                    origin_school_id=origin_school_id,
                    destination_school_id=dest_school_id,
                    status=StudentStatus.DRAFT,
                    limit=500
                )
                
                # Also include PENDING students not in any batch
                pending_students = list_students(
                    session,
                    origin_school_id=origin_school_id,
                    destination_school_id=dest_school_id,
                    status=StudentStatus.PENDING,
                    limit=500
                )
                
                # Combine and deduplicate
                all_students = {s.id: s for s in available_students}
                for s in pending_students:
                    all_students[s.id] = s
                available_students = list(all_students.values())
            
            if available_students:
                st.caption(f"{len(available_students)} aluno(s) disponíveis para este par de escolas")
                
                # Show as table with checkboxes
                student_data = []
                for s in available_students:
                    student_data.append({
                        "Selecionar": False,
                        "ID": s.id,
                        "Nome": s.name,
                        "Endereço": s.full_address,
                        "Status": rotulo_aluno(s.status),
                        "Turma": s.origin_class.name if s.origin_class else "",
                    })
                
                df = st.data_editor(
                    student_data,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Selecionar": st.column_config.CheckboxColumn("✓"),
                        "ID": st.column_config.NumberColumn("ID", disabled=True),
                        "Status": st.column_config.TextColumn("Status", disabled=True),
                    },
                    key="batch_student_selector"
                )
                
                selected_ids = [int(row["ID"]) for row in df if row["Selecionar"]]
                
                if selected_ids:
                    st.info(f"{len(selected_ids)} aluno(s) selecionado(s)")
                    
                    if st.button("📦 Criar Lote com Selecionados", type="primary", use_container_width=True):
                        with get_session() as session:
                            batch = create_batch(
                                session,
                                origin_school_id=origin_school_id,
                                destination_school_id=dest_school_id,
                                year=year,
                                origin_class_id=origin_class.id if origin_class else None,
                                notes=notes
                            )
                            add_students_to_batch(session, batch.id, selected_ids)
                            
                            # Update student status to PENDING
                            for sid in selected_ids:
                                from encaminhamento.services.status_tracker import transition_student_status
                                transition_student_status(sid, StudentStatus.PENDING)
                        
                        st.success(f"✅ Lote #{batch.id} criado com {len(selected_ids)} aluno(s)!")
                        st.rerun()
                else:
                    st.button("📦 Criar Lote", disabled=True, use_container_width=True)
            else:
                st.warning("Nenhum aluno disponível para esta combinação de escolas")
        else:
            st.info("Selecione escola de origem e destino para ver alunos disponíveis")
    
    elif escolhida == 1:
        st.subheader("Lotes Existentes")

        # Filtros
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            filter_origin = school_selector("Origem", key="batch_filter_origin", is_origin=True, allow_new=False)
        with col2:
            filter_dest = school_selector("Destino", key="batch_filter_dest", is_destination=True, allow_new=False)
        with col3:
            filter_year = st.selectbox(
                "Ano", ["Todos"] + [str(a) for a in range(2020, 2031)],
                key="batch_filter_year",
            )
        with col4:
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
                destination_school_id=filter_dest["id"] if filter_dest else None,
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
                            "origin_class": batch.origin_class.name if batch.origin_class else "N/A",
                            "year": batch.year,
                            "student_count": batch.student_count,
                            "status": rotulo_lote(batch.status),
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
                        st.markdown(f"Status: {batch_info['status'].upper()}")
                    
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
                        if batch_info["status"] in [BatchStatus.DRAFT.value, BatchStatus.GENERATED.value]:
                            if st.button("📄 Gerar PDF", use_container_width=True, key=f"gen_pdf_{batch_info['id']}"):
                                pdf_path = generate_batch_pdf(batch_info["id"])
                                with get_session() as session:
                                    update_batch_status(session, batch_info["id"], BatchStatus.GENERATED, pdf_path)
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
                                st.success("Lote concluído!")
                                st.rerun()
                    
                    # Email dialog
                    if st.session_state.get(f"send_email_batch_{batch.id}"):
                        st.divider()
                        st.subheader("Enviar Email")
                        
                        to_emails = st.text_area(
                            "Emails destinatários (um por linha):",
                            key=f"email_to_{batch.id}",
                            placeholder="diretor@escola.com\nsecretaria@escola.com"
                        )
                        
                        custom_msg = st.text_area(
                            "Mensagem personalizada:",
                            key=f"email_msg_{batch.id}"
                        )
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("📧 Enviar", key=f"confirm_send_{batch.id}"):
                                emails = [e.strip() for e in to_emails.split("\n") if e.strip()]
                                if emails:
                                    from encaminhamento.services.email_sender import send_batch_notification
                                    result = send_batch_notification(
                                        batch.id, emails, batch.pdf_path, custom_msg
                                    )
                                    if result.success:
                                        st.success(result.message)
                                    else:
                                        st.error(f"Erro: {result.message} - {result.error}")
                                else:
                                    st.error("Informe pelo menos um email")
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
            st.info("Nenhum lote encontrado. Crie o primeiro na aba 'Criar Lote'.")