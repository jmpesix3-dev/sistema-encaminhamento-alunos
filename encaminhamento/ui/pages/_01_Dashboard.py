"""
Painel de Controle.

Responde, de cima para baixo: o que falta resolver, como esta a
situacao e onde clicar para ir resolver.
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from encaminhamento.ui.components import sidebar_navigation, ir_para
from encaminhamento.database import get_session
from encaminhamento.database.crud import list_schools
from encaminhamento.services.relatorio import (
    montar_resumo, exportar_resumo, detalhar_pendencia,
    detalhar_alunos_por_escola, contar_situacao_aluno,
    detalhar_situacao_aluno,
    ROTULO_STATUS_ALUNO, ROTULO_STATUS_LOTE,
    ORDEM_ALUNO, ORDEM_LOTE, COR_STATUS,
    SITUACAO_ALUNO, COR_SITUACAO,
)
from encaminhamento.config import DATA_DIR

PASSOS = [
    ("1", "Carregar planilha", "Receber a demanda das escolas", "Alunos", {"aba": "upload"}),
    ("2", "Definir vagas", "Quantos alunos cada escola comporta", "Escolas", {"capacidade": True}),
    ("3", "Alocar alunos", "Distribuir por proximidade", "Auto_Allocation", {"alocacao": "previa"}),
    ("4", "Gerar e enviar", "PDF e envio para a escola", "Batch_Management", {"lote_status": "todos"}),
]



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
    """
    Cartao de pendencia: titulo, descricao, casos e botao de navegar.

    Os casos so sao carregados depois do clique. O Streamlit executa o
    conteudo do expansor mesmo fechado, e consultar os casos a cada
    desenho da pagina deixava o painel lento.
    """
    titulo = f"⚠️ {p.titulo} — {p.quantidade}" if destaque else f"{p.titulo} — {p.quantidade}"
    rotulo_botao = "Resolver →" if destaque else "Ver →"

    with st.expander(titulo, expanded=False):
        st.caption(p.descricao)

        chave_casos = f"casos_{p.chave}"

        if not st.session_state.get(chave_casos):
            # So um botao agora: nada de consulta antes do usuario pedir
            if st.button(
                f"👁️ Ver {p.quantidade} caso(s)",
                key=f"ver_{p.chave}",
                use_container_width=True,
            ):
                st.session_state[chave_casos] = True
                st.rerun()
        else:
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

            if st.button(
                "Ocultar casos",
                key=f"ocultar_{p.chave}",
                use_container_width=True,
            ):
                st.session_state.pop(chave_casos, None)
                st.rerun()

        if p.pagina:
            st.divider()
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

    # Destaque para as pendencias mais criticas. O aviso de atualizacao
    # usa criticidade 0 e por isso nao pode ser testado com "== 1".
    for p in resumo.pendencias:
        if p.criticidade <= 1:
            _cartao_pendencia(p, destaque=True)

    # Demais, em duas colunas alinhadas pela base
    demais = [p for p in resumo.pendencias if p.criticidade > 1]
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


def _cards_etapa(rotulos, valores, total, pagina, chave_estado, prefixo):
    """
    Um card por etapa, com numero, porcentagem e barra na cor da etapa.

    Etapa vazia continua aparecendo com 0%, para dar forma ao fluxo.
    """
    n = len(rotulos)
    cols = st.columns(n)

    for col, chave in zip(cols, rotulos):
        quantidade = valores.get(chave, 0)
        pct = (quantidade / total * 100) if total else 0
        rotulo = ROTULO_STATUS_ALUNO.get(chave) or ROTULO_STATUS_LOTE.get(chave, chave)
        cor = COR_STATUS.get(chave, "#2f7ed8")

        with col:
            st.markdown(
                f"""
                <div style="
                    border:1px solid {cor}55;
                    border-top:3px solid {cor};
                    border-radius:8px;
                    padding:10px 12px;
                    margin-bottom:4px;">
                  <div style="
                      font-size:12px;
                      opacity:0.75;
                      margin-bottom:2px;">{rotulo}</div>
                  <div style="
                      font-size:26px;
                      font-weight:600;
                      color:{cor};
                      line-height:1.1;">{quantidade}</div>
                  <div style="
                      font-size:12px;
                      opacity:0.6;
                      margin-bottom:8px;">{pct:.0f}% do total</div>
                  <div style="
                      background:rgba(127,127,127,0.25);
                      border-radius:3px;
                      height:6px;
                      overflow:hidden;">
                    <div style="background:{cor};width:{max(pct, 1.5)}%;height:6px;"></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # O botao fica fora do card para o clique funcionar bem
            if st.button(
                "Ver lista",
                key=f"{prefixo}_{chave}",
                use_container_width=True,
                disabled=quantidade == 0,
            ):
                ir_para(pagina, **{chave_estado: chave})


