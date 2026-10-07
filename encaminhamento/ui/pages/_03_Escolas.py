import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from encaminhamento.ui.components import sidebar_navigation, seletor_abas
from encaminhamento.database import get_session
from encaminhamento.database.crud import list_schools, update_school
from encaminhamento.services.geocoding import NIVEL, get_geocoding_service
from encaminhamento.utils.geo import validar_coordenada

CENTRO_SJB = (-21.6344, -41.0499)


# ======================================================================
# Aba: dados cadastrais
# ======================================================================
def _aba_dados():
    st.subheader("Dados das escolas")
    st.caption(
        "Edite os dados e clique em salvar. As alterações ficam no banco; "
        "para trazer o arquivo escolas.xlsx de volta, rode importar_escolas.py."
    )

    with get_session() as session:
        escolas = list_schools(session)
        linhas = [{
            "ID": e.id,
            "Escola": e.name,
            "Modalidade": e.modalidade or "",
            "Endereço": e.address or "",
            "Distrito": e.distrito or "",
            "Contato": e.contato or "",
            "Telefone": e.phone or "",
            "E-mail": e.email or "",
        } for e in escolas]

    if not linhas:
        st.info("Nenhuma escola cadastrada.")
        return

    df = pd.DataFrame(linhas)

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "Escola": st.column_config.TextColumn("Escola", required=True, width="large"),
            "Modalidade": st.column_config.TextColumn("Modalidade"),
            "Endereço": st.column_config.TextColumn("Endereço", width="large"),
            "Distrito": st.column_config.TextColumn("Distrito", width="small"),
            "Contato": st.column_config.TextColumn("Contato"),
            "Telefone": st.column_config.TextColumn("Telefone"),
            "E-mail": st.column_config.TextColumn("E-mail"),
        },
        key="dados_escolas_editor",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Salvar alterações", type="primary", use_container_width=True):
            with get_session() as session:
                cadastradas = {e.id: e for e in list_schools(session)}

            salvas = 0
            avisos = []

            for _, row in edited.iterrows():
                eid = int(row["ID"])
                atual = cadastradas.get(eid)
                if atual is None:
                    continue

                novo_nome = (row["Escola"] or "").strip()
                if not novo_nome:
                    avisos.append(f"ID {eid}: nome vazio, não salvo.")
                    continue

                mudanca = (
                    atual.name != novo_nome
                    or (atual.modalidade or "") != (row["Modalidade"] or "")
                    or (atual.address or "") != (row["Endereço"] or "")
                    or (atual.distrito or "") != (row["Distrito"] or "")
                    or (atual.contato or "") != (row["Contato"] or "")
                    or (atual.phone or "") != (row["Telefone"] or "")
                    or (atual.email or "") != (row["E-mail"] or "")
                )
                if not mudanca:
                    continue

                with get_session() as session:
                    update_school(
                        session, eid,
                        name=novo_nome,
                        modalidade=row["Modalidade"],
                        address=row["Endereço"],
                        distrito=row["Distrito"],
                        contato=row["Contato"],
                        phone=row["Telefone"],
                        email=row["E-mail"],
                    )
                salvas += 1

            if salvas:
                st.success(f"{salvas} escola(s) atualizada(s).")
                st.rerun()
            else:
                st.info("Nenhuma alteração.")

            for aviso in avisos:
                st.warning(aviso)

    with col2:
        st.caption(
            f"{len(linhas)} escola(s) cadastrada(s). "
            "Campos em branco podem ser preenchidos aqui mesmo."
        )


# ======================================================================
# Aba: capacidade
# ======================================================================
def _aba_capacidade():
    st.subheader("Capacidade de alunos por escola")
    st.caption("A alocacao usa esse numero: ninguem entra acima da capacidade.")

    with get_session() as session:
        dados = [{
            "ID": e.id,
            "Escola": e.name,
            "Distrito": e.distrito or "",
            "Capacidade atual": e.oferta or 0,
            "Nova capacidade": e.oferta or 0,
        } for e in list_schools(session)]

    if not dados:
        st.info("Nenhuma escola cadastrada.")
        return

    edited = st.data_editor(
        pd.DataFrame(dados),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True),
            "Escola": st.column_config.TextColumn("Escola", disabled=True),
            "Distrito": st.column_config.TextColumn("Distrito", disabled=True),
            "Capacidade atual": st.column_config.NumberColumn("Capacidade atual", disabled=True),
            "Nova capacidade": st.column_config.NumberColumn(
                "Nova capacidade", min_value=0, max_value=500, step=1, required=True
            ),
        },
        key="cap_editor",
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("💾 Salvar capacidades", type="primary", use_container_width=True):
            alteradas = 0
            for _, row in edited.iterrows():
                nova = int(row["Nova capacidade"])
                if nova != int(row["Capacidade atual"]):
                    with get_session() as session:
                        update_school(session, int(row["ID"]), oferta=nova)
                    alteradas += 1

            st.success(f"{alteradas} escola(s) atualizada(s)." if alteradas
                       else "Nenhuma alteracao.")
            if alteradas:
                st.rerun()

    with c2:
        sem_capacidade = int((edited["Nova capacidade"] == 0).sum())
        if sem_capacidade:
            st.warning(f"{sem_capacidade} escola(s) sem capacidade definida.")
        else:
            st.success("Todas as escolas tem capacidade.")


