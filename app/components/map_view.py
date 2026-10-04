"""
Componente de mapa geoespacial do DF com PyDeck.

Modos: coropleto por RA, mapa de calor 2D e hexágonos 3D. O mapa base usa
os estilos gratuitos da CARTO, que não exigem token (o Streamlit renderiza
PyDeck com MapLibre e estilos mapbox:// não funcionam sem chave).
"""

import math
from typing import Any, Dict, List, Optional

import pandas as pd
import pydeck as pdk
import streamlit as st

DF_CENTER_LAT = -15.7942
DF_CENTER_LON = -47.8822

ESTILOS_MAPA = {
    "Claro": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "Colorido": "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    "Escuro": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}
ESTILO_PADRAO = ESTILOS_MAPA["Claro"]

# RA sem ocorrências nos filtros / contorno / preenchimento nos modos heatmap e 3D
COR_SEM_DADOS = [158, 158, 158, 150]
COR_CONTORNO = [70, 70, 70, 160]
COR_NEUTRA_CAMADAS = [120, 120, 120, 35]

# Rampa âmbar → laranja → vermelho → vinho (stops interpolados linearmente)
_RAMPA_COREPLETO = [
    (0.00, [255, 237, 160]),
    (0.35, [254, 178, 76]),
    (0.65, [227, 74, 51]),
    (0.85, [165, 15, 21]),
    (1.00, [105, 15, 25]),
]


def _escala_cores():
    """Função intensidade (0–1) → [r, g, b, alpha]."""
    def cor(intensidade: float) -> List[int]:
        i = min(1.0, max(0.0, intensidade))
        for (t0, c0), (t1, c1) in zip(_RAMPA_COREPLETO, _RAMPA_COREPLETO[1:]):
            if i <= t1:
                f = 0.0 if t1 == t0 else (i - t0) / (t1 - t0)
                rgb = [int(round(c0[k] + f * (c1[k] - c0[k]))) for k in range(3)]
                return [*rgb, 235]
        return [*_RAMPA_COREPLETO[-1][1], 235]
    return cor


def _bbox_de_features(features: List[Dict[str, Any]]) -> Optional[List[float]]:
    """[minLon, minLat, maxLon, maxLat] dos contornos."""
    bb = [180.0, 90.0, -180.0, -90.0]

    def percorrer(coords):
        if isinstance(coords[0], (int, float)):
            lon, lat = coords[0], coords[1]
            bb[0] = min(bb[0], lon)
            bb[1] = min(bb[1], lat)
            bb[2] = max(bb[2], lon)
            bb[3] = max(bb[3], lat)
        else:
            for c in coords:
                percorrer(c)

    try:
        for f in features:
            geom = (f.get("geometry") or {})
            coords = geom.get("coordinates") or []
            if coords:
                percorrer(coords)
    except (TypeError, IndexError):
        return None
    return bb if bb[0] <= bb[2] else None


def _zoom_para_bbox(bb: List[float], largura_px: int = 900, altura_px: int = 600) -> float:
    """Zoom que enquadra o bbox na projeção Web Mercator."""
    span_lon = max(bb[2] - bb[0], 1e-4) * 1.08
    span_lat = max(bb[3] - bb[1], 1e-4) * 1.08
    zx = math.log2(360.0 * largura_px / (512.0 * span_lon))
    zy = math.log2(360.0 * altura_px / (512.0 * span_lat))
    return max(8.0, min(11.5, min(zx, zy)))


def _montar_dados_coropleto(
    coropleto: Optional[List[Dict[str, Any]]],
    regioes_geo: Optional[List[Dict[str, Any]]],
    top_naturezas: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Une contornos + totais; RAs sem dados entram em cinza."""
    dados = []
    if not regioes_geo:
        return dados

    totais = {c["nome"]: int(c.get("total", 0)) for c in (coropleto or [])}
    max_total = max((t for t in totais.values() if t > 0), default=0)
    cor = _escala_cores()

    for ra in regioes_geo:
        contorno = ra.get("contorno")
        if not contorno:
            continue
        nome = ra.get("nome", "—")
        total = totais.get(nome, 0)
        if total > 0 and max_total > 0:
            # sqrt comprime a cauda: crime é muito assimétrico e na escala
            # linear quase tudo ficaria no início da rampa
            cor_feat = cor(math.sqrt(total / max_total))
            rotulo = f"🔴 <b>{total:,}</b> ocorrência(s)".replace(",", ".")
            for item in (top_naturezas or {}).get(nome, [])[:3]:
                nat = str(item.get("natureza", "?"))
                qtd = int(item.get("total", 0))
                rotulo += f"<br/>• {nat}: <b>{qtd:,}</b>".replace(",", ".")
        else:
            cor_feat = COR_SEM_DADOS
            rotulo = "⚪ Sem dados registrados (nos filtros atuais)"
        rotulo += "<br/><i>🖱️ clique na RA para o detalhe completo</i>"
        dados.append({
            "nome": nome,
            "total": total,
            "rotulo": rotulo,
            "tipo": "Feature",
            "geometry": contorno,
            "cor": cor_feat,
        })
    return dados


def render_map(
    pontos_calor: List[List[float]],
    ocorrencias: List[Dict[str, Any]],
    coropleto: Optional[List[Dict[str, Any]]] = None,
    regioes_geo: Optional[List[Dict[str, Any]]] = None,
    regiao_selecionada: Optional[str] = None,
    regioes_meta: Optional[List[Dict[str, Any]]] = None,
    tipo_camada: str = "Coropleto por RA",
    estilo_mapa: Optional[str] = None,
    top_naturezas: Optional[Dict[str, Any]] = None,
    detalhe_callback=None,
):
    """Renderiza o mapa. Com detalhe_callback, o clique numa RA chama
    callback(nome_regiao) via on_select do Streamlit."""
    layers = []
    modo_coropleto = "Coropleto" in tipo_camada

    dados_coropleto = _montar_dados_coropleto(coropleto, regioes_geo, top_naturezas)

    # Polígonos das RAs: coloridos no coropleto, neutros nos outros modos
    if dados_coropleto:
        if modo_coropleto:
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                id="ra-coropleto",
                data=dados_coropleto,
                stroked=True,
                filled=True,
                get_fill_color="cor",
                get_line_color=COR_CONTORNO,
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
            ))
        else:
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                id="ra-referencia",
                data=dados_coropleto,
                stroked=True,
                filled=True,
                get_fill_color=COR_NEUTRA_CAMADAS,
                get_line_color=[90, 90, 90, 130],
                line_width_min_pixels=1,
                pickable=False,
            ))

    if pontos_calor:
        df_pts = pd.DataFrame(pontos_calor, columns=["latitude", "longitude", "peso"])
        if "Heatmap" in tipo_camada:
            layers.append(pdk.Layer(
                "HeatmapLayer",
                id="pontos-calor",
                data=df_pts,
                get_position=["longitude", "latitude"],
                get_weight="peso",
                radius_pixels=55,
                intensity=1.5,
                threshold=0.08,
            ))
        elif "3D" in tipo_camada:
            layers.append(pdk.Layer(
                "HexagonLayer",
                id="hexagonos-3d",
                data=df_pts,
                get_position=["longitude", "latitude"],
                radius=2500,
                elevation_scale=50,
                elevation_range=[0, 1200],
                extruded=True,
                coverage=1,
            ))

    if not layers:
        st.warning("Nenhum contorno de RA disponível. Configure o banco "
                   "(docker compose up -d ou DATABASE_URL na nuvem) e rode "
                   "`python -m db.load_csv`.")
        return
    if not modo_coropleto and not pontos_calor:
        st.warning("Nenhuma ocorrência encontrada para os filtros selecionados.")
    elif modo_coropleto and dados_coropleto and all(f["total"] == 0 for f in dados_coropleto):
        st.info("Nenhuma ocorrência nos filtros atuais — todas as RAs aparecem em cinza.")

    # Centro: enquadra o DF pelo bbox dos contornos, ou foca a RA selecionada
    if regiao_selecionada and regioes_meta:
        meta_ra = next((r for r in regioes_meta if r["nome"] == regiao_selecionada), None)
        if meta_ra:
            lat, lon, zoom = meta_ra["latitude"], meta_ra["longitude"], meta_ra.get("zoom", 12)
        else:
            lat, lon, zoom = DF_CENTER_LAT, DF_CENTER_LON, 9.5
    else:
        bbox = _bbox_de_features(dados_coropleto)
        if bbox:
            lat = (bbox[1] + bbox[3]) / 2
            lon = (bbox[0] + bbox[2]) / 2
            zoom = _zoom_para_bbox(bbox)
        else:
            lat, lon, zoom = DF_CENTER_LAT, DF_CENTER_LON, 9.5

    view_state = pdk.ViewState(
        latitude=lat, longitude=lon, zoom=zoom,
        pitch=45 if "3D" in tipo_camada else 0, bearing=0,
    )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=estilo_mapa or ESTILO_PADRAO,
        tooltip={
            "html": "<b>{nome}</b><br>{rotulo}",
            "style": {"backgroundColor": "#1f2937", "color": "#f9fafb"},
        } if modo_coropleto else None,
    )

    evento = st.pydeck_chart(
        deck,
        use_container_width=True,
        on_select="rerun" if detalhe_callback else "ignore",
        key="mapa-df",
    )

    # Clique numa RA: extrai o nome da feature selecionada
    if detalhe_callback:
        objetos = []
        selecao = getattr(evento, "selection", None)
        if selecao is not None:
            mapa_objs = getattr(selecao, "objects", None)
            if mapa_objs is None and hasattr(selecao, "get"):
                mapa_objs = selecao.get("objects")
            if isinstance(mapa_objs, dict):
                for lista in mapa_objs.values():
                    objetos.extend(lista or [])
            elif isinstance(mapa_objs, list):
                objetos.extend(mapa_objs)
        for obj in objetos:
            nome = obj.get("nome") if isinstance(obj, dict) else None
            if nome:
                detalhe_callback(nome)
                break

    if modo_coropleto:
        st.caption(
            "🎨 **Coropleto**: intensidade por RA — quanto mais vermelho, mais ocorrências "
            "nos filtros selecionados. **Cinzas** = RAs sem registros nos filtros atuais. "
            "Passe o mouse para ver o total e **clique na RA** para abrir o painel de detalhe."
        )
    else:
        st.caption("💡 Arraste para mover; rolagem do mouse aproxima/afasta.")
