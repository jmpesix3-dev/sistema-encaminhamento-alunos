import streamlit as st
from encaminhamento.config import APP_TITLE, APP_ICON, PAGE_LAYOUT
from encaminhamento.database import init_db
from encaminhamento.ui.components import sidebar_navigation

# Page config
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout=PAGE_LAYOUT,
    initial_sidebar_state="expanded"
)

# Initialize database
init_db()

# Initialize session state
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"

# Custom CSS
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .stDataFrame {
        font-size: 0.9rem;
    }
    div[data-testid="stSidebarNav"] {
        display: none;
    }

    /* Tira o espaco vazio do topo: o cabecalho do Streamlit (botao de
       recolher) ocupa altura demais antes do conteudo do menu */
    section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
        padding-top: 0.35rem;
        padding-bottom: 0;
        height: auto;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0.25rem;
    }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:first-child {
        padding-top: 0;
    }

    /* Menu lateral: lista compacta, sem bolinha de radio */
    section[data-testid="stSidebar"] [data-testid="stRadio"] {
        margin-bottom: 0;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label {
        padding: 4px 8px;
        border-radius: 6px;
        margin-bottom: 1px;
        cursor: pointer;
        transition: background 0.12s ease;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background-color: #f5f6f8;
    }
    /* esconde a bolinha do radio */
    section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"],
    section[data-testid="stSidebar"] [data-testid="stRadio"] svg {
        display: none !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] {
        display: inline;
    }
    /* item ativo: so cor no texto */
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background-color: transparent;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        color: #2563eb;
        font-weight: 600;
    }
    /* espacamentos mais justos */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        margin-bottom: 0.3rem;
    }
    section[data-testid="stSidebar"] hr {
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # Consulta de atualizacao: uma vez por sessao, e apenas se ja
    # passou o intervalo. Falha de internet nao trava o sistema.
    _verificar_atualizacao()

    # Route to appropriate page
    page = st.session_state.current_page

    if page == "Dashboard":
        from encaminhamento.ui.pages._01_Dashboard import render
    elif page == "Alunos":
        from encaminhamento.ui.pages._02_Alunos import render
    elif page == "Escolas":
        from encaminhamento.ui.pages._03_Escolas import render
    elif page == "Batch_Management":
        from encaminhamento.ui.pages._05_Batch_Management import render
    elif page == "Automation":
        from encaminhamento.ui.pages._06_Automation import render
    elif page == "Auto_Allocation":
        from encaminhamento.ui.pages._07_Auto_Allocation import render
    elif page == "Atualizar":
        from encaminhamento.ui.pages._08_Atualizacao import render
    else:
        from encaminhamento.ui.pages._01_Dashboard import render

    render()


def _verificar_atualizacao():
    """Procura versao nova, respeitando o intervalo de horas."""
    if st.session_state.get("_atualizacao_verificada"):
        return
    st.session_state["_atualizacao_verificada"] = True

    try:
        from encaminhamento.services import atualizacao
        atualizacao.verificar()
    except Exception:
        # Sem internet, sem registro, qualquer eventualidade:
        # o sistema abre normalmente.
        pass


if __name__ == "__main__":
    main()