def _situacao_por_escola():
    """Visao por escola de origem."""
    st.markdown("**Por escola**")

    linhas = detalhar_alunos_por_escola()

    if not linhas:
        st.info("Nenhum aluno cadastrado.")
        return

    # Filtro por escola
    nomes = {l["id"]: l["Escola"] for l in linhas}
    c1, c2 = st.columns([2, 1])

    with c1:
        escolhida = st.selectbox(
            "Escola de origem",
            options=[None] + list(nomes.keys()),
            format_func=lambda i: "Todas as escolas" if i is None else nomes[i],
            key="situacao_escola",
        )

    with c2:
        st.write("")
        st.write("")
        if escolhida is not None and st.button(
            "Ver alunos", key="situacao_ver_alunos", use_container_width=True
        ):
            ir_para("Alunos", aluno_origem=escolhida)

    visiveis = [l for l in linhas if escolhida is None or l["id"] == escolhida]

    if len(linhas) > 1:
        st.caption(f"{len(linhas)} escolas com alunos, de {resumo_total_escolas()} cadastradas.")

    tabela = pd.DataFrame([{
        "Escola": l["Escola"],
        "Distrito": l["Distrito"],
        "Alunos": l["Alunos"],
        "Rascunho": l["Rascunho"],
        "Pendente": l["Pendente"],
        "Enviado": l["Enviado"],
        "Confirmado": l["Confirmado"],
        "Alocados": l["Alocados"],
        "Capacidade": l["Capacidade"],
        "Vagas livres": l["Vagas livres"],
        "Ocupação": l["Ocupacao"],
    } for l in visiveis])

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
        column_config={
            c: st.column_config.NumberColumn(c, format="%d")
            for c in ("Alunos", "Rascunho", "Pendente", "Enviado",
                      "Confirmado", "Alocados", "Capacidade", "Vagas livres")
        },
    )


def resumo_total_escolas():
    """Total de escolas cadastradas."""
    with get_session() as session:
        return len(list_schools(session))


def _situacao_aluno():
    """Quatro cards de situacao do aluno, cada um clicavel."""
    st.subheader("Situação dos alunos")

    contagens = contar_situacao_aluno()
    total = contagens["alunos"]

    cards = [
        ("alunos", "Alunos", contagens["alunos"], COR_SITUACAO["alunos"], "Alunos"),
        ("encaminhados", "Encaminhados", contagens["encaminhados"], COR_SITUACAO["encaminhados"], "Alunos"),
        ("pendente", "Pendente", contagens["pendente"], COR_SITUACAO["pendente"], "Alunos"),
        ("info_pendente", "Informação Pendente", contagens["info_pendente"], COR_SITUACAO["info_pendente"], "Alunos"),
    ]

    cols = st.columns(4, vertical_alignment="bottom")
    for col, (chave, titulo, quantidade, cor, pagina) in zip(cols, cards):
        with col:
            pct = (quantidade / total * 100) if total else 0
            st.markdown(
                f"""
                <div style="
                    border:1px solid {cor}55;
                    border-top:3px solid {cor};
                    border-radius:8px;
                    padding:10px 12px;
                    margin-bottom:4px;">
                  <div style="
                      font-size:11px;
                      opacity:0.75;
                      margin-bottom:2px;">{titulo}</div>
                  <div style="
                      font-size:26px;
                      font-weight:600;
                      color:{cor};
                      line-height:1.1;">{quantidade}</div>
                  <div style="
                      font-size:11px;
                      opacity:0.6;
                      margin-bottom:8px;">{pct:.0f}% do total</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Ver lista", key=f"sit_aluno_{chave}", use_container_width=True,
                disabled=quantidade == 0,
            ):
                ir_para(pagina, aluno_status=chave)


def _situacao(resumo):
    """Situacao de alunos e lotes por etapa, mais a visao por escola."""
    st.subheader("Situação")

    # ---- Alunos ----
    total_alunos = resumo.alunos
    st.markdown(f"**Alunos** — {total_alunos} no total")
    if total_alunos:
        _cards_etapa(
            ORDEM_ALUNO, resumo.por_status_aluno, total_alunos,
            "Alunos", "aluno_status", "etapa_aluno",
        )
    else:
        st.info("Nenhum aluno cadastrado.")

    st.divider()

    # ---- Lotes ----
    total_lotes = resumo.lotes
    st.markdown(f"**Lotes** — {total_lotes} no total")
    if total_lotes:
        _cards_etapa(
            ORDEM_LOTE, resumo.por_status_lote, total_lotes,
            "Batch_Management", "lote_status", "etapa_lote",
        )
    else:
        st.info("Nenhum lote criado.")

    st.divider()

    # ---- Por escola ----
    _situacao_por_escola()


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
    _situacao_aluno()

    st.divider()
    _situacao_por_escola()

    st.divider()
    _escolas_atencao(resumo)

    st.divider()
    _exportar(resumo)
