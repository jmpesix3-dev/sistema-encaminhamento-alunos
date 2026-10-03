import streamlit as st
from typing import Optional
from encaminhamento.database.models import School
from encaminhamento.database.crud import list_schools, search_schools
from encaminhamento.database import get_session


def ir_para(pagina: str, **estado):
    """
    Navega para outra pagina ja deixando filtros definidos.

    As chaves passadas em `estado` viram `ir_<chave>` no session_state,
    e a pagina de destino aplica e limpa.
    """
    for chave, valor in estado.items():
        st.session_state[f"ir_{chave}"] = valor
    st.session_state.current_page = pagina
    st.rerun()


def seletor_abas(
    nomes: list,
    inicial: int = 0,
    chave: str = "abas",
    forcar: bool = False,
) -> int:
    """
    Seletor de abas que abre numa aba especifica.

    O st.tabs() desta versao do Streamlit nao aceita `index`, entao
    usamos o segmented_control e devolvemos o indice escolhido. Quem
    chama renderiza apenas o conteudo da aba selecionada.

    forcar=True sobrescreve a aba atual - use quando o usuario veio
    por redirecionamento do painel e precisa abrir numa aba especifica.
    """
    if inicial >= len(nomes):
        inicial = 0

    atual = st.session_state.get(chave)

    # Definir no session_state ANTES de criar o widget e o jeito confiavel:
    # o parametro `default` so vale na primeira renderizacao, e num
    # redirecionamento do painel essa ja foi a primeira.
    if forcar or atual not in nomes:
        st.session_state[chave] = nomes[inicial]
        # Com o valor no session_state, passar default gera aviso
        escolhido = st.segmented_control(
            "Seção",
            nomes,
            selection_mode="single",
            label_visibility="collapsed",
            key=chave,
        )
    else:
        escolhido = st.segmented_control(
            "Seção",
            nomes,
            default=nomes[inicial],
            selection_mode="single",
            label_visibility="collapsed",
            key=chave,
        )

    if escolhido in nomes:
        return nomes.index(escolhido)
    return inicial


def school_selector(
    label: str,
    key: str,
    is_origin: bool = None,
    is_destination: bool = None,
    allow_new: bool = True,
    placeholder: str = "Selecione ou digite para buscar...",
    filtro_id: int = None,
) -> Optional[dict]:
    """
    Seletor de escola com busca e criacao.

    Devolve um dicionario com id, name e code. Para pre-selecionar,
    passe filtro_id com o id da escola desejada.
    """
    with get_session() as session:
        schools = list_schools(session, is_origin=is_origin, is_destination=is_destination)
        # Extract data while session is open
        school_data = [{"id": s.id, "name": s.name, "code": s.code} for s in schools]
    
    options = {f"{s['name']} ({s['code']})" if s['code'] else s['name']: s for s in school_data}
    option_names = list(options.keys())

    # Pre-seleciona pelo id (usado quando o painel redireciona com filtro)
    if filtro_id is not None and key not in st.session_state:
        for nome, item in options.items():
            if item["id"] == filtro_id:
                st.session_state[key] = nome
                break

    selected_name = st.selectbox(
        label,
        options=[""] + option_names,
        format_func=lambda x: x if x else placeholder,
        key=key
    )
    
    if selected_name and selected_name in options:
        return options[selected_name]
    
    if allow_new and selected_name and selected_name not in options:
        # User typed a new name
        with get_session() as session:
            new_school = search_schools(session, selected_name)
            if new_school:
                s = new_school[0]
                st.info(f"Encontrado: {s.name}")
                return {"id": s.id, "name": s.name, "code": s.code}
    
    return None


def _selecionar_aba(abas_atual, indice, rotulos):
    """Atualiza o seletor de abas para o indice pedido."""
    if indice < len(abas_atual):
        rotulos[indice]["selected"] = True


def render_student_table(students, show_actions: bool = False, key_prefix: str = "") -> None:
    """Tabela de alunos. Aceita dicionarios ou objetos SQLAlchemy."""
    if not students:
        st.info("Nenhum aluno encontrado")
        return

    from encaminhamento.utils.status import rotulo_aluno

    data = []
    for s in students:
        # Handle both dict and model object
        if isinstance(s, dict):
            row = {
                "Nome": s.get("name", ""),
                "Nome Civil": s.get("civil_name", ""),
                "Endereço": s.get("full_address", s.get("address", "")),
                "Escola Origem": s.get("origin_school", ""),
                "Turma Origem": s.get("origin_class", ""),
                "Destino 1": s.get("destination_school_1", ""),
                "Destino 2": s.get("destination_school_2", ""),
                "Status": s.get("status", ""),
                "Assinatura": "✓" if s.get("responsible_signature") else "",
            }
            if show_actions:
                row["ID"] = s.get("id")
        else:
            row = {
                "Nome": s.name,
                "Nome Civil": s.civil_name or "",
                "Endereço": s.full_address,
                "Escola Origem": s.origin_school.name if s.origin_school else "",
                "Turma Origem": s.origin_class.name if s.origin_class else "",
                "Destino 1": s.destination_school_1.name if s.destination_school_1 else "",
                "Destino 2": s.destination_school_2.name if s.destination_school_2 else "",
                "Status": rotulo_aluno(s.status),
                "Assinatura": "✓" if s.responsible_signature else "",
            }
            if show_actions:
                row["ID"] = s.id
        data.append(row)
    
    st.dataframe(data, use_container_width=True, hide_index=True)


