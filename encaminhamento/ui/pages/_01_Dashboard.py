"""
Painel de Controle.

Responde, de cima para baixo: o que falta resolver, como esta a
situacao e onde clicar para ir resolver.
"""
import streamlit as st
import streamlit.components.v2 as components
import pandas as pd
from datetime import datetime
from sqlalchemy import select

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
from encaminhamento.database.models import (
    Class, ForwardingBatch, StudentStatus,
)
from encaminhamento.utils.helpers import get_or_create_school_from_name, format_student_name
from encaminhamento.config import DATA_DIR, RESUMO_KEEP_N
from encaminhamento.utils.arquivos import manter_arquivos_recentes

PASSOS = [
    ("1", "Carregar planilha", "Receber a demanda das escolas", "Alunos", {"aba": "upload"}),
    ("2", "Definir vagas", "Quantos alunos cada escola comporta", "Escolas", {"capacidade": True}),
    ("3", "Alocar alunos", "Distribuir por proximidade", "Auto_Allocation", {"alocacao": "previa"}),
    ("4", "Gerar e enviar", "PDF e envio para a escola", "Batch_Management", {"lote_status": "todos"}),
]


# --- Cards clicaveis da "Situacao dos alunos" (componente html interativo) ---
# Um iframe com os 4 cards de HTML/CSS puro: cor por status, numero destacado e
# toda a superficie do card clicavel. O clique envia um *trigger* para o Python,
# que abre o editor em linha (sem mudar a URL).
_SIT_CARDS_CSS = """
.sitc{
  flex:1;min-width:0;
  border:1pxpx solid;border-top:3px solid;
  border-radius:8px;padding:8px 4px;text-align:center;
  background:transparent;color:inherit;font-family:inherit;
  cursor:pointer;font-size:13px;transition:opacity .08s;
}
.sitc:hover{opacity:0.82;}
.sitt{display:block;font-size:10px;opacity:0.7;margin:0;}
.sitn{display:block;font-size:22px;font-weight:600;margin:2px 0;}
.sitp{display:block;font-size:10px;opacity:0.5;margin:0;}
"""

_SIT_CARDS_JS = r"""
export default function(component) {
  var { data, setTriggerValue, parentElement } = component;
  var root = parentElement.querySelector('#sit-root');
  if (!root) { root = document.createElement('div'); root.id = 'sit-root'; root.style.cssText = 'display:flex;gap:10px;height:100%;align-items:stretch;padding:2px 4px;box-sizing:border-box;'; parentElement.appendChild(root); }
  root.innerHTML = '';
  (data || []).forEach(function(c) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'sitc';
    b.setAttribute('data-key', c.chave);
    if (c.cor) { b.style.borderColor = c.cor + '55'; b.style.borderTopColor = c.cor; }
    b.innerHTML = '<span class="sitt">' + c.titulo + '</span>'
              + '<span class="sitn" style="color:' + c.cor + '">' + c.quantidade + '</span>'
              + '<span class="sitp">' + c.pct + '%</span>';
    b.addEventListener('click', function() { setTriggerValue('clicked', c.chave); });
    root.appendChild(b);
  });
}
"""

_componente_cards_situacao = components.component(
    "situacao_aluno_cards",
    css=_SIT_CARDS_CSS,
    js=_SIT_CARDS_JS,
)


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
            if st.button("Abrir", key=f"passo_{numero}", width="stretch",):
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
                width="stretch",
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
                    width="stretch",
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
                width="stretch",
            ):
                st.session_state.pop(chave_casos, None)
                st.rerun()

        if p.pagina:
            st.divider()
            if st.button(rotulo_botao, key=f"ir_{p.chave}", width="stretch",):
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


