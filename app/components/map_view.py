"""
Componente de Mapa Geoespacial do DF utilizando PyDeck.

Suporta 3 modos:
  - Coropleto por RA (polígonos coloridos pela intensidade) — dados reais
  - Mapa de Calor 2D (HeatmapLayer) nos centroides das RAs
  - Agrupamento 3D (HexagonLayer)
"""

import streamlit as st
import pydeck as pdk
import pandas as pd
from typing import List, Dict, Any, Optional

DF_CENTER_LAT = -15.7942
DF_CENTER_LON = -47.8822


def _escala_cores(maximo: float):
    """Retorna função cor → [r, g, b, alpha] para intensidade 0–1
    (amarelo → laranja → vermelho escuro)."""
    def cor(intensidade: float) -> List[int]:
        i = min(1.0, max(0.0, intensidade))
        if i < 0.5:
            t = i / 0.5
            r, g, b = 255, int(255 - t * 128), 0        # amarelo → laranja
        else:
            t = (i - 0.5) / 0.5
            r, g, b = 255, int(127 - t * 100), int(t * 60)  # laranja → vermelho
        return [r, g, b, 200]
    return cor


def render_map(
    pontos_calor: List[List[float]],
    ocorrencias: List[Dict[str, Any]],
    coropleto: Optional[List[Dict[str, Any]]] = None,
    regioes_geo: Optional[List[Dict[str, Any]]] = None,
    regiao_selecionada: Optional[str] = None,
    regioes_meta: Optional[List[Dict[str, Any]]] = None,
    tipo_camada: str = "Coropleto por RA",
    raio_metros: int = 1800,
):
    """Renderiza a visualização geoespacial com PyDeck."""
    layers = []

    # ----------------------------------------------------------------------
    # Camada coropleto (polígonos das RAs)
    # ----------------------------------------------------------------------
    dados_coropleto = []
    max_total = 0
    if coropleto and regioes_geo:
        totais = {c["nome"]: c["total"] for c in coropleto}

        for ra in regioes_geo:
            contorno = ra.get("contorno")
            if not contorno:
                continue
            total = totais.get(ra["nome"], 0)
            dados_coropleto.append({
                "nome": ra["nome"],
                "total": total,
                "tipo": "Feature",
                "geometry": contorno,
            })
        # escala de cor considera só as RAs de fato plotadas
        # (o agregado 'Distrito Federal', sem polígono, não entra)
        max_total = max((f["total"] for f in dados_coropleto), default=0)

    if dados_coropleto and "Coropleto" in tipo_camada:
        cor = _escala_cores(max_total)
        for feat in dados_coropleto:
            intensidade = (feat["total"] / max_total) if max_total > 0 else 0
            feat["cor"] = cor(intensidade)

        layer_coropleto = pdk.Layer(
            "GeoJsonLayer",
            data=dados_coropleto,
            stroked=True,
            filled=True,
            get_fill_color="cor",
            get_line_color=[60, 60, 60, 120],
            line_width_min_pixels=1,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(layer_coropleto)

    # ----------------------------------------------------------------------
    # Camadas de calor / hexágonos (centroides ponderados)
    # ----------------------------------------------------------------------
    if pontos_calor:
        df_pts = pd.DataFrame(pontos_calor, columns=["latitude", "longitude", "peso"])
        if "Heatmap" in tipo_camada:
            layers.append(pdk.Layer(
                "HeatmapLayer",
                data=df_pts,
                get_position=["longitude", "latitude"],
                get_weight="peso",
                radius_pixels=int(raio_metros / 35),
                intensity=1.5,
                threshold=0.08,
            ))
        elif "3D" in tipo_camada:
            layers.append(pdk.Layer(
                "HexagonLayer",
                data=df_pts,
                get_position=["longitude", "latitude"],
                radius=int(raio_metros / 2),
                elevation_scale=50,
                elevation_range=[0, 1200],
                extruded=True,
                coverage=1,
            ))

    if not layers:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        return

    # Centro do mapa
    if regiao_selecionada and regioes_meta:
        meta_ra = next((r for r in regioes_meta if r["nome"] == regiao_selecionada), None)
        if meta_ra:
            lat, lon, zoom = meta_ra["latitude"], meta_ra["longitude"], meta_ra.get("zoom", 12)
        else:
            lat, lon, zoom = DF_CENTER_LAT, DF_CENTER_LON, 10.5
    else:
        lat, lon, zoom = DF_CENTER_LAT, DF_CENTER_LON, 9.5

    view_state = pdk.ViewState(
        latitude=lat, longitude=lon, zoom=zoom,
        pitch=45 if "3D" in tipo_camada else 0, bearing=0,
    )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/light-v10",
        tooltip={
            "html": "<b>{nome}</b><br>Ocorrências: {total}",
            "style": {"backgroundColor": "#1f2937", "color": "#f9fafb"},
        },
    )

    st.pydeck_chart(deck, use_container_width=True)
    if dados_coropleto and "Coropleto" in tipo_camada:
        st.caption(
            "🎨 **Coropleto**: intensidade por RA — quanto mais vermelho, mais ocorrências "
            "nos filtros selecionados. Passe o mouse sobre a RA para ver o total."
        )
    else:
        st.caption("💡 **Dica de Interação**: Arraste para mover. Rolagem do mouse aproxima/afasta.")
