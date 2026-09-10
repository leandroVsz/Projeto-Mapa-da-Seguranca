"""
Aplicação Principal Streamlit - Mapa da Segurança do Distrito Federal

Painel geoespacial e analítico de ocorrências criminais no DF.
Atua como cliente da API REST (FastAPI) com suporte a fallback local.
"""

from pathlib import Path
import sys
import streamlit as st
import pandas as pd

# Inclusão da raiz no sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api_client import ApiClient
from app.components.metrics import render_metrics
from app.components.map_view import render_map
from app.components.charts import render_charts
from api.services.data_ingestion import consolidar_arquivos_por_cidade, gerar_dados_amostra

# Configuração da página
st.set_page_config(
    page_title="Mapa da Segurança DF",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inicializa cliente da API
@st.cache_resource
def get_api_client():
    return ApiClient()

client = get_api_client()

# ==============================================================================
# Barra Lateral - Filtros e Configurações
# ==============================================================================
st.sidebar.title("🛡️ Mapa da Segurança DF")
st.sidebar.caption("Universidade Católica de Brasília | Soluções Computacionais")

# Status do Backend (API REST)
api_status = client.check_health()
if api_status["online"]:
    st.sidebar.success("🟢 **Backend API Conectado** (`:8000`)")
    st.sidebar.markdown("[📖 Abrir Swagger /docs](http://localhost:8000/docs)")
else:
    st.sidebar.info("🟡 **Modo Direto Local** (Sem API no ar)")
    st.sidebar.caption("Para subir o backend: `python run.py api`")

st.sidebar.divider()
st.sidebar.subheader("🔍 Filtros de Análise")

opcoes = client.get_filtros()
regioes_meta = client.get_regioes()

# Filtro por Região Administrativa
ra_selecionadas = st.sidebar.multiselect(
    "Região Administrativa (RA)",
    options=opcoes.get("regioes", []),
    default=[],
    placeholder="Todas as regiões do DF",
)

# Filtro por Natureza do Crime
crimes_selecionados = st.sidebar.multiselect(
    "Natureza da Ocorrência",
    options=opcoes.get("naturezas", []),
    default=[],
    placeholder="Todos os tipos de crime",
)

# Filtro por Ano
anos_disponiveis = opcoes.get("anos", [2024, 2023, 2022])
anos_selecionados = st.sidebar.multiselect(
    "Ano da Ocorrência",
    options=anos_disponiveis,
    default=anos_disponiveis,
)

# Filtro por Período do Dia
periodos_selecionados = st.sidebar.multiselect(
    "Período do Dia",
    options=opcoes.get("periodos", ["Madrugada", "Manhã", "Tarde", "Noite"]),
    default=opcoes.get("periodos", ["Madrugada", "Manhã", "Tarde", "Noite"]),
)

st.sidebar.divider()

# Configurações do Mapa de Calor
st.sidebar.subheader("🎨 Configurações do Mapa")
tipo_camada = st.sidebar.radio(
    "Tipo de Camada",
    ["Mapa de Calor (Heatmap 2D)", "Agrupamento 3D (Hexágonos)"],
    index=0,
)
raio_calor = st.sidebar.slider("Raio dos Pontos (metros)", 500, 4000, 1800, step=100)
ponderar_severidade = st.sidebar.checkbox("Ponderar por Gravidade do Crime", value=True)

# ==============================================================================
# Consulta de Dados através do ApiClient
# ==============================================================================
pontos_calor = client.get_heatmap(
    regioes=ra_selecionadas if ra_selecionadas else None,
    naturezas=crimes_selecionados if crimes_selecionados else None,
    anos=anos_selecionados if anos_selecionados else None,
    periodos=periodos_selecionados if periodos_selecionados else None,
    ponderar=ponderar_severidade,
)

stats = client.get_stats(
    regioes=ra_selecionadas if ra_selecionadas else None,
    naturezas=crimes_selecionados if crimes_selecionados else None,
    anos=anos_selecionados if anos_selecionados else None,
    periodos=periodos_selecionados if periodos_selecionados else None,
)

# ==============================================================================
# Cabeçalho Principal e Indicadores (KPIs)
# ==============================================================================
st.title("🛡️ Mapa da Segurança Pública - Distrito Federal")
st.markdown("Visualização geoespacial da criminalidade baseada em dados abertos da Secretaria de Segurança Pública (SSP-DF).")

render_metrics(stats)

st.markdown("---")

# ==============================================================================
# Abas de Navegação Principal
# ==============================================================================
tab_mapa, tab_graficos, tab_tabela, tab_api = st.tabs([
    "📍 Mapa Geoespacial",
    "📊 Gráficos & Tendências",
    "📋 Tabela de Ocorrências",
    "🔌 Backend API REST",
])

with tab_mapa:
    regiao_foco = ra_selecionadas[0] if (ra_selecionadas and len(ra_selecionadas) == 1) else None
    render_map(
        pontos_calor=pontos_calor,
        ocorrencias=[],
        regiao_selecionada=regiao_foco,
        regioes_meta=regioes_meta,
        tipo_camada=tipo_camada,
        raio_metros=raio_calor,
    )

with tab_graficos:
    st.subheader("Análise Estatística da Criminalidade")
    render_charts(stats)

with tab_tabela:
    st.subheader("Registros Detalhados de Ocorrências")
    termo = st.text_input("🔍 Buscar por logradouro, crime ou RA:", "")

    ocorrencias = client.get_ocorrencias(
        regioes=ra_selecionadas if ra_selecionadas else None,
        naturezas=crimes_selecionados if crimes_selecionados else None,
        anos=anos_selecionados if anos_selecionados else None,
        periodos=periodos_selecionados if periodos_selecionados else None,
        busca=termo if termo else None,
        limite=600,
    )

    if ocorrencias:
        df_tab = pd.DataFrame(ocorrencias)
        colunas_exibir = [
            c for c in ["id", "regiao_administrativa", "natureza_crime", "data", "hora", "periodo_dia", "logradouro_detalhe", "peso_severidade"]
            if c in df_tab.columns
        ]
        st.dataframe(df_tab[colunas_exibir], use_container_width=True)
        st.caption(f"Mostrando {len(df_tab)} registros correspondentes aos filtros.")

        csv_bytes = df_tab.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Baixar Ocorrências Filtradas (CSV)",
            data=csv_bytes,
            file_name="ocorrencias_df_filtradas.csv",
            mime="text/csv",
        )
    else:
        st.info("Nenhuma ocorrência encontrada com os termos pesquisados.")


with tab_api:
    st.subheader("🔌 Backend API REST (FastAPI)")
    st.markdown("""
    
    - **Servidor**: FastAPI + Uvicorn na porta `8000`.
    - **Documentação Swagger**: Acesse [http://localhost:8000/docs](http://localhost:8000/docs) para testar os endpoints interativamente.
    """)

    st.markdown("#### Endpoints Disponíveis:")
    st.code("""
GET  /api/health       -> Status de integridade e total de registros
GET  /api/regioes      -> Lista de RAs e coordenadas centrais
GET  /api/filtros      -> Opções para filtros (crimes, anos, períodos)
GET  /api/heatmap      -> Matriz [latitude, longitude, peso] para mapa de calor
GET  /api/ocorrencias  -> Listagem detalhada com busca e filtros
GET  /api/stats        -> Indicadores agregados e KPIs
POST /api/consolidar   -> Dispara pipeline de ETL dos arquivos brutos
    """, language="text")

    st.info("💡 **Como iniciar a API**: Execute `python run.py api` ou use `run.bat` (opção 2).")

st.sidebar.divider()
st.sidebar.caption("UCB - Soluções Computacionais (8º Semestre)")