def _situacao_por_escola(ano_encaminhamento: int = None):
    """Visao por escola de origem."""
    st.markdown("**Por escola**")

    linhas = detalhar_alunos_por_escola(ano_encaminhamento=ano_encaminhamento)

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
            "Ver alunos", key="situacao_ver_alunos", width="stretch",
        ):
            ir_para("Alunos", aluno_origem=escolhida,
                    aluno_ano=ano_encaminhamento)

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
        width="stretch",
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


def _situacao_aluno(ano_encaminhamento: int = None):
    """Quatro cards clicaveis; ao clicar no proprio card, o editor aparece."""
    from encaminhamento.utils.helpers import get_or_create_school_from_name

    contagens = contar_situacao_aluno(ano_encaminhamento)
    total = contagens["alunos"]

    def _pct(q):
        return round((q / total * 100) if total else 0)

    st.subheader("Situação dos alunos")

    if "situacao_aluno_aberto" not in st.session_state:
        st.session_state["situacao_aluno_aberto"] = None

    cards = [
        ("alunos", "Alunos", contagens["alunos"], COR_SITUACAO["alunos"]),
        ("encaminhados", "Encaminhados", contagens["encaminhados"], COR_SITUACAO["encaminhados"]),
        ("pendente", "Pendente", contagens["pendente"], COR_SITUACAO["pendente"]),
        ("info_pendente", "Informação Pendente", contagens["info_pendente"], COR_SITUACAO["info_pendente"]),
    ]
    _chaves = {k for k, _, _, _ in cards}

    # Renderiza os 4 cards como um componente interativo (HTML + CSS + JS).
    # Clique em um card -> trigger 'clicked' -> abre o editor em linha.
    dados = [
        {"chave": k, "titulo": t, "quantidade": q, "cor": cor, "pct": _pct(q)}
        for k, t, q, cor in cards
    ]
    _resultado_cards = _componente_cards_situacao(
        data=dados, key="situacao_aluno_cards", on_clicked_change=lambda: None,
        width="stretch", height="88px",
    )
    clicked = _resultado_cards.get("clicked")
    if clicked in _chaves:
        st.session_state["situacao_aluno_aberto"] = clicked

    chave_aberta = st.session_state.get("situacao_aluno_aberto")

    if chave_aberta is not None:
        titulo = next(t for k, t, _, _ in cards if k == chave_aberta)
        quantidade = next(q for k, _, q, _ in cards if k == chave_aberta)

        if quantidade == 0:
            with st.container(border=True):
                st.caption(f"Sem alunos em '{titulo}'.")
                if st.button("✕ Fechar", key=f"sit_aluno_fechar_zero_{chave_aberta}"):
                    st.session_state["situacao_aluno_aberto"] = None
                    st.rerun()
        else:
            linhas = detalhar_situacao_aluno(chave_aberta, ano_encaminhamento)
            if not linhas:
                with st.container(border=True):
                    st.caption(f"Sem alunos em '{titulo}'.")
                    if st.button("✕ Fechar", key=f"sit_aluno_fechar_vazio_{chave_aberta}"):
                        st.session_state["situacao_aluno_aberto"] = None
                        st.rerun()
            else:
                df = pd.DataFrame(linhas)
                column_config = {
                    "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "Aluno": st.column_config.TextColumn("Aluno", disabled=True, width="medium"),
                    "Origem": st.column_config.TextColumn("Origem", disabled=True, width="medium"),
                    "1ª opção": st.column_config.TextColumn("1ª opção", width="medium"),
                    "2ª opção": st.column_config.TextColumn("2ª opção", width="medium"),
                    "Endereço": st.column_config.TextColumn("Endereço", width="large"),
                    "Alocado em": st.column_config.TextColumn("Alocado em", disabled=True, width="medium"),
                    "Status": st.column_config.TextColumn("Status", disabled=True, width="small"),
                    "Pendência": st.column_config.TextColumn("Pendência", width="medium"),
                }
                edited = st.data_editor(
                    df, width="stretch", hide_index=True,
                    column_config=column_config,
                    key=f"sit_aluno_edit_{chave_aberta}", num_rows="dynamic",
                )
                st.caption(f"{len(edited)} aluno(s) — edite e salve.")
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1:
                    if st.button("💾 Salvar", key=f"sit_aluno_salvar_{chave_aberta}", type="primary", width="stretch"):
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
                                    session, sid,
                                    name=row["Aluno"], address=row["Endereço"],
                                    destination_school_1_id=(get_or_create_school_from_name(d1, is_destination=True) if d1 else None),
                                    destination_school_2_id=(get_or_create_school_from_name(d2, is_destination=True) if d2 else None),
                                )
                            mudancas += 1
                        if mudancas:
                            get_allocation_service().run_allocation()
                            st.success(f"{mudancas} atualizado(s).")
                            st.rerun()
                        else:
                            st.info("Nenhuma alteração.")
                with c2:
                    if st.button("🔄 Re-alocar", key=f"sit_aluno_realocar_{chave_aberta}", width="stretch"):
                        with st.spinner("Alocando..."):
                            resultado = get_allocation_service().run_allocation()
                        st.success(f"{resultado.get('alocados', 0)} alocados, {resultado.get('sem_vaga', 0)} sem vaga.")
                        st.rerun()
                with c3:
                    if st.button("✕ Fechar", key=f"sit_aluno_fechar_edit_{chave_aberta}", width="stretch"):
                        st.session_state["situacao_aluno_aberto"] = None
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
        if st.button("Ver todas as escolas →", width="stretch",):
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
            if st.button(acao, key=f"atencao_{e['id']}", width="stretch",):
                if e["geolocalizada"]:
                    ir_para("Escolas", mapa_escola=e["id"])
                else:
                    ir_para("Escolas", localizacao=True)

    st.divider()
    with st.expander("Ver todos os números", expanded=False):
        st.dataframe(
            tabela.sort_values("Escola"),
            width="stretch",
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
    # Mantem apenas os RESUMO_KEEP_N mais recentes, removendo o restante.
    manter_arquivos_recentes(DATA_DIR, "resumo_*.xlsx", RESUMO_KEEP_N)
    with open(caminho, "rb") as f:
        st.download_button(
            "⬇️ Exportar resumo",
            f.read(),
            file_name=f"resumo_encaminhamento_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )


def _seletor_ano_encaminhamento():
    """
    Ano alvo do encaminhamento (recebimento X -> encaminhamento X+1).

    'Todos' = sem filtro. Retorna None quando nao houver filtro.
    """
    with get_session() as session:
        anos_classe = {
            c + 1
            for c in session.execute(select(Class.year)).scalars().all()
            if c
        }
        anos_lote = {
            b
            for b in session.execute(select(ForwardingBatch.year)).scalars().all()
            if b
        }
        todos = sorted(anos_classe | anos_lote)

    if not todos:
        st.info("Nenhum ano de encaminhamento definido ainda.")
        return None

    escolha = st.selectbox(
        "Ano de encaminhamento",
        options=["Todos"] + [str(a) for a in todos],
        key="dashboard_ano_encaminhamento",
        help="Recebidos em X sao encaminhados em X+1 (ex.: 2026 -> 2027).",
    )
    return None if escolha == "Todos" else int(escolha)


def render():
    sidebar_navigation()

    col_t, col_b = st.columns([4, 1])
    with col_t:
        st.title("Painel de Controle")
        st.caption("Visão geral do encaminhamento de alunos")
    with col_b:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar", width="stretch",):
            st.rerun()

    ano_encaminhamento = _seletor_ano_encaminhamento()

    resumo = montar_resumo(ano_encaminhamento=ano_encaminhamento)

    st.divider()
    _passos()

    st.divider()
    _pendencias(resumo)

    st.divider()
    _situacao_aluno(ano_encaminhamento)

    st.divider()
    _situacao_por_escola(ano_encaminhamento)

    st.divider()
    _escolas_atencao(resumo)

    st.divider()
    _exportar(resumo)
