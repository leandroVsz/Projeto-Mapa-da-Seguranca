"""
Componentes de gráficos e análises estatísticas para o Streamlit.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.chart_export import gerar_csv, gerar_pdf, nome_arquivo

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]

DIMENSOES = {
    "Região Administrativa": "por_regiao",
    "Natureza do crime": "por_natureza",
    "Mês": "por_mes",
    "Ano": "por_ano",
}

TIPOS_GRAFICO = ["Barras", "Barras horizontais", "Linha", "Área", "Pizza", "Rosca"]


def montar_dataframe(stats: dict, dimensao: str, top_n: int = 10) -> pd.DataFrame:
    """Converte uma dimensão do dicionário `stats` em DataFrame (Categoria, Ocorrências)."""
    chave = DIMENSOES[dimensao]
    dados = (stats or {}).get(chave) or {}
    if not dados:
        return pd.DataFrame(columns=["Categoria", "Ocorrências"])

    if chave == "por_mes":
        itens = sorted((int(k), v) for k, v in dados.items())
        df = pd.DataFrame({
            "Categoria": [MESES[m - 1] for m, _ in itens],
            "Ocorrências": [v for _, v in itens],
        })
    elif chave == "por_ano":
        itens = sorted((int(k), v) for k, v in dados.items())
        df = pd.DataFrame({
            "Categoria": [str(a) for a, _ in itens],
            "Ocorrências": [v for _, v in itens],
        })
    else:
        df = (pd.DataFrame(list(dados.items()), columns=["Categoria", "Ocorrências"])
              .sort_values("Ocorrências", ascending=False)
              .head(top_n))
    return df.reset_index(drop=True)


def criar_figura(df: pd.DataFrame, tipo: str, titulo: str):
    """Cria a figura Plotly conforme o tipo escolhido."""
    x, y = "Categoria", "Ocorrências"
    if tipo == "Barras":
        fig = px.bar(df, x=x, y=y, title=titulo)
    elif tipo == "Barras horizontais":
        fig = px.bar(df.iloc[::-1], x=y, y=x, orientation="h", title=titulo)
    elif tipo == "Linha":
        fig = px.line(df, x=x, y=y, markers=True, title=titulo)
    elif tipo == "Área":
        fig = px.area(df, x=x, y=y, title=titulo)
    elif tipo == "Pizza":
        fig = px.pie(df, names=x, values=y, title=titulo)
    else:  # Rosca
        fig = px.pie(df, names=x, values=y, hole=0.45, title=titulo)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    return fig


def _render_visao_geral(stats: dict):
    """Os 4 gráficos fixos originais."""
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📍 Top 10 Regiões Administrativas com Mais Ocorrências")
        if stats.get("por_regiao"):
            st.bar_chart(pd.Series(stats["por_regiao"]), color="#38bdf8")
    with c2:
        st.markdown("##### 🚨 Distribuição por Natureza do Crime")
        if stats.get("por_natureza"):
            st.bar_chart(pd.Series(stats["por_natureza"]), color="#ef4444")

    c3, c4 = st.columns(2)
    with c3:
        por_mes = stats.get("por_mes", {})
        if por_mes:
            st.markdown("##### 📅 Ocorrências por Mês (histórico agregado)")
            serie = pd.Series({
                MESES[int(m) - 1]: q
                for m, q in sorted(por_mes.items(), key=lambda kv: int(kv[0]))
            })
            st.bar_chart(serie, color="#f59e0b")
    with c4:
        if stats.get("por_ano"):
            st.markdown("##### 📈 Evolução Histórica Anual")
            st.line_chart(pd.Series(stats["por_ano"]), color="#10b981")


def render_charts(stats: dict):
    """Renderiza o gráfico personalizado (escolha de tipo) + visão geral."""
    if not stats:
        st.info("Nenhuma estatística disponível.")
        return

    st.markdown("#### 🎛️ Gráfico personalizado")
    c1, c2, c3 = st.columns([2, 2, 1])
    dimensao = c1.selectbox("Dados a analisar", list(DIMENSOES), key="grafico_dimensao")
    tipo = c2.selectbox("Tipo de gráfico", TIPOS_GRAFICO, key="grafico_tipo")
    top_n = c3.number_input("Top N", min_value=3, max_value=30, value=10,
                            key="grafico_topn",
                            disabled=dimensao in ("Mês", "Ano"))

    df = montar_dataframe(stats, dimensao, int(top_n))
    if df.empty:
        st.info("Sem dados para os filtros atuais.")
    else:
        titulo = f"Ocorrências por {dimensao.lower()}"
        st.plotly_chart(criar_figura(df, tipo, titulo), width="stretch")

        b1, b2, _ = st.columns([1, 1, 3])
        b1.download_button(
            "⬇️ Exportar CSV",
            data=gerar_csv(df),
            file_name=nome_arquivo(titulo, tipo, "csv"),
            mime="text/csv",
            key="exportar_csv",
            width="stretch",
        )
        b2.download_button(
            "⬇️ Exportar PDF",
            data=gerar_pdf(df, tipo, titulo),
            file_name=nome_arquivo(titulo, tipo, "pdf"),
            mime="application/pdf",
            key="exportar_pdf",
            width="stretch",
        )

    with st.expander("📊 Visão geral (gráficos fixos)", expanded=False):
        _render_visao_geral(stats)
