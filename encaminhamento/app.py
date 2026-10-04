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

/* ---------------- Menu lateral ---------------- */
    /* Botoes do Streamlit centralizam o conteudo em tres niveis
       (button, div e span). E preciso zerar os tres para o texto
       ficar a esquerda. */
    section[data-testid="stSidebar"] div[data-testid="stButton"] {
        margin-bottom: 0;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button,
    section[data-testid="stSidebar"] div[data-testid="stButton"] button > div,
    section[data-testid="stSidebar"] div[data-testid="stButton"] button > div > span {
        justify-content: flex-start !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        min-height: unset;
        padding: 5px 8px;
        border-left: 3px solid transparent;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button p {
        text-align: left !important;
        font-size: 13px;
        font-weight: 450;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
        background: rgba(127, 127, 127, 0.14) !important;
        border-color: transparent !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] button:focus,
    section[data-testid="stSidebar"] div[data-testid="stButton"] button:focus-visible,
    section[data-testid="stSidebar"] div[data-testid="stButton"] button:active {
        background: transparent !important;
        border-color: transparent !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* Cartao de pendencias: mais compacto, sem a borda pesada */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 2px 4px;
        margin-bottom: 8px;
        border-radius: 6px;
    }
    section[data-testid="stVerticalBlockBorderWrapper"]
        div[data-testid="stButton"] button {
        padding: 6px 8px;
    }
    section[data-testid="stVerticalBlockBorderWrapper"]
        div[data-testid="stButton"] button p {
        font-size: 12.5px;
        font-weight: 600;
    }

    /* Margem do cabecalho customizado (o div do markdown) */
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        margin-bottom: 0;
    }

    /* Espacos mais justos */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        margin-bottom: 0.35rem;
    }
    section[data-testid="stSidebar"] hr {
        margin: 0.7rem 0;
    }

    /* O cabecalho do Streamlit (botao de recolher) ocupa altura
       demais antes do conteudo do menu. Reduz sem esconder. */
    section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
        padding-top: 0.2rem;
        padding-bottom: 0;
        height: auto;
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