def render_batch_table(batches, show_actions: bool = False) -> None:
    """
    Tabela de lotes. Aceita dicionarios (dados ja extraidos) ou objetos
    SQLAlchemy ainda vinculados a uma sessao.
    """
    if not batches:
        st.info("Nenhum lote encontrado")
        return

    from encaminhamento.utils.status import rotulo_aluno, rotulo_lote

    data = []
    for b in batches:
        if isinstance(b, dict):
            row = {
                "ID": b.get("id"),
                "Ano": b.get("year"),
                "Escola Origem": b.get("origin_school", ""),
                "Escola Destino": b.get("destination_school", ""),
                "Turma": b.get("origin_class", ""),
                "Alunos": b.get("student_count", 0),
                "Status": b.get("status", ""),
                "PDF": "✓" if b.get("pdf_path") else "",
                "Enviado em": b.get("sent_at", ""),
            }
        else:
            row = {
                "ID": b.id,
                "Ano": b.year,
                "Escola Origem": b.origin_school.name if b.origin_school else "",
                "Escola Destino": b.destination_school.name if b.destination_school else "",
                "Turma": b.origin_class.name if b.origin_class else "",
                "Alunos": b.student_count,
                "Status": rotulo_lote(b.status),
                "PDF": "✓" if b.pdf_path else "",
                "Enviado em": b.sent_at.strftime("%d/%m/%Y %H:%M") if b.sent_at else "",
            }
        data.append(row)

    st.dataframe(data, use_container_width=True, hide_index=True)


def metric_card(title: str, value: str, delta: str = None, help_text: str = None):
    """Render a metric card."""
    st.metric(title, value, delta=delta, help=help_text)


def sidebar_navigation():
    """Menu lateral compacto: cabe inteiro sem rolagem."""
    # Garante que a pagina atual exista, mesmo se o app nao inicializou
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Dashboard"

    with st.sidebar:
        # Cabecalho enxuto, sem o titulo grande
        st.markdown(
            """
            <div style="padding: 2px 0 6px 0;">
              <div style="font-size: 15px; font-weight: 600; color: #262730;">
                📋 Encaminhamento
              </div>
              <div style="font-size: 11px; color: #8a94a6;">Alunos</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Aviso de pendencias, para quem nao abre o painel saber que ha algo a resolver
        try:
            from encaminhamento.services.relatorio import montar_resumo
            n_pendencias = montar_resumo().total_pendencias
        except Exception:
            n_pendencias = 0

        if n_pendencias:
            if st.button(
                f"⚠️ {n_pendencias} pendência(s)",
                use_container_width=True,
                type="primary",
                key="nav_pendencias",
            ):
                st.session_state.current_page = "Dashboard"
                st.rerun()

        # Menu: um radio ocupa bem menos espaco que sete botoes
        paginas = {
            "📊 Painel": "Dashboard",
            "📥 Alunos": "Alunos",
            "🏫 Escolas": "Escolas",
            "🎯 Alocação": "Auto_Allocation",
            "📦 Lotes": "Batch_Management",
            "⚙️ Automação": "Automation",
            "⬇️ Atualizar": "Atualizar",
        }
        rotulos = list(paginas)
        atual = st.session_state.get("current_page", "Dashboard")
        indice = rotulos.index(
            next(r for r, k in paginas.items() if k == atual)
        ) if atual in paginas.values() else 0

        escolhida = st.radio(
            "Menu",
            options=rotulos,
            index=indice,
            label_visibility="collapsed",
            key="nav_menu",
        )

        if paginas[escolhida] != atual:
            st.session_state.current_page = paginas[escolhida]
            st.rerun()

        st.divider()

        # Totais em uma linha so
        try:
            with get_session() as session:
                from sqlalchemy import func, select
                from encaminhamento.database.models import School, Student, ForwardingBatch

                escolas = session.execute(select(func.count(School.id))).scalar() or 0
                alunos = session.execute(select(func.count(Student.id))).scalar() or 0
                lotes = session.execute(select(func.count(ForwardingBatch.id))).scalar() or 0

            st.caption(f"🏫 {escolas}  ·  👥 {alunos}  ·  📦 {lotes}")
        except Exception:
            st.caption("Carregando...")

        # Assinatura, sempre visivel no rodape do menu
        st.markdown(
            """
            <div style="
                margin-top: 14px;
                padding-top: 8px;
                border-top: 1px solid #e6e9ef;
                text-align: center;">
              <div style="font-size: 10px; color: #a4adbd; letter-spacing: 0.2px;">
                Desenvolvido por
              </div>
              <div style="font-size: 11px; color: #7b8696; font-weight: 600; margin-top: 1px;">
                C3 Sistemas e Serviços
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def confirm_dialog(message: str, key: str) -> bool:
    """Simple confirmation dialog."""
    if f"confirm_{key}" not in st.session_state:
        st.session_state[f"confirm_{key}"] = False
    
    if st.session_state[f"confirm_{key}"]:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Confirmar", key=f"yes_{key}", use_container_width=True):
                st.session_state[f"confirm_{key}"] = False
                return True
        with col2:
            if st.button("❌ Cancelar", key=f"no_{key}", use_container_width=True):
                st.session_state[f"confirm_{key}"] = False
                st.rerun()
        return False
    
    if st.button("🗑️ " + message, key=f"btn_{key}"):
        st.session_state[f"confirm_{key}"] = True
        st.rerun()
    return False


def file_uploader_with_preview(label: str, key: str, accept_multiple: bool = False):
    """File uploader with preview for Excel files."""
    uploaded = st.file_uploader(
        label,
        type=["xlsx", "xls"],
        accept_multiple_files=accept_multiple,
        key=key
    )
    
    if uploaded:
        files = uploaded if isinstance(uploaded, list) else [uploaded]
        for f in files:
            st.caption(f"📄 {f.name} ({f.size:,} bytes)")
    
    return uploaded