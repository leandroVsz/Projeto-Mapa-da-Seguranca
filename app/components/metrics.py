"""
Componente de exibição de cartões de indicadores (KPIs).
"""

import streamlit as st


def render_metrics(stats: dict):
    """Renderiza 4 cartões com indicadores principais de segurança pública."""
    if not stats:
        return

    c1, c2, c3, c4 = st.columns(4)

    total = stats.get("total_ocorrencias", 0)
    total_fmt = f"{total:,}".replace(",", ".")
    c1.metric(label="Total de Ocorrências", value=total_fmt)

    ra = stats.get("ra_mais_afetada", "N/A")
    c2.metric(label="RA com Maior Incidência", value=ra)

    crime = stats.get("crime_mais_frequente", "N/A")
    c3.metric(label="Crime Mais Frequente", value=crime)

    periodo = stats.get("periodo_mais_critico", "N/A")
    c4.metric(label="Período Mais Crítico", value=periodo)