# ======================================================================
# Aba: localizacao
# ======================================================================
def _js_pin(nome_mapa: str) -> str:
    """
    JavaScript que desenha um pin vermelho no ponto clicado no mapa.

    O mapa do folium e criado em um script separado, as vezes depois deste.
    Por isso o codigo espera o mapa existir antes de se conectar aos eventos.
    """
    return f"""
<script>
(function() {{
  var NOME = {nome_mapa};
  var tentativas = 0;

  function conectar() {{
    tentativas += 1;
    var mapa = window[NOME];

    if (!mapa) {{
      if (tentativas < 100) {{ setTimeout(conectar, 50); }}
      return;
    }}

    var pin = L.marker(mapa.getCenter(), {{
      draggable: true,
      zIndexOffset: 1000,
      icon: L.icon({{
        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
        iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        shadowSize: [41, 41],
        className: 'pin-escola'
      }})
    }});

    function mostrar(lat, lng) {{
      pin.setLatLng([lat, lng]);
      if (!mapa.hasLayer(pin)) {{ pin.addTo(mapa); }}
      pin.setZIndexOffset(1000);
    }}

    // Desenha o pin na posicao inicial
    var centro = mapa.getCenter();
    mostrar(centro.lat, centro.lng);
    pin.bindTooltip('Posicao escolhida', {{permanent: true, direction: 'top'}})
       .openTooltip();

    // Clique no mapa move o pin
    mapa.on('click', function(e) {{
      mostrar(e.latlng.lat, e.latlng.lng);
    }});

    // Arrastar o pin tambem atualiza
    pin.on('dragend', function() {{
      var p = pin.getLatLng();
      mostrar(p.lat, p.lng);
    }});
  }}

  conectar();
}})();
</script>
"""


def _mapa_ajuste(escola):
    """
    Mapa com o marcador da escola.

    Duas formas de escolher o ponto:
      - clicar no mapa (last_clicked)
      - desenhar um ponto com a ferramenta do topo (last_active_drawing)
    """
    lat = escola["latitude"] if escola["latitude"] is not None else CENTRO_SJB[0]
    lon = escola["longitude"] if escola["longitude"] is not None else CENTRO_SJB[1]

    # Posicao escolhida na ultima interacao, se houver
    escolhida = escola.get("pin")
    if escolhida:
        lat, lon = escolhida

    mapa = folium.Map(location=[lat, lon], zoom_start=17)

    # Demais escolas, como referencia
    for outra in escola["demais"]:
        if outra["latitude"] is not None and outra["longitude"] is not None:
            folium.CircleMarker(
                location=[outra["latitude"], outra["longitude"]],
                radius=4, color="#999", fill=True, fill_opacity=0.45,
                tooltip=outra["nome"],
            ).add_to(mapa)

    # Marcador da posicao escolhida
    folium.Marker(
        location=[lat, lon],
        icon=folium.Icon(color="red", icon="info-sign"),
        tooltip=escola["nome"],
    ).add_to(mapa)

    # Posicao ja salva, quando difere da escolhida
    if escola["latitude"] is not None and (
        escola["latitude"] != lat or escola["longitude"] != lon
    ):
        folium.CircleMarker(
            location=[escola["latitude"], escola["longitude"]],
            radius=9, color="blue", fill=False, weight=3,
            tooltip="Posicao salva",
        ).add_to(mapa)

    # Ferramenta para marcar ponto exato
    Draw(
        export=True,
        draw_options={
            "marker": True,
            "circle": False,
            "circlemarker": False,
            "polyline": False,
            "polygon": False,
            "rectangle": False,
        },
        edit_options={"remove": True},
    ).add_to(mapa)

    # JavaScript: desenha o pin no ponto clicado
    mapa.get_root().html.add_child(folium.Element(_js_pin(mapa.get_name())))

    saida = st_folium(
        mapa,
        key=f"mapa_escola_{escola['id']}",
        height=470,
        returned_objects=["last_clicked", "last_active_drawing"],
    )

    if not isinstance(saida, dict):
        return None

    # Ponto desenhado com a ferramenta
    desenho = saida.get("last_active_drawing")
    if desenho:
        ponto = _ponto_do_desenho(desenho)
        if ponto:
            return ponto

    # Clique no mapa
    clique = saida.get("last_clicked")
    if isinstance(clique, dict) and "lat" in clique:
        return (float(clique["lat"]), float(clique["lng"]))

    return None

