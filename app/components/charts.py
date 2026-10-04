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
        por_mes = stats.get("por_mes", {})
        if por_mes:
            st.markdown("##### 📅 Ocorrências por Mês (histórico agregado)")
            meses = ["jan", "fev", "mar", "abr", "mai", "jun",
                     "jul", "ago", "set", "out", "nov", "dez"]
            # chaves voltam do JSON como strings; normaliza para int
            serie = pd.Series({
                meses[int(m) - 1]: q
                for m, q in sorted(por_mes.items(), key=lambda kv: int(kv[0]))
            })
            st.bar_chart(serie, color="#f59e0b")

    with c4:
        st.markdown("##### 📈 Evolução Histórica Anual")
        por_ano = stats.get("por_ano", {})
        if por_ano:
            s_ano = pd.Series(por_ano)
            st.line_chart(s_ano, color="#10b981")

