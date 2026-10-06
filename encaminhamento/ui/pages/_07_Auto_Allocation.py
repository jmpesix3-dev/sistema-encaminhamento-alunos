import streamlit as st
import pandas as pd

from encaminhamento.ui.components import sidebar_navigation, seletor_abas
from encaminhamento.database import get_session
from encaminhamento.database.crud import list_schools, list_students, update_student
from encaminhamento.database.models import StudentStatus
from encaminhamento.services.allocation import get_allocation_service
from encaminhamento.services.geocoding import get_geocoding_service
from encaminhamento.utils.geo import validar_coordenada

ROTULO_ESCOLHA = {1: "1ª opção", 2: "2ª opção"}


def _grupos(resultado):
    """
    Agrupa os resultados por escola de destino.

    A ordem dentro do grupo e: primeiro os que foram pela 1a opcao, em
    ordem de prioridade; depois os da 2a opcao, tambem por prioridade.
    Sem misturar as duas fases, que tem contadores separados.
    """
    grupos = {}

    for r in resultado.results:
        if r.status == "allocated":
            chave = r.allocated_school_name or "(escola sem nome)"
        else:
            chave = "__sem_vaga__"
        grupos.setdefault(chave, []).append(r)

    for chave, alunos in grupos.items():
        def ordem(r):
            if r.status != "allocated":
                return (2, 0)
            opcao = 1 if r.original_choice_1_id == r.allocated_school_id else 2
            return (opcao, r.priority or 999)
        alunos.sort(key=ordem)

    # Escolas com mais alunos primeiro; sem vaga sempre por ultimo
    ordenados = sorted(
        (k for k in grupos if k != "__sem_vaga__"),
        key=lambda k: (-len(grupos[k]), k),
    )
    if "__sem_vaga__" in grupos:
        ordenados.append("__sem_vaga__")

    return [(k, grupos[k]) for k in ordenados]


def _linhas_do_grupo(alunos):
    """Linhas de tabela de um grupo de alunos."""
    linhas = []
    for r in alunos:
        if r.status == "allocated":
            escolha = 1 if r.original_choice_1_id == r.allocated_school_id else 2
            linhas.append({
                "Aluno": r.student_name,
                "Opcao": ROTULO_ESCOLHA.get(escolha, "-"),
                "Distancia (km)": r.distance_km,
                "Prioridade": r.priority,
            })
        else:
            linhas.append({
                "Aluno": r.student_name,
                "Opcao": "",
                "Distancia (km)": None,
                "Prioridade": None,
            })
    return linhas


def _mostrar_resultado(resultado, titulo):
    st.subheader(titulo)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alunos", resultado.total_students)
    c2.metric("Alocados", resultado.allocated)
    c3.metric("Sem vaga", resultado.sem_vaga)
    with c4:
        dist = [r.distance_km for r in resultado.results if r.distance_km is not None]
        if dist:
            st.metric("Distancia media", f"{sum(dist)/len(dist):.1f} km")

    st.markdown("**Vagas por escola**")
    if resultado.by_school:
        tabela = [{
            "Escola": info.get("school_name", str(sid)),
            "Alocados": info["allocated"],
            "Capacidade": info["capacity"],
            "Vagas livres": info["capacity"] - info["allocated"],
        } for sid, info in sorted(resultado.by_school.items(),
                                  key=lambda kv: -kv[1]["allocated"])]
        st.dataframe(
            pd.DataFrame(tabela),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Alocados": st.column_config.NumberColumn("Alocados", format="%d"),
                "Capacidade": st.column_config.NumberColumn("Capacidade", format="%d"),
                "Vagas livres": st.column_config.NumberColumn("Vagas livres", format="%d"),
            },
        )
    else:
        st.info("Nenhuma escola recebeu alunos.")

    # Alunos agrupados por escola de destino
    st.markdown("**Alunos por escola**")

    for chave, alunos in _grupos(resultado):
        if chave == "__sem_vaga__":
            rotulo = f"⚠️ Sem vaga — {len(alunos)} aluno(s)"
        else:
            capacidade = ""
            for sid, info in resultado.by_school.items():
                if info.get("school_name") == chave:
                    capacidade = f" — {info['allocated']}/{info['capacity']} vagas"
                    break
            rotulo = f"📍 {chave} — {len(alunos)} aluno(s){capacidade}"

        with st.expander(rotulo, expanded=chave != "__sem_vaga__"):
            st.dataframe(
                pd.DataFrame(_linhas_do_grupo(alunos)),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Distancia (km)": st.column_config.NumberColumn(
                        "Distancia (km)", format="%.2f"),
                    "Prioridade": st.column_config.NumberColumn("Prioridade", format="%d"),
                },
            )

    # Resumo por opcao
    primeira = sum(1 for r in resultado.results if r.status == "allocated"
                   and r.original_choice_1_id == r.allocated_school_id)
    segunda = resultado.allocated - primeira
    st.caption(
        f"{primeira} alocado(s) na 1a opcao, {segunda} na 2a opcao, "
        f"{resultado.sem_vaga} sem vaga."
    )


