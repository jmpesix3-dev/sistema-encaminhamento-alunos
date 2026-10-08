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
from encaminhamento.database.crud import list_schools, update_student
from encaminhamento.services.relatorio import (
    montar_resumo, exportar_resumo, detalhar_pendencia,
    detalhar_alunos_por_escola, contar_situacao_aluno,
    detalhar_situacao_aluno,
    ROTULO_STATUS_ALUNO, ROTULO_STATUS_LOTE,
    ORDEM_ALUNO, ORDEM_LOTE, COR_STATUS,
    SITUACAO_ALUNO, COR_SITUACAO,
)
from encaminhamento.services.allocation import get_allocation_service
from encaminhamento.database.models import StudentStatus
from encaminhamento.utils.helpers import get_or_create_school_from_name, format_student_name
from encaminhamento.utils.status import opcoes_aluno, para_valor_aluno
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

    # Detecta clique via query params
    nav_toggle = st.query_params.get("nav_toggle", "")
    nav_filter_key = st.query_params.get("nav_filter_key", "")
    nav_filter_val = st.query_params.get("nav_filter_val", "")
    if nav_toggle:
        ir_para(nav_toggle, **{nav_filter_key: nav_filter_val})
        st.rerun()

    for col, chave in zip(cols, rotulos):
        quantidade = valores.get(chave, 0)
        pct = (quantidade / total * 100) if total else 0
        rotulo = ROTULO_STATUS_ALUNO.get(chave) or ROTULO_STATUS_LOTE.get(chave, chave)
        cor = COR_STATUS.get(chave, "#2f7ed8")

        with col:
            if quantidade > 0:
                card_html = f"""
                <div style="
                    border:1px solid {cor}55;
                    border-top:3px solid {cor};
                    border-radius:8px;
                    padding:10px 12px;
                    cursor:pointer;
                    transition:opacity 0.2s;"
                     onclick="var u=new URLSearchParams(window.location.search);u.set('nav_toggle','{pagina}');u.set('nav_filter_key','{chave_estado}');u.set('nav_filter_val','{chave}');window.location.search=u.toString()">
                  <div style="font-size:12px;opacity:0.75;margin-bottom:2px;">{rotulo}</div>
                  <div style="font-size:26px;font-weight:600;color:{cor};line-height:1.1;">{quantidade}</div>
                  <div style="font-size:12px;opacity:0.6;margin-bottom:8px;">{pct:.0f}% do total</div>
                  <div style="background:rgba(127,127,127,0.25);border-radius:3px;height:6px;overflow:hidden;">
                    <div style="background:{cor};width:{max(pct, 1.5)}%;height:6px;"></div>
                  </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.markdown(
                    f"""
                    <div style="
                        border:1px solid {cor}55;
                        border-top:3px solid {cor};
                        border-radius:8px;
                        padding:10px 12px;">
                      <div style="font-size:12px;opacity:0.75;margin-bottom:2px;">{rotulo}</div>
                      <div style="font-size:26px;font-weight:600;color:{cor};line-height:1.1;">{quantidade}</div>
                      <div style="font-size:12px;opacity:0.6;margin-bottom:8px;">{pct:.0f}% do total</div>
                      <div style="background:rgba(127,127,127,0.25);border-radius:3px;height:6px;overflow:hidden;">
                        <div style="background:{cor};width:{max(pct, 1.5)}%;height:6px;"></div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


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
    """Quatro cards clicaveis; ao clicar num card, os alunos aparecem abaixo em editor."""

    from encaminhamento.utils.helpers import get_or_create_school_from_name
    from encaminhamento.utils.status import opcoes_aluno, para_valor_aluno

    # Detecta clique via query params (botao HTML dentro do card)
    toggle = st.query_params.get("toggle", "")
    if toggle:
        chave = toggle
        expandido = bool(st.session_state.get(f"sit_aluno_lista_{chave}"))
        if expandido:
            st.session_state.pop(f"sit_aluno_lista_{chave}", None)
        else:
            for _c in ("alunos", "encaminhados", "pendente", "info_pendente"):
                st.session_state.pop(f"sit_aluno_lista_{_c}", None)
            st.session_state[f"sit_aluno_lista_{chave}"] = True
        st.query_params.clear()
        st.rerun()

    contagens = contar_situacao_aluno()
    total = contagens["alunos"]

    cards = [
        ("alunos", "Alunos", contagens["alunos"], COR_SITUACAO["alunos"], "Alunos"),
        ("encaminhados", "Encaminhados", contagens["encaminhados"], COR_SITUACAO["encaminhados"], "Alunos"),
        ("pendente", "Pendente", contagens["pendente"], COR_SITUACAO["pendente"], "Alunos"),
        ("info_pendente", "Informação Pendente", contagens["info_pendente"], COR_SITUACAO["info_pendente"], "Alunos"),
    ]

    def _pct(q):
        return (q / total * 100) if total else 0

    st.subheader("Situação dos alunos")

    st.markdown("""
    <style>
    .status-card-click {
        position: relative;
        cursor: pointer;
        transition: opacity 0.2s;
    }
    .status-card-click:hover {
        opacity: 0.85;
    }
    .status-card-click button {
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        cursor: pointer;
        z-index: 2;
        opacity: 0;
    }
    </style>
    """, unsafe_allow_html=True)

    cols = st.columns(4, vertical_alignment="bottom")
    for col, (chave, titulo, quantidade, cor, _pagina) in zip(cols, cards):
        with col:
            pct = _pct(quantidade)
            expandido = bool(st.session_state.get(f"sit_aluno_lista_{chave}"))
            if expandido and quantidade > 0:
                cor = "#9c27b0"

            card_html = f"""
            <div class="status-card-click"
                 onclick="var u=new URLSearchParams(window.location.search);u.set('toggle','{chave}');window.location.search=u.toString()">
              <div style="
                  border:1px solid {cor}55;
                  border-top:3px solid {cor};
                  border-radius:8px;
                  padding:10px 12px;">
                <div style="font-size:11px;opacity:0.75;margin-bottom:2px;">{titulo}</div>
                <div style="font-size:26px;font-weight:600;color:{cor};line-height:1.1;">{quantidade}</div>
                <div style="font-size:11px;opacity:0.6;">{pct:.0f}% do total</div>
              </div>
            </div>
            """ if quantidade > 0 else f"""
            <div style="
                border:1px solid {cor}55;
                border-top:3px solid {cor};
                border-radius:8px;
                padding:10px 12px;">
              <div style="font-size:11px;opacity:0.75;margin-bottom:2px;">{titulo}</div>
              <div style="font-size:26px;font-weight:600;color:{cor};line-height:1.1;">{quantidade}</div>
              <div style="font-size:11px;opacity:0.6;">{pct:.0f}% do total</div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

    for chave, titulo, quantidade, cor, pagina in cards:
        if quantidade == 0:
            continue
        if not st.session_state.get(f"sit_aluno_lista_{chave}"):
            continue

        with st.container(border=True):
            linhas = detalhar_situacao_aluno(chave)
            if not linhas:
                st.caption(f"Sem alunos em '{titulo}'.")
            else:
                df = pd.DataFrame(linhas)
                edited = st.data_editor(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ID": st.column_config.NumberColumn("ID", disabled=True),
                        "Origem": st.column_config.TextColumn("Origem", disabled=True),
                        "Alocado em": st.column_config.TextColumn("Alocado em", disabled=True),
                        "1ª opção": st.column_config.TextColumn("1ª opção"),
                        "2ª opção": st.column_config.TextColumn("2ª opção"),
                        "Endereço": st.column_config.TextColumn("Endereço"),
                        "Status": st.column_config.SelectboxColumn(
                            "Status", options=opcoes_aluno(), required=True
                        ),
                    },
                    key=f"sit_aluno_edit_{chave}",
                    num_rows="dynamic",
                )
                st.caption(f"{len(edited)} aluno(s).")
                if st.button(
                    "💾 Salvar e tentar encaminhar novamente",
                    key=f"sit_aluno_salvar_{chave}",
                    type="primary",
                    use_container_width=True,
                ):
                    mudancas = 0
                    for _, row in edited.iterrows():
                        sid = int(row["ID"])
                        original = df[df["ID"] == sid].iloc[0]
                        if row.equals(original):
                            continue

                        d1 = (row.get("1ª opção") or "").strip()
                        d2 = (row.get("2ª opção") or "").strip()

                        with get_session() as session:
                            update_student(
                                session,
                                sid,
                                name=row["Aluno"],
                                address=row["Endereço"],
                                destination_school_1_id=(
                                    get_or_create_school_from_name(d1, is_destination=True) if d1 else None
                                ),
                                destination_school_2_id=(
                                    get_or_create_school_from_name(d2, is_destination=True) if d2 else None
                                ),
                                status=para_valor_aluno(row["Status"]),
                            )
                        mudancas += 1

                    if mudancas:
                        get_allocation_service().run_allocation()
                        st.success(f"{mudancas} aluno(s) atualizado(s). Encaminhamento tentado novamente.")
                        st.session_state.pop(f"sit_aluno_lista_{chave}", None)
                        st.rerun()
                    else:
                        st.info("Nenhuma alteração detectada.")

            # Mapeia a chave do card para o filtro da pagina Alunos
            filtro_alunos = {
                "alunos": None,
                "encaminhados": "encaminhados",
                "pendente": "sem_vaga",
                "info_pendente": "info_pendente",
            }
            filtro = filtro_alunos.get(chave)

            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "📋 Ir para Alunos (filtro aplicado)",
                    key=f"sit_aluno_ir_{chave}",
                    use_container_width=True,
                ):
                    if filtro:
                        ir_para("Alunos", aluno_status=filtro)
                    else:
                        ir_para("Alunos")
            with c2:
                if st.button(
                    "Ocultar", key=f"sit_aluno_occ_{chave}", use_container_width=True
                ):
                    st.session_state.pop(f"sit_aluno_lista_{chave}", None)
                    st.rerun()


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
