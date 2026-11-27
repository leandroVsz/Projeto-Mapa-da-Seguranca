"""
Componente Streamlit: "Consultar minha região" (requisito 4).

Três formas de entrada — endereço, CEP ou geolocalização do dispositivo —
que resultam na RA correspondente. Ao achar a RA, o componente a registra
como região de detalhe (mesmo callback do clique no mapa), e o painel de
detalhe já existente passa a exibir os indicadores dela.
"""

from typing import Any, Callable, Dict, Optional, cast

import streamlit as st

ENDERECO, CEP, GPS = "📝 Endereço", "📮 CEP", "📡 Minha localização"
_ROTULO_METODO = {
    "poligono_postgis": "contorno oficial da RA (PostGIS)",
    "poligono_geojson": "contorno oficial da RA (GeoJSON local)",
    "centroide_mais_proximo": "RA de centro mais próximo (aproximado)",
}


def _mostrar_resultado(res: Dict[str, Any]) -> None:
    if "erro" in res:
        st.error(res["erro"])
        return
    if res.get("endereco_encontrado"):
        st.caption(f"Local encontrado: {res['endereco_encontrado']}")
    st.caption(
        f"Coordenadas: {res['latitude']:.5f}, {res['longitude']:.5f} · "
        f"Método: {_ROTULO_METODO.get(res['metodo'], res['metodo'])}"
    )
    if res.get("precisao") == "bairro":
        st.warning(
            "O mapa só encontrou o **bairro**, não a rua deste CEP. O ponto marca o centro do "
            "bairro, por isso CEPs diferentes do mesmo bairro caem no mesmo lugar. "
            "A região (RA) continua correta."
        )
    elif res.get("aproximado"):
        st.warning(
            "Resultado aproximado: a RA foi estimada pelo centro mais próximo "
            "(sem o contorno oficial disponível). Confira no mapa."
        )
    st.caption(
        "O filtro **Região Administrativa** da barra lateral foi ajustado para essa região. "
        "Para voltar a ver o DF inteiro, limpe esse filtro."
    )


def render_localizar(client: Any, selecionar_regiao: Callable[[str], None]) -> None:
    """Desenha o painel de consulta e aciona `selecionar_regiao(nome_ra)`."""
    # Container (e não expander/radio): mantém a estrutura de widgets que os
    # testes de usabilidade já indexam por posição (app.radio[0], app.expander).
    with st.container(border=True):
        st.markdown("**🔎 Consultar a região por endereço, CEP ou localização**")
        modo = st.segmented_control(
            "Como deseja informar o local?",
            [ENDERECO, CEP, GPS],
            default=ENDERECO,
            key="loc_modo",
            label_visibility="collapsed",
        ) or ENDERECO
        resultado: Optional[Dict[str, Any]] = None

        if modo == ENDERECO:
            with st.form("form-loc-endereco"):
                endereco = st.text_input(
                    "Endereço", placeholder="Ex.: CNB 12 Lote 3, Taguatinga",
                )
                if st.form_submit_button("Buscar região", type="primary"):
                    with st.spinner("Localizando endereço..."):
                        resultado = client.localizar_regiao(endereco=endereco)

        elif modo == CEP:
            with st.form("form-loc-cep"):
                cep = st.text_input("CEP", placeholder="Ex.: 70040-010", max_chars=9)
                if st.form_submit_button("Buscar região", type="primary"):
                    with st.spinner("Consultando CEP..."):
                        resultado = client.localizar_regiao(cep=cep)

        else:
            st.caption("O navegador vai pedir permissão para acessar a sua localização.")
            pos: Optional[Dict[str, Any]] = None
            try:
                from streamlit_geolocation import streamlit_geolocation  # pyright: ignore

                pos = cast(Dict[str, Any], streamlit_geolocation())  # pyright: ignore
            except ImportError:
                st.info("Instale `streamlit-geolocation` (pip install -r requirements.txt) "
                        "ou informe as coordenadas manualmente abaixo.")
            if pos and pos.get("latitude") is not None and pos.get("longitude") is not None:
                # O componente devolve a mesma posição a cada rerun: só consulta
                # quando ela muda, para não sobrescrever a RA clicada no mapa.
                chave = (round(pos["latitude"], 5), round(pos["longitude"], 5))
                if st.session_state.get("loc_ultima_pos") != chave:
                    st.session_state["loc_ultima_pos"] = chave
                    resultado = client.localizar_regiao(
                        latitude=pos["latitude"], longitude=pos["longitude"]
                    )
            with st.form("form-loc-coord"):
                c1, c2 = st.columns(2)
                lat = c1.number_input("Latitude", value=-15.7942, format="%.5f")
                lon = c2.number_input("Longitude", value=-47.8822, format="%.5f")
                if st.form_submit_button("Usar estas coordenadas"):
                    resultado = client.localizar_regiao(latitude=lat, longitude=lon)

        if resultado is not None:
            st.session_state["loc_resultado"] = resultado
            if "erro" not in resultado:
                selecionar_regiao(resultado["regiao"])
                # Pede ao main.py que ajuste o filtro lateral de RA para a região
                # encontrada (mapa, gráficos e KPIs passam a mostrar essa RA).
                st.session_state["ra_filtro_pendente"] = resultado["regiao"]
                st.rerun()

        if st.session_state.get("loc_resultado"):
            _mostrar_resultado(st.session_state["loc_resultado"])
