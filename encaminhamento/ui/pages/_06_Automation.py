import streamlit as st
import pandas as pd
from pathlib import Path
from encaminhamento.utils.status import rotulo_aluno, rotulo_lote
from encaminhamento.utils.helpers import validar_emails
from encaminhamento.ui.components import sidebar_navigation, seletor_abas
from encaminhamento.database import get_session
from encaminhamento.database.crud import list_batches, list_schools, create_sent_email, list_sent_emails
from encaminhamento.database.models import BatchStatus
from encaminhamento.services.pdf_generator import generate_batch_pdf
from encaminhamento.services.email_sender import send_batch_notification, test_smtp_connection, EmailResult
from encaminhamento.services.status_tracker import get_status_summary, auto_advance_batch_status, bulk_transition_students
from encaminhamento.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_USE_TLS, EMAIL_FROM, NOME_SISTEMA


def render():
    sidebar_navigation()
    
    st.title("⚙️ Automação")
    st.caption("Gerencie automações: geração de PDF, envio de emails, atualização de status")
    
    # Aba enviada pelo painel
    ir_email = st.session_state.pop("ir_email", False)
    abas = ["📄 PDFs", "📧 Emails", "🔧 Status & Configuração"]
    inicial = 1 if ir_email else 0
    
    escolhida = seletor_abas(abas, inicial, chave="abas_automacao")
    
    if escolhida == 0:
        st.subheader("Geração de PDFs em Lote")
        
        with get_session() as session:
            batches = list_batches(session, status=BatchStatus.DRAFT)
            batches_generated = list_batches(session, status=BatchStatus.GENERATED)
        
        all_batches = batches + batches_generated
        
        if all_batches:
            st.caption(f"{len(batches)} lote(s) em rascunho, {len(batches_generated)} com PDF gerado")
            
            # Extract batch data while session is open to avoid detached instance errors
            batch_options = {}
            for b in all_batches:
                with get_session() as session:
                    from encaminhamento.database.crud import get_batch
                    batch = get_batch(session, b.id)
                    if batch:
                        label = f"Lote #{batch.id} - {batch.destination_school.name if batch.destination_school else '—'} ({batch.student_count} alunos) - {rotulo_lote(batch.status)}"
                        batch_options[label] = batch.id
            
            selected = st.multiselect(
                "Selecionar lotes para gerar PDF:",
                options=list(batch_options.keys()),
                key="pdf_batch_select"
            )
            
            if selected:
                if st.button("📄 Gerar PDFs Selecionados", type="primary"):
                    progress = st.progress(0)
                    status_text = st.empty()
                    
                    for i, key in enumerate(selected):
                        batch_id = batch_options[key]
                        status_text.text(f"Gerando PDF para Lote #{batch_id}...")
                        
                        try:
                            pdf_path = generate_batch_pdf(batch_id)
                            with get_session() as session:
                                from encaminhamento.database.crud import update_batch_status
                                update_batch_status(session, batch_id, BatchStatus.GENERATED, pdf_path)
                            status_text.text(f"✅ Lote #{batch_id} - PDF gerado")
                        except Exception as e:
                            status_text.text(f"❌ Lote #{batch_id} - Erro: {e}")
                        
                        progress.progress((i + 1) / len(selected))
                    
                    status_text.text("Concluído!")
                    st.success(f"{len(selected)} PDF(s) gerado(s) com sucesso!")
                    st.rerun()
            
            # Show existing PDFs
            st.divider()
            st.subheader("PDFs Existentes")
            for b in batches_generated:
                if b.pdf_path:
                    import os
                    if os.path.exists(b.pdf_path):
                        with open(b.pdf_path, "rb") as f:
                            st.download_button(
                                f"⬇️ Lote #{b.id} - {b.destination_school.name if b.destination_school else '—'}",
                                f.read(),
                                file_name=f"encaminhamento_lote_{b.id}.pdf",
                                mime="application/pdf",
                                key=f"download_pdf_{b.id}"
                            )
        else:
            st.info("Nenhum lote em rascunho ou gerado. Crie lotes na 'Gestão de Lotes'.")
    
    elif escolhida == 1:
        st.subheader("Envio de Emails")
        
        # Select batches ready to send
        with get_session() as session:
            ready_batches = list_batches(session, status=BatchStatus.GENERATED)
            sent_batches = list_batches(session, status=BatchStatus.SENT)
        
        sendable = ready_batches + sent_batches
        
        if sendable:
            st.caption(f"{len(ready_batches)} pronto(s) para envio, {len(sent_batches)} já enviado(s)")
            
            # Extract batch data while session is open to avoid detached instance errors
            batch_options = {}
            for b in sendable:
                with get_session() as session:
                    from encaminhamento.database.crud import get_batch
                    batch = get_batch(session, b.id)
                    if batch:
                        label = f"Lote #{batch.id} - {batch.destination_school.name if batch.destination_school else '—'} ({batch.student_count} alunos) - {rotulo_lote(batch.status)}"
                        batch_options[label] = batch.id
            
            selected_key = st.selectbox(
                "Selecionar lote:",
                options=list(batch_options.keys()),
                key="email_batch_select"
            )
            
            if selected_key:
                batch_id = batch_options[selected_key]
                summary = get_status_summary(batch_id)
                
                with get_session() as session:
                    from encaminhamento.database.crud import get_batch
                    batch = get_batch(session, batch_id)
                    if batch:
                        school_email = batch.destination_school.email if batch.destination_school else ""
                        dest_name = batch.destination_school.name if batch.destination_school else "—"
                        origin_name = batch.origin_school.name if batch.origin_school else "—"

                        # Informacoes do lote em linhas limpas (sem indentacao) + status dos alunos
                        info = (
                            f"**Lote #{batch.id}**\n\n"
                            f"Escola Destino: {dest_name}\n"
                            f"Escola Origem: {origin_name}\n"
                            f"Alunos: {batch.student_count}\n"
                            f"Status: {rotulo_lote(batch.status)}"
                        )
                        st.info(info)

                        if summary.get("by_status"):
                            status_items = [
                                f"{status}: {count}" for status, count in summary["by_status"].items() if count > 0
                            ]
                            if status_items:
                                st.caption("Status dos alunos: " + ", ".join(status_items))

                        if not SMTP_USER or not SMTP_PASSWORD:
                            st.warning("⚠️ SMTP não configurado. Configure SMTP_USER e SMTP_PASSWORD no .env.")

                        # Campos de envio em duas colunas
                        col_to, col_cc = st.columns(2)
                        with col_to:
                            to_emails = st.text_area(
                                "Emails destinatários (um por linha ou separados por vírgula):",
                                value=school_email,
                                key="email_to_addresses",
                                placeholder="diretor@escoladestino.com\nsecretaria@escoladestino.com",
                            )
                        with col_cc:
                            cc_emails = st.text_area(
                                "CC (opcional, um por linha ou separados por vírgula):",
                                key="email_cc_addresses",
                                placeholder="coordenador@rede.edu.br",
                            )

                        # Validacao: preview de validos e sinalizacao de invalidos
                        validacao = validar_emails(to_emails)
                        validos = validacao["validos"]
                        invalidos = validacao["invalidos"]

                        if invalidos:
                            st.error(f"❌ {len(invalidos)} email(s) inválido(s): {', '.join(invalidos)}")
                        if validos:
                            preview = ", ".join(validos[:5])
                            if len(validos) > 5:
                                preview += f" +{len(validos) - 5} mais"
                            st.caption(f"Destinatários válidos ({len(validos)}): {preview}")
                        else:
                            st.caption("Nenhum destinatário válido.")

                        custom_message = st.text_area(
                            "Mensagem personalizada (opcional):",
                            key="email_custom_msg",
                            placeholder="Mensagem adicional para o email...",
                        )

                        include_pdf = st.checkbox("Anexar PDF do encaminhamento", value=True, key="email_attach_pdf")

                        if include_pdf and not (batch.pdf_path and Path(batch.pdf_path).exists()):
                            st.warning("⚠️ Nenhum PDF gerado para este lote. O email será enviado sem anexo.")

                        pode_enviar = bool(validos) and not invalidos
                        rotulo_btn = f"📧 Enviar Email ({len(validos)})" if validos else "📧 Enviar Email"
                        if st.button(rotulo_btn, type="primary", disabled=not pode_enviar):
                            emails = validos
                            cc = validar_emails(cc_emails)["validos"] if cc_emails else None

                            pdf_path = batch.pdf_path if (include_pdf and batch.pdf_path and Path(batch.pdf_path).exists()) else None

                            with st.spinner("Enviando email..."):
                                result = send_batch_notification(
                                    batch.id, emails, pdf_path, custom_message, cc=cc
                                )

                            # Registra o envio no historico (sucesso ou falha)
                            subject = f"{NOME_SISTEMA} - {dest_name} - {batch.student_count} alunos"
                            with get_session() as session_log:
                                create_sent_email(
                                    session_log,
                                    batch_id=batch.id,
                                    to_emails=emails,
                                    cc_emails=cc,
                                    subject=subject,
                                    pdf_attached=bool(pdf_path),
                                    success=result.success,
                                    error_message=result.error,
                                )

                            if result.success:
                                st.success(f"✅ {result.message}")
                                if batch.status == BatchStatus.GENERATED:
                                    with get_session() as session:
                                        from encaminhamento.database.crud import update_batch_status
                                        update_batch_status(session, batch.id, BatchStatus.SENT)
                                    st.rerun()
                            else:
                                st.error(f"❌ {result.message}: {result.error}")
                    else:
                        st.info("Nenhum lote com PDF gerado. Gere PDFs na aba 'PDFs' primeiro.")
    
        st.divider()
        with st.expander("📋 Histórico de envios (últimos 50)", expanded=False):
            with get_session() as session:
                historicos = list_sent_emails(session, limit=50)
                rows = []
                for h in historicos:
                    dest = h.batch.destination_school.name if (h.batch and h.batch.destination_school) else "—"
                    rows.append({
                        "Data": h.sent_at.strftime("%d/%m/%Y %H:%M") if h.sent_at else "",
                        "Lote": f"#{h.batch_id}" if h.batch_id else "—",
                        "Destino": dest,
                        "Para": h.to_emails,
                        "CC": h.cc_emails or "",
                        "Assunto": h.subject,
                        "Anexo": "Sim" if h.pdf_attached else "Não",
                        "Status": "✅ Enviado" if h.success else "❌ Falha",
                        "Erro": h.error_message or "",
                    })
            if rows:
                df_hist = pd.DataFrame(rows)
                st.dataframe(df_hist, hide_index=True, width="stretch")
            else:
                st.caption("Nenhum envio registrado ainda.")
    
    elif escolhida == 2:
        st.subheader("Status e Configurações")
        
        st.markdown("**Atualização Automática de Status dos Lotes**")
        
        with get_session() as session:
            all_batches = list_batches(session)
            # Extract batch IDs and statuses to avoid detached instances
            batch_data = [(b.id, b.status.value) for b in all_batches]
        
        if batch_data:
            if st.button("🔄 Atualizar Status de Todos os Lotes"):
                updated = 0
                for batch_id, old_status in batch_data:
                    new_status = auto_advance_batch_status(batch_id)
                    if new_status.value != old_status:
                        updated += 1
                        st.caption(f"Lote #{batch_id}: {rotulo_lote(old_status)} → {rotulo_lote(new_status)}")
                
                if updated > 0:
                    st.success(f"✅ {updated} lote(s) atualizado(s)!")
                else:
                    st.info("Nenhuma atualização necessária")
                st.rerun()
        
        st.divider()
        
        st.markdown("**Transição Manual de Status de Alunos**")

        # Contagem de alunos por status
        with get_session() as session:
            from sqlalchemy import select, func
            from encaminhamento.database.models import Student, StudentStatus

            draft_count = session.execute(select(func.count(Student.id)).where(Student.status == StudentStatus.DRAFT)).scalar() or 0
            pending_count = session.execute(select(func.count(Student.id)).where(Student.status == StudentStatus.PENDING)).scalar() or 0
            sent_count = session.execute(select(func.count(Student.id)).where(Student.status == StudentStatus.SENT)).scalar() or 0
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.caption(f"Rascunho: {draft_count}")
            if draft_count > 0 and st.button("📤 Rascunho → Pendente", key="draft_to_pending"):
                with get_session() as session:
                    from encaminhamento.services.status_tracker import bulk_transition_students
                    from encaminhamento.database.crud import list_students
                    students = list_students(session, status=StudentStatus.DRAFT, limit=100)
                    ids = [s.id for s in students]
                    result = bulk_transition_students(ids, StudentStatus.PENDING)
                st.success(f"{len(result['success'])} aluno(s) movidos para Pendente")
                st.rerun()
        
        with col2:
            st.caption(f"Pendente: {pending_count}")
            if pending_count > 0 and st.button("📤 Pendente → Enviado", key="pending_to_sent"):
                with get_session() as session:
                    from encaminhamento.services.status_tracker import bulk_transition_students
                    from encaminhamento.database.crud import list_students
                    students = list_students(session, status=StudentStatus.PENDING, limit=100)
                    ids = [s.id for s in students]
                    result = bulk_transition_students(ids, StudentStatus.SENT)
                st.success(f"{len(result['success'])} aluno(s) movidos para Enviado")
                st.rerun()
        
        with col3:
            st.caption(f"Enviado: {sent_count}")
            if sent_count > 0 and st.button("✅ Enviado → Confirmado", key="sent_to_confirmed"):
                with get_session() as session:
                    from encaminhamento.services.status_tracker import bulk_transition_students
                    from encaminhamento.database.crud import list_students
                    students = list_students(session, status=StudentStatus.SENT, limit=100)
                    ids = [s.id for s in students]
                    result = bulk_transition_students(ids, StudentStatus.CONFIRMED)
                st.success(f"{len(result['success'])} aluno(s) movidos para Confirmado")
                st.rerun()
        
        st.divider()
        
        # Batch status transitions
        st.markdown("**Transição Manual de Status de Lotes**")
        
        for status in BatchStatus:
            with get_session() as session:
                batches_in_status = list_batches(session, status=status)
            
            if batches_in_status:
                with st.expander(f"{rotulo_lote(status)} ({len(batches_in_status)} lote(s))"):
                    for batch in batches_in_status:
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.caption(f"Lote #{batch.id} - {batch.destination_school.name if batch.destination_school else '—'}")
                        with col2:
                            next_statuses = {
                                BatchStatus.DRAFT: BatchStatus.GENERATED,
                                BatchStatus.GENERATED: BatchStatus.SENT,
                                BatchStatus.SENT: BatchStatus.COMPLETED,
                            }
                            if batch.status in next_statuses:
                                if st.button(f"→ {next_statuses[batch.status].value}", key=f"advance_{batch.id}"):
                                    with get_session() as session:
                                        from encaminhamento.database.crud import update_batch_status
                                        update_batch_status(session, batch.id, next_statuses[batch.status])
                                    st.success(f"Lote #{batch.id} avançado!")
                                    st.rerun()
                        with col3:
                            if st.button("🔄", key=f"auto_advance_{batch.id}", help="Auto-avançar baseado nos alunos"):
                                auto_advance_batch_status(batch.id)
                                st.rerun()
    
        st.divider()

        st.markdown("**Configurações do Sistema**")

        with st.expander("🔧 Testar Configuração SMTP", expanded=not (SMTP_USER and SMTP_PASSWORD)):
            if st.button("Testar Conexão SMTP"):
                with st.spinner("Testando..."):
                    result = test_smtp_connection()
                if result.success:
                    st.success(f"✅ {result.message}")
                else:
                    st.error(f"❌ {result.message}: {result.error}")

            st.caption(f"Servidor: {SMTP_HOST}:{SMTP_PORT}")
            st.caption(f"Usuário: {SMTP_USER}")
            st.caption(f"Remetente: {EMAIL_FROM}")
        
        st.markdown("**Configuração de Email (variáveis de ambiente)**")
        
        config_items = {
            "SMTP_HOST": SMTP_HOST,
            "SMTP_PORT": str(SMTP_PORT),
            "SMTP_USER": SMTP_USER,
            "SMTP_PASSWORD": "••••••••" if SMTP_PASSWORD else "Não configurado",
            "SMTP_USE_TLS": str(SMTP_USE_TLS),
            "EMAIL_FROM": EMAIL_FROM,
        }
        
        for key, value in config_items.items():
            st.text_input(key, value=value, disabled=True, key=f"config_{key}")
        
        st.info("Configure estas variáveis no arquivo `.env` ou nas variáveis de ambiente do sistema.")
        
        st.divider()
        
        st.markdown("**Diretórios de Dados**")
        from encaminhamento.config import DATA_DIR, EXCEL_IMPORT_DIR, EXCEL_EXPORT_DIR, PDF_EXPORT_DIR, BACKUP_DIR
        
        dirs = {
            "Dados": DATA_DIR,
            "Importação": EXCEL_IMPORT_DIR,
            "Exportação": EXCEL_EXPORT_DIR,
            "PDFs": PDF_EXPORT_DIR,
            "Backup": BACKUP_DIR,
        }
        
        for name, path in dirs.items():
            st.text_input(name, value=str(path), disabled=True, key=f"dir_{name}")
        
        st.divider()
        
        st.markdown("**Backup e Manutenção**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📦 Criar Backup do Banco", use_container_width=True):
                import shutil
                from datetime import datetime
                from encaminhamento.config import DATABASE_URL
                
                db_path = DATABASE_URL.replace("sqlite:///", "")
                backup_name = f"encaminhamento_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                backup_path = BACKUP_DIR / backup_name
                
                try:
                    shutil.copy2(db_path, backup_path)
                    st.success(f"Backup criado: {backup_name}")
                except Exception as e:
                    st.error(f"Erro ao criar backup: {e}")
        
        with col2:
            if st.button("🧹 Limpar Arquivos Temporários", use_container_width=True):
                import os
                cleaned = 0
                for dir_path in [EXCEL_IMPORT_DIR, EXCEL_EXPORT_DIR, PDF_EXPORT_DIR]:
                    for f in dir_path.glob("*"):
                        if f.is_file() and f.suffix in [".tmp", ".temp"]:
                            f.unlink()
                            cleaned += 1
                st.success(f"{cleaned} arquivo(s) temporário(s) removido(s)")