def _ponto_do_desenho(desenho):
    """Le a coordenada de um desenho do plugin Draw."""
    if not isinstance(desenho, dict):
        return None
    lat = desenho.get("lat")
    lon = desenho.get("lng")
    if lat is not None and lon is not None:
        return (float(lat), float(lon))
    return None


def _aba_localizacao():
    st.subheader("Localização das escolas")
    st.caption("A localizacao define a proximidade usada na alocacao de alunos.")

    geo = get_geocoding_service()

    with get_session() as session:
        escolas = [{
            "id": e.id,
            "nome": e.name,
            "endereco": e.address or "",
            "distrito": e.distrito or "",
            "latitude": e.latitude,
            "longitude": e.longitude,
        } for e in list_schools(session)]

    total = len(escolas)
    prontas = sum(1 for e in escolas if e["latitude"] is not None)
    faltando = total - prontas

    c1, c2, c3 = st.columns(3)
    c1.metric("Escolas", total)
    c2.metric("Localizadas", prontas)
    c3.metric("Faltando", faltando)

    # ---------------- busca automatica ----------------
    with st.expander("🔑 Busca automática"):
        col1, col2 = st.columns([2, 1])
        with col1:
            chave = st.text_input(
                "Chave do Google Maps Geocoding API",
                value=geo.api_key,
                type="password",
                placeholder="vazio = usa OpenStreetMap",
                key="chave_google",
            )
            if chave != geo.api_key:
                geo.api_key = chave
                st.info("A chave sera usada na proxima busca.")
        with col2:
            st.write("")
            st.write("")
            st.caption(f"Em uso: **{', '.join(geo.provedores_ativos())}**")

        st.caption(
            "Sem a chave o sistema tenta: endereco completo, rua e numero, "
            "bairro e, por ultimo, a posicao do distrito."
        )

        if faltando and st.button("🗺️ Buscar as que faltam", type="primary"):
            alvos = [{
                "id": e["id"],
                "nome": e["nome"],
                "endereco": e["endereco"] or e["nome"],
                "distrito": e["distrito"],
            } for e in escolas if e["latitude"] is None]

            barra = st.progress(0.0)
            rotulo = st.empty()
            log_placeholder = st.empty()
            registro = []

            def progresso(atual, total_, endereco, status, resultado=None):
                barra.progress((atual - 1) / total_ if total_ else 1)
                limpo = str(endereco).replace("\n", " ")[:55]
                if resultado:
                    rotulo.text(f"[{atual}/{total_}] {limpo} — {NIVEL.get(status, status)}")
                    registro.append(
                        f"[{atual}/{total_}] {resultado[0]:.5f}, {resultado[1]:.5f}  {limpo}")
                else:
                    rotulo.text(f"[{atual}/{total_}] {limpo}")
                    registro.append(f"[{atual}/{total_}] {limpo}")

                with log_placeholder:
                    with st.expander("📋 Log", expanded=False):
                        st.code("\n".join(registro[-8:]), language=None)

            geo.progresso = progresso
            resumo = geo.geocode_escolas(alvos)

            gravadas = 0
            for e in alvos:
                if e.get("lat") is not None:
                    with get_session() as session:
                        update_school(session, e["id"],
                                      latitude=e["lat"], longitude=e["lon"])
                    gravadas += 1

            barra.progress(1.0)
            rotulo.success(f"{gravadas} escola(s) localizadas.")
            with st.expander("Precisão", expanded=True):
                for nivel, qtd in resumo["por_nivel"].items():
                    if qtd:
                        st.write(f"  {NIVEL.get(nivel, nivel):<32} {qtd}")
            st.rerun()

    st.divider()

    # ---------------- lista com ajuste por escola ----------------
    st.markdown("#### Localização de cada escola")
    st.caption(
        "Confira a latitude e longitude de cada escola. Para corrigir, "
        "clique em **Ajustar** que o mapa abre."
    )

    # busca rapida
    filtrar = st.text_input("🔎 Filtrar escola", key="filtro_escolas", placeholder="digite o nome")

    # escola aberta no mapa
    aberta = st.session_state.get("mapa_escola")

    if aberta is not None:
        _painel_mapa(escolas, aberta)
        st.divider()

    for e in sorted(escolas, key=lambda x: x["nome"]):
        if filtrar and filtrar.lower() not in e["nome"].lower():
            continue

        e_id = e["id"]
        c1, c2, c3, c4 = st.columns([4, 2, 2, 1])

        with c1:
            st.markdown(f"**{e['nome']}**")
            if e["endereco"]:
                st.caption(e["endereco"][:60])

        with c2:
            if e["latitude"] is not None:
                st.caption(f"lat {e['latitude']:.5f}")
            else:
                st.caption("sem posição")

        with c3:
            if e["longitude"] is not None:
                st.caption(f"lng {e['longitude']:.5f}")
            else:
                st.caption("-")

        with c4:
            if st.button("📍 Ajustar", key=f"abrir_mapa_{e_id}", use_container_width=True):
                st.session_state["mapa_escola"] = e_id
                st.session_state.pop(f"pin_escola_{e_id}", None)
                st.rerun()


