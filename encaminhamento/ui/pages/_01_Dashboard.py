"""
Painel de Controle.

Responde, de cima para baixo: o que falta resolver, como esta a
situacao e onde clicar para ir resolver.
"""
import streamlit as st
import pandas as pd

from encaminhamento.ui.components import sidebar_navigation, ir_para
from encaminhamento.services.relatorio import (
    montar_resumo, exportar_resumo, detalhar_pendencia,
    ROTULO_STATUS_ALUNO, ROTULO_STATUS_LOTE,
    ORDEM_ALUNO, ORDEM_LOTE,
)
from encaminhamento.config import DATA_DIR
from datetime import datetime

COR_STATUS = {
    "draft": "#9aa5b1",
    "pending": "#f0a30a",
    "sent": "#2f7ed8",
    "confirmed": "#1f9d55",
    "cancelled": "#d64545",
    "generated": "#2f7ed8",
    "completed": "#1f9d55",
}

PASSOS = [
    ("1", "Carregar planilha", "Receber a demanda das escolas", "Alunos", {"aba": "upload"}),
    ("2", "Definir vagas", "Quantos alunos cada escola comporta", "Escolas", {"capacidade": True}),
    ("3", "Alocar alunos", "Distribuir por proximidade", "Auto_Allocation", {"alocacao": "previa"}),
    ("4", "Gerar e enviar", "PDF e envio para a escola", "Batch_Management", {"lote_status": "todos"}),
]


def _barra_status(rotulos, valores):
    """Barras horizontais com rotulo, barra e contagem."""
    total = sum(valores.values()) or 1
    for chave in rotulos:
        v = valores.get(chave, 0)
        if v <= 0:
            continue
        pct = v / total
        cols = st.columns([2, 5, 1])
        with cols[0]:
            st.caption(ROTULO_STATUS_ALUNO.get(chave) or ROTULO_STATUS_LOTE.get(chave, chave))
        with cols[1]:
            # st.progress nao aceita cor, entao a barra usa a cor padrao
            st.progress(min(pct, 1.0), text=None)
        with cols[2]:
            st.caption(f"**{v}**")


def _indicadores(resumo):
    """Linha de indicadores clicaveis."""
    c = st.columns(5)

    itens = [
        ("🏫 Escolas", resumo.escolas, "Escolas", {}, "normal"),
        ("👥 Alunos", resumo.alunos, "Alunos", {}, "normal"),
        ("✅ Alocados", resumo.alocados, "Auto_Allocation", {"alocacao": "previa"}, "normal"),
        ("⛔ Sem vaga", resumo.sem_vaga, "Alunos", {"aluno_status": "sem_vaga"},
         "inverse" if resumo.sem_vaga else "normal"),
        ("📦 Lotes", resumo.lotes, "Batch_Management", {"lote_status": "todos"},
         "inverse" if resumo.lotes and not resumo.por_status_lote.get("completed") else "normal"),
    ]

    for col, (titulo, valor, pagina, estado, cor) in zip(c, itens):
        with col:
            if st.button(
                f"{titulo}\n\n**{valor}**",
                use_container_width=True,
                key=f"ind_{titulo}",
                type="secondary" if valor else "secondary",
            ):
                ir_para(pagina, **estado)


def _passos():
    """Fluxo numerado do processo."""
    st.subheader("Como começar")
    # Cartoes com borda e conteudo alinhado pela base, para os botoes ficarem
    # na mesma altura mesmo quando o texto quebra em mais linhas.
    cols = st.columns(4, vertical_alignment="bottom", border=True)
    for col, (numero, titulo, desc, pagina, estado) in zip(cols, PASSOS):
        with col:
            st.markdown(f"**{numero}. {titulo}**")
            st.caption(desc)
            if st.button("Abrir", key=f"passo_{numero}", use_container_width=True):
                ir_para(pagina, **estado)


def _cartao_pendencia(p, destaque: bool):
    """Cartao de pendencia: titulo, descricao, casos e botao de navegar."""
    titulo = f"⚠️ {p.titulo} — {p.quantidade}" if destaque else f"{p.titulo} — {p.quantidade}"
    rotulo_botao = "Resolver →" if destaque else "Ver →"

    with st.expander(titulo, expanded=False):
        st.caption(p.descricao)

        linhas = detalhar_pendencia(p.chave)
        if not linhas:
            st.caption("Sem casos para detalhar.")
        else:
            colunas = list(linhas[0].keys())
            st.dataframe(
                pd.DataFrame(linhas),
                use_container_width=True,
                hide_index=True,
                column_config={
                    c: st.column_config.NumberColumn(c, format="%d")
                    for c in colunas
                    if c in ("Alunos", "Alunos apontam", "Procura",
                             "Capacidade", "Excesso", "Vagas livres")
                },
            )
            st.caption(f"{len(linhas)} caso(s).")

        if p.pagina:
            if st.button(rotulo_botao, key=f"ir_{p.chave}", use_container_width=True):
                ir_para(p.pagina, **p.estado)


