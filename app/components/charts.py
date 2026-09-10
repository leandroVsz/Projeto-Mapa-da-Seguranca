"""
Componentes de gráficos e análises estatísticas para o Streamlit.
"""

import streamlit as st
import pandas as pd


def render_charts(stats: dict):
    """Renderiza gráficos estatísticos organizados em 2 colunas."""
    if not stats:
        st.info("Nenhuma estatística disponível.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📍 Top 10 Regiões Administrativas com Mais Ocorrências")
        por_regiao = stats.get("por_regiao", {})
        if por_regiao:
            s_reg = pd.Series(por_regiao)
            st.bar_chart(s_reg, color="#38bdf8")

    with c2:
        st.markdown("##### 🚨 Distribuição por Natureza do Crime")
        por_crime = stats.get("por_natureza", {})
        if por_crime:
            s_crime = pd.Series(por_crime)
            st.bar_chart(s_crime, color="#ef4444")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("##### 🕒 Ocorrências por Período do Dia")
        por_periodo = stats.get("por_periodo", {})
        if por_periodo:
            s_per = pd.Series(por_periodo)
            st.bar_chart(s_per, color="#f59e0b")

    with c4:
        st.markdown("##### 📈 Evolução Histórica Anual")
        por_ano = stats.get("por_ano", {})
        if por_ano:
            s_ano = pd.Series(por_ano)
            st.line_chart(s_ano, color="#10b981")

