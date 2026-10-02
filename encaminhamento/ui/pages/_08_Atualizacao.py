import streamlit as st

from encaminhamento.ui.components import sidebar_navigation
from encaminhamento.config import BRANCH, INTERVALO_VERIFICACAO_HORAS, REPOSITORIO
from encaminhamento.services import atualizacao


def _mostrar_datas(dados):
    """Traduz a data do commit para o formato brasileiro."""
    data = dados.get("data_commit")
    if not data:
        return ""
    from datetime import datetime
    try:
        return datetime.fromisoformat(data.replace("Z", "+00:00")).strftime("%d/%m/%Y às %H:%M")
    except ValueError:
        return ""


def render():
    sidebar_navigation()

    st.title("⬇️ Atualizar o Sistema")
    st.caption("Traz a versão mais recente direto do GitHub, sem mexer nos seus dados")

    # Se veio do cartão de pendência, mostra o botão logo no topo
    quer_atualizar = st.session_state.pop("ir_atualizar", None)

    st.caption(f"Repositório: `{REPOSITORIO}` (branch `{BRANCH}`)")

    st.divider()

    # ------------------------------------------------------------------
    # Consultar
    # ------------------------------------------------------------------
    c1, c2 = st.columns(2)

    with c1:
        if st.button("🔄 Verificar agora", use_container_width=True):
            with st.spinner("Consultando o GitHub..."):
                dados = atualizacao.verificar(forcar=True)
            st.session_state["_verif"] = dados

    with c2:
        st.caption(
            f"O sistema consulta sozinho a cada "
            f"{INTERVALO_VERIFICACAO_HORAS} horas."
        )

    dados = st.session_state.get("_verif") or atualizacao.estado()

    if dados.get("erro"):
        st.warning(dados["erro"])

    ultima = dados.get("ultima_verificacao")
    if ultima:
        try:
            from datetime import datetime
            quando = datetime.fromisoformat(ultima).strftime("%d/%m/%Y às %H:%M")
            st.caption(f"Última verificação: {quando}")
        except ValueError:
            pass

    st.divider()

    # ------------------------------------------------------------------
    # Situação
    # ------------------------------------------------------------------
    instalado = (dados.get("commit_instalado") or "")[:7]
    remoto = (dados.get("commit_remoto") or "")[:7]

    c1, c2, c3 = st.columns(3)
    c1.metric("Versão instalada", instalado or "desconhecida")
    c2.metric("Versão no GitHub", remoto or "—")
    c3.metric("Situação", "Atualizar" if dados.get("disponivel") else "Em dia")

    if not dados.get("commit_instalado"):
        st.info(
            "Ainda não foi registrada qual versão está instalada. "
            "Clique em **Verificar agora** para registrar."
        )

    if not dados.get("disponivel"):
        if instalado and remoto and instalado == remoto:
            st.success("O sistema já está na versão mais recente.")
        return

    # ------------------------------------------------------------------
    # Tem versão nova
    # ------------------------------------------------------------------
    st.success(f"**Há uma versão nova disponível.**")

    if dados.get("mensagem"):
        st.markdown(f"**O que mudou:** {dados['mensagem']}")

    quando = _mostrar_datas(dados)
    if quando:
        st.caption(f"Publicada em {quando}  ·  versão {remoto}")

    st.divider()

    st.markdown("""
**O que será trocado**

O código do sistema (telas, serviços e scripts).

**O que não será tocado**

- Os alunos, as escolas e as alocações (o banco de dados)
- As coordenadas já encontradas
- Suas chaves do Google e do email
- O ambiente virtual
""")

    # ------------------------------------------------------------------
    # Aplicar
    # ------------------------------------------------------------------
    if st.button("⬇️ Atualizar agora", type="primary", use_container_width=True):
        with st.spinner("Baixando e aplicando a atualização..."):
            resultado = atualizacao.aplicar()

        if not resultado.get("ok"):
            st.error(resultado.get("mensagem", "Falha desconhecida."))
        else:
            arquivos = resultado.get("arquivos", 0)

            if resultado.get("requisitos_mudaram"):
                st.warning(
                    "A versão nova traz dependências diferentes. "
                    "Rode **instalar.bat** (ou `instalar.sh`) antes de continuar."
                )
                if st.button("📦 Abrir instrução de instalação", use_container_width=True):
                    st.info(
                        "No Windows: clique duas vezes em `instalar.bat`.\n\n"
                        "No Mac ou Linux: rode `bash instalar.sh`.\n\n"
                        "Depois volte para cá."
                    )
                    return
            else:
                st.success(f"{arquivos} arquivo(s) atualizado(s).")

            st.caption(f"Nova versão: {resultado.get('commit', '')}")

            if st.button("🔄 Recarregar o sistema", use_container_width=True):
                st.session_state.pop("_verif", None)
                st.rerun()