def _pendencias(resumo):
    """Cartoes de pendencia, ordenados por impacto."""
    st.subheader("Pendências")

    if not resumo.pendencias:
        st.success(
            "Nenhuma pendência — todas as escolas têm capacidade e "
            "localização, e todos os alunos foram alocados."
        )
        return

    # Destaque para as pendencias que travam o processo
    for p in resumo.pendencias:
        if p.criticidade == 1:
            _cartao_pendencia(p, destaque=True)

    # Demais, em duas colunas alinhadas pela base
    demais = [p for p in resumo.pendencias if p.criticidade != 1]
    if demais:
        st.caption("Outras pendências")
        # Garante que sempre sobrem posicoes vazias para manter pares
        posicoes = list(demais)
        if len(posicoes) % 2:
            posicoes.append(None)
        for i in range(0, len(posicoes), 2):
            linha = posicoes[i:i + 2]
            cols = st.columns(len(linha), vertical_alignment="top")
            for col, p in zip(cols, linha):
                if p is not None:
                    with col:
                        _cartao_pendencia(p, destaque=False)


def _situacao(resumo):
    """Situacao de alunos e lotes, lado a lado."""
    st.subheader("Situação")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Alunos**")
        if any(resumo.por_status_aluno.values()):
            _barra_status(ORDEM_ALUNO, resumo.por_status_aluno)
        else:
            st.info("Nenhum aluno cadastrado.")

    with c2:
        st.markdown("**Lotes**")
        if any(resumo.por_status_lote.values()):
            _barra_status(ORDEM_LOTE, resumo.por_status_lote)
        else:
            st.info("Nenhum lote criado.")


def _escolas_atencao(resumo):
    """Tabela so com as escolas que precisam de atencao."""
    st.subheader("Escolas que precisam de atenção")

    com_problema = []
    for e in resumo.relacao_escolas:
        motivos = []
        if e["capacidade"] == 0:
            motivos.append("sem capacidade")
        if not e["geolocalizada"]:
            motivos.append("sem geolocalização")
        if e["capacidade"] > 0 and e["alunos_procura"] > e["capacidade"]:
            motivos.append(f"demanda {e['alunos_procura']} > {e['capacidade']} vagas")
        if motivos:
            com_problema.append({**e, "motivo": ", ".join(motivos)})

    c1, c2 = st.columns([3, 1])
    with c1:
        st.caption(f"{len(com_problema)} de {len(resumo.relacao_escolas)} escolas precisam de atenção")

    if not com_problema:
        st.success("Todas as escolas estão com capacidade e localização em dia.")
        return

    tabela = pd.DataFrame([{
        "Escola": e["escola"],
        "Distrito": e["distrito"],
        "Problema": e["motivo"],
        "Procura": e["alunos_procura"],
        "Capacidade": e["capacidade"],
        "Alocados": e["alocados"],
    } for e in com_problema])

    with c2:
        if st.button("Ver todas as escolas →", use_container_width=True):
            ir_para("Escolas", dados=True)

    # Tabela com botao de ajuste por linha
    for e in com_problema:
        cols = st.columns([4, 2, 1])
        with cols[0]:
            st.markdown(f"**{e['escola']}**")
            if e["distrito"]:
                st.caption(f"Distrito: {e['distrito']}")
        with cols[1]:
            st.caption(e["motivo"])
        with cols[2]:
            acao = "Ajustar" if not e["geolocalizada"] else "Abrir"
            if st.button(acao, key=f"atencao_{e['id']}", use_container_width=True):
                if e["geolocalizada"]:
                    ir_para("Escolas", mapa_escola=e["id"])
                else:
                    ir_para("Escolas", localizacao=True)

    st.divider()
    with st.expander("Ver todos os números", expanded=False):
        st.dataframe(
            tabela.sort_values("Escola"),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Procura": st.column_config.NumberColumn("Procura", format="%d"),
                "Capacidade": st.column_config.NumberColumn("Capacidade", format="%d"),
                "Alocados": st.column_config.NumberColumn("Alocados", format="%d"),
            },
        )


def _exportar(resumo):
    """Baixa o resumo em Excel."""
    destino = DATA_DIR / f"resumo_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    caminho = exportar_resumo(resumo, str(destino))
    with open(caminho, "rb") as f:
        st.download_button(
            "⬇️ Exportar resumo",
            f.read(),
            file_name=f"resumo_encaminhamento_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


def render():
    sidebar_navigation()

    col_t, col_b = st.columns([4, 1])
    with col_t:
        st.title("Painel de Controle")
        st.caption("Visão geral do encaminhamento de alunos")
    with col_b:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()

    resumo = montar_resumo()

    st.divider()
    _passos()

    st.divider()
    _pendencias(resumo)

    st.divider()
    _indicadores(resumo)

    st.divider()
    _situacao(resumo)

    st.divider()
    _escolas_atencao(resumo)

    st.divider()
    _exportar(resumo)
