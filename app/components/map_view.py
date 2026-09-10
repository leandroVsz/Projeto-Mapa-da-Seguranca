"""
Componente de Mapa Geoespacial e Mapa de Calor do DF utilizando PyDeck.
"""

import streamlit as st
import pydeck as pdk
import pandas as pd
from typing import List, Dict, Any, Optional

DF_CENTER_LAT = -15.7942
DF_CENTER_LON = -47.8822


def render_map(
    pontos_calor: List[List[float]],
    ocorrencias: List[Dict[str, Any]],
    regiao_selecionada: Optional[str] = None,
    regioes_meta: Optional[List[Dict[str, Any]]] = None,
    tipo_camada: str = "Mapa de Calor (Heatmap 2D)",
    raio_metros: int = 1800,
):
    """Renderiza a visualização geoespacial com PyDeck."""
    if not pontos_calor:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        return

    # Determina o centro e zoom do mapa
    if regiao_selecionada and regioes_meta:
        meta_ra = next((r for r in regioes_meta if r["nome"] == regiao_selecionada), None)
        if meta_ra:
            lat = meta_ra["latitude"]
            lon = meta_ra["longitude"]
            zoom = meta_ra.get("zoom", 13)
        else:
            lat = sum(p[0] for p in pontos_calor) / len(pontos_calor)
            lon = sum(p[1] for p in pontos_calor) / len(pontos_calor)
            zoom = 12
    else:
        lat = DF_CENTER_LAT
        lon = DF_CENTER_LON
        zoom = 10.5

    view_state = pdk.ViewState(
        latitude=lat,
        longitude=lon,
        zoom=zoom,
        pitch=45 if "3D" in tipo_camada else 0,
        bearing=0,
    )

    # Converte pontos para DataFrame
    df_pts = pd.DataFrame(pontos_calor, columns=["latitude", "longitude", "peso"])

    if "Heatmap" in tipo_camada:
        layer = pdk.Layer(
            "HeatmapLayer",
            data=df_pts,
            get_position=["longitude", "latitude"],
            get_weight="peso",
            radius_pixels=int(raio_metros / 35),
            intensity=1.5,
            threshold=0.08,
        )
        map_style = None
    else:
        # Modo 3D Hexágonos
        layer = pdk.Layer(
            "HexagonLayer",
            data=df_pts,
            get_position=["longitude", "latitude"],
            radius=int(raio_metros / 2),
            elevation_scale=50,
            elevation_range=[0, 1200],
            extruded=True,
            coverage=1,
        )
        map_style = "mapbox://styles/mapbox/dark-v10"

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style=map_style,
        tooltip={"text": "Coordenadas: {latitude}, {longitude}\nPeso: {peso}"},
    )

    st.pydeck_chart(deck, use_container_width=True)
    st.caption("💡 **Dica de Interação**: Arraste para mover o mapa. Use a rolagem do mouse para aproximar ou afastar.")