def render():
    sidebar_navigation()

    st.title("🎯 Alocação Automática")
    st.caption("Distribui os alunos por proximidade, respeitando a capacidade de cada escola")

    svc = get_allocation_service()
    stats = svc.get_allocation_stats()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alunos", stats["total"])
    c2.metric("Alocados", stats["allocated"])
    c3.metric("Sem vaga", stats["sem_vaga"])
    c4.metric("Pendentes", stats["pending"])

    if stats["total"] == 0:
        st.warning("Nenhum aluno cadastrado. Use a página **Alunos** para carregar as planilhas.")
        return

    if stats["allocated"] == 0:
        st.info("A alocação ainda não foi executada. Rode a prévia abaixo para conferir.")

    # Aba enviada pelo painel
    ir_alocacao = st.session_state.pop("ir_alocacao", None)
    # A capacidade e editada na pagina de Escolas, que ja tem a aba
    # Capacidade com os mesmos dados. Nao repetir aqui.
    abas = ["👁️ Prévia", "▶️ Executar", "📍 Coordenadas"]
    inicial = 2 if ir_alocacao == "coordenadas" else 0

    escolhida = seletor_abas(abas, inicial, chave="abas_alocacao")

    # -----------------------------------------------------------------
    # PREVIA
    # -----------------------------------------------------------------
    if escolhida == 0:
        c1, c2 = st.columns(2)

        with c1:
            if st.button("👁️ Simular alocação", type="primary", use_container_width=True):
                with st.spinner("Calculando..."):
                    st.session_state["previa"] = svc.run_allocation(preview=True)

        with c2:
            if "previa" in st.session_state:
                if st.button("🗑️ Limpar prévia", use_container_width=True):
                    st.session_state.pop("previa", None)
                    st.rerun()

        if "previa" in st.session_state:
            _mostrar_resultado(st.session_state["previa"], "Prévia da alocação")
        else:
            st.info("Clique em **Simular alocação** para ver o resultado sem gravar no banco.")

    # -----------------------------------------------------------------
    # EXECUTAR
    # -----------------------------------------------------------------
    elif escolhida == 1:
        st.warning(
            "A execução grava a alocação no banco: cada aluno passa a ter uma "
            "**escola de destino definida** e a prioridade por proximidade."
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("▶️ Executar alocação", type="primary", use_container_width=True):
                with st.spinner("Alocando alunos..."):
                    resultado = svc.run_allocation(preview=False)
                st.session_state["previa"] = resultado
                st.success(
                    f"**{resultado.allocated} aluno(s) alocado(s)**, "
        f"{resultado.sem_vaga} sem vaga."
                )

        with col2:
            if stats["allocated"] > 0 and st.button("↩️ Desfazer alocação", use_container_width=True):
                total = svc.reset_allocations()
                st.session_state.pop("previa", None)
                st.success(f"{total} aluno(s) voltou para pendente.")
                st.rerun()

        if "previa" in st.session_state and st.session_state["previa"].allocated:
            _mostrar_resultado(st.session_state["previa"], "Último resultado")

    # -----------------------------------------------------------------
    # COORDENADAS
    # -----------------------------------------------------------------
    elif escolhida == 2:
        _aba_coordenadas(svc)


# ======================================================================
# Aba: Coordenadas
# ======================================================================
def _aba_coordenadas(svc):
    st.subheader("Coordenadas dos alunos")
    st.caption(
        "A alocação por proximidade precisa das coordenadas. "
        "Sem elas, o aluno não entra na ordenação por distância."
    )

    with get_session() as session:
        escolas = list_schools(session)
        alunos = list_students(session, status=StudentStatus.DRAFT, limit=5000)

        esc_ok = sum(1 for e in escolas if e.latitude is not None)
        alu_ok = sum(1 for a in alunos if a.latitude is not None)
        pendentes = [
            {
                "id": a.id,
                "nome": a.name,
                "endereco": a.address or "",
                "origem": a.origin_school.name if a.origin_school else "",
                "latitude": a.latitude,
                "longitude": a.longitude,
            }
            for a in alunos if a.latitude is None
        ]
        ja_prontos = [
            {
                "Aluno": a.name,
                "Latitude": a.latitude,
                "Longitude": a.longitude,
                "Endereço": (a.address or "")[:40],
            }
            for a in alunos if a.latitude is not None
        ]

    faltando = len(pendentes)

    c1, c2, c3 = st.columns(3)
    c1.metric("Escolas geolocalizadas", f"{esc_ok}/{len(escolas)}")
    c2.metric("Alunos geolocalizados", f"{alu_ok}/{len(alunos)}")
    c3.metric("Faltando", faltando)

    # Alunos que faltam
    if not faltando:
        st.success("Todos os alunos têm coordenadas.")
    else:
        st.warning(
            f"**{faltando} aluno(s)** sem coordenada não podem ser alocados por "
            "proximidade."
        )

        # Servico de geocodificacao
        geo = get_geocoding_service()

        with st.expander("🔑 Serviço de geolocalização"):
            col1, col2 = st.columns([2, 1])
            with col1:
                chave = st.text_input(
                    "Chave do Google Maps Geocoding API",
                    value=geo.api_key,
                    type="password",
                    placeholder="vazio = usa OpenStreetMap",
                    key="chave_google_alunos",
                )
                if chave != geo.api_key:
                    geo.api_key = chave
                    st.info("A chave será usada na próxima busca.")
            with col2:
                st.write("")
                st.write("")
                st.caption(f"Em uso: **{', '.join(geo.provedores_ativos())}**")

            st.caption(
                "Sem a chave o sistema tenta: endereço completo, rua e número, "
                "bairro e, por último, a posição do distrito."
            )

        # Lista dos pendentes, para quem preferir ajustar na mao
        st.markdown("**Alunos sem coordenada**")

        if pendentes:
            df = pd.DataFrame([{
                "ID": p["id"],
                "Aluno": p["nome"],
                "Origem": p["origem"],
                "Endereço": p["endereco"][:50],
                "Latitude": None,
                "Longitude": None,
            } for p in pendentes])

            edited = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                height=260,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", disabled=True),
                    "Aluno": st.column_config.TextColumn("Aluno", disabled=True),
                    "Origem": st.column_config.TextColumn("Origem", disabled=True),
                    "Endereço": st.column_config.TextColumn("Endereço", disabled=True),
                    "Latitude": st.column_config.NumberColumn("Latitude", format="%.6f"),
                    "Longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
                },
                key="coord_alunos_editor",
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("💾 Salvar coordenadas digitadas", use_container_width=True):
                    salvas = 0
                    avisos = []
                    for _, row in edited.iterrows():
                        lat, lon = row["Latitude"], row["Longitude"]
                        if pd.isna(lat) or pd.isna(lon):
                            continue
                        ok, msg = validar_coordenada(lat, lon)
                        if not ok:
                            avisos.append(f"{row['Aluno']}: {msg}")
                            continue
                        with get_session() as session:
                            update_student(
                                session, int(row["ID"]),
                                latitude=float(lat), longitude=float(lon),
                            )
                        salvas += 1

                    if salvas:
                        st.success(f"{salvas} aluno(s) com coordenada salva.")
                    else:
                        st.info("Nenhuma coordenada preenchida.")
                    for aviso in avisos:
                        st.warning(aviso)
                    if salvas:
                        st.rerun()

            with col2:
                if st.button("🗺️ Buscar automaticamente", type="primary",
                             use_container_width=True):
                    alvos = [
                        {"id": p["id"], "endereco": p["endereco"], "nome": p["nome"]}
                        for p in pendentes
                    ]

                    barra = st.progress(0)
                    rotulo = st.empty()
                    registro = []

                    def progresso(atual, total, endereco, status, resultado=None):
                        pct = (atual - 1) / total if total else 1
                        barra.progress(pct)
                        rotulo.text(f"[{atual}/{total}] {str(endereco)[:60]}")
                        if resultado:
                            registro.append(
                                f"[{atual}/{total}] {status}  "
                                f"{endereco[:45]}  "
                                f"({resultado[0]:.5f}, {resultado[1]:.5f})"
                            )
                        else:
                            registro.append(f"[{atual}/{total}] {endereco[:45]}")

                        with st.expander("Log da busca", expanded=False):
                            st.code("\n".join(registro[-10:]), language=None)

                    geo.progresso = progresso
                    resumo = geo.geocode_alunos(alvos)

                    for a in alvos:
                        if a.get("lat") is not None:
                            with get_session() as session:
                                update_student(
                                    session, a["id"],
                                    latitude=a["lat"], longitude=a["lon"],
                                )

                    barra.progress(1.0)

                    niveis = resumo["por_nivel"]
                    exatas = niveis.get("exata", 0) + niveis.get("rua", 0)
                    bairro = niveis.get("localidade", 0)
                    aproximadas = niveis.get("distrito", 0) + niveis.get("centro", 0)

                    st.success(
                        f"**{len(alvos)} aluno(s) processado(s)** — "
                        f"{exatas} por endereço, {bairro} por bairro, "
                        f"{aproximadas} aproximadas."
                    )
                    st.rerun()

    # Alunos ja geolocalizados
    if ja_prontos:
        st.markdown("**Alunos já geolocalizados**")
        st.dataframe(
            pd.DataFrame(ja_prontos),
            use_container_width=True,
            hide_index=True,
            height=240,
            column_config={
                "Latitude": st.column_config.NumberColumn("Latitude", format="%.6f"),
                "Longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
            },
        )