def _painel_mapa(escolas, escola_id):
    """Abre o mapa de uma escola para ajuste."""
    escola = next(e for e in escolas if e["id"] == escola_id)

    c1, c2 = st.columns([6, 1])
    with c1:
        st.markdown(f"##### 📍 {escola['nome']}")
    with c2:
        if st.button("✕ Fechar", use_container_width=True):
            st.session_state.pop("mapa_escola", None)
            st.session_state.pop("pin_escola", None)
            st.rerun()

    st.caption(
        "Clique no mapa no ponto exato da escola: um pin vermelho aparece "
        "mostrando onde voce selecionou. Depois confirme a coordenada e salve."
    )
    if escola["latitude"] is not None:
        st.caption(f"Posição salva: {escola['latitude']:.6f}, {escola['longitude']:.6f}")

    # pin escolhido na ultima interacao
    pin = st.session_state.get(f"pin_escola_{escola_id}")
    demais = [e for e in escolas if e["id"] != escola_id]
    nova = _mapa_ajuste(dict(escola, demais=demais, pin=pin))

    # guarda para o proximo rerun
    if nova:
        st.session_state[f"pin_escola_{escola_id}"] = nova

    c1, c2 = st.columns([3, 1])

    with c1:
        st.caption(
            "🔴 pin vermelho = posição escolhida agora. "
            "🔵 círculo azul = posição já salva. "
            "⚪ círculos cinzos = outras escolas."
        )

    with c2:
        if nova:
            ok, msg = validar_coordenada(*nova)
            st.write(f"📍 **{nova[0]:.6f}, {nova[1]:.6f}**")
            if not ok:
                st.error(msg)
            if st.button("💾 Salvar posição", type="primary", use_container_width=True):
                if not ok:
                    st.error("Coordenada inválida, não salva.")
                else:
                    with get_session() as session:
                        update_school(session, escola["id"],
                                      latitude=nova[0], longitude=nova[1])
                    st.session_state.pop(f"pin_escola_{escola_id}", None)
                    st.success(f"Posição de {escola['nome']} atualizada.")
                    st.rerun()
        else:
            st.info("Clique no mapa para escolher a posição.")


# ======================================================================
def render():
    sidebar_navigation()

    st.title("🏫 Escolas")
    st.caption("Cadastro, capacidade e localizacao das unidades escolares")

    # Filtros enviados pelo painel: abrem a aba ou o mapa certo
    ir_capacidade = st.session_state.pop("ir_capacidade", False)
    ir_localizacao = st.session_state.pop("ir_localizacao", False)
    ir_dados = st.session_state.pop("ir_dados", False)
    ir_mapa = st.session_state.pop("ir_mapa_escola", None)

    if ir_mapa is not None:
        st.session_state["mapa_escola"] = ir_mapa
        ir_localizacao = True

    abas = ["📋 Dados", "🎯 Capacidade", "📍 Localização"]
    if ir_capacidade:
        inicial = 1
    elif ir_localizacao or ir_mapa is not None:
        inicial = 2
    else:
        inicial = 0

    escolhida = seletor_abas(abas, inicial, chave="abas_escolas")

    if escolhida == 0:
        _aba_dados()
    elif escolhida == 1:
        _aba_capacidade()
    else:
        _aba_localizacao()
