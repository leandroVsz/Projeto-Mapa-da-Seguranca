"""
Aplicação Principal Streamlit - Mapa da Segurança do Distrito Federal

Painel geoespacial e analítico de ocorrências criminais no DF.
Atua como cliente da API REST (FastAPI) com suporte a fallback local.
"""

from pathlib import Path
import os
import sys
import streamlit as st
import pandas as pd
import os as _os_modulo

EMBED_API = _os_modulo.getenv("EMBED_API", "false").strip().lower() in ("1", "true", "yes", "on")

# Inclusão da raiz no sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api_client import ApiClient
from app.auth_ui import (
    render_auth_tab,
    render_login_gate,
    init_auth_state,
    is_logado,
    usuario_logado,
    logout,
)
from app.components.metrics import render_metrics
from app.components.map_view import render_map, ESTILOS_MAPA
from app.components.charts import render_charts
from api.embedded import iniciar_api_embutida

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

# Deploy em nuvem (Streamlit Cloud): sobe a API FastAPI no mesmo processo.
if EMBED_API:
    iniciar_api_embutida()

client = get_api_client()


def _selecionar_regiao(nome_ra: str):
    """Callback do clique no mapa: guarda a RA clicada para o painel de detalhe."""
    st.session_state["ra_detalhe"] = nome_ra

# Gate opcional de login via AUTH_REQUIRED=true no .env
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").strip().lower() in ("1", "true", "yes", "on")
init_auth_state()
if not render_login_gate(AUTH_REQUIRED):
    st.stop()

# Barra lateral: filtros e configurações do mapa
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

# Sessão do usuário (login/registro na aba 'Conta & Acesso')
if is_logado():
    u = usuario_logado()
    st.sidebar.success(f"👤 **{u['nome']}**\n\n{u['email']}")
    if st.sidebar.button("🚪 Sair da conta", use_container_width=True):
        logout()
        st.rerun()
else:
    st.sidebar.info("👤 **Visitante**\n\nEntre pela aba **Conta & Acesso** abaixo.")

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

# Filtro por Eixo Indicador (macro-categoria SSP-DF)
eixos_disponiveis = opcoes.get("eixos", [])
eixos_selecionados = st.sidebar.multiselect(
    "Eixo Indicador",
    options=eixos_disponiveis,
    default=[],
    placeholder="Todos os eixos (C.V.L.I., C.C.P., ...)",
    disabled=not eixos_disponiveis,
    help=("Disponível apenas com o banco PostgreSQL conectado."
          if not eixos_disponiveis else None),
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

st.sidebar.divider()

# Configurações do Mapa
st.sidebar.subheader("🎨 Configurações do Mapa")
tem_contornos = any(r.get("contorno") for r in (regioes_meta or []))
opcoes_camada = (
    ["Coropleto por RA", "Mapa de Calor (Heatmap 2D)"]
    if tem_contornos
    else ["Mapa de Calor (Heatmap 2D)"]
)
tipo_camada = st.sidebar.radio("Tipo de Camada", opcoes_camada, index=0)
estilo_escolhido = st.sidebar.select_slider(
    "Estilo do Mapa Base",
    options=list(ESTILOS_MAPA.keys()),
    value="Claro",
)

pontos_calor = client.get_heatmap(
    regioes=ra_selecionadas if ra_selecionadas else None,
    naturezas=crimes_selecionados if crimes_selecionados else None,
    eixos=eixos_selecionados if eixos_selecionados else None,
    anos=anos_selecionados if anos_selecionados else None,
)

coropleto = client.get_coropleto(
    regioes=ra_selecionadas if ra_selecionadas else None,
    naturezas=crimes_selecionados if crimes_selecionados else None,
    eixos=eixos_selecionados if eixos_selecionados else None,
    anos=anos_selecionados if anos_selecionados else None,
)

stats = client.get_stats(
    regioes=ra_selecionadas if ra_selecionadas else None,
    naturezas=crimes_selecionados if crimes_selecionados else None,
    eixos=eixos_selecionados if eixos_selecionados else None,
    anos=anos_selecionados if anos_selecionados else None,
)

st.title("🛡️ Mapa da Segurança Pública - Distrito Federal")
st.markdown("Visualização geoespacial da criminalidade baseada em dados abertos da Secretaria de Segurança Pública (SSP-DF).")

render_metrics(stats)

st.markdown("---")

tab_mapa, tab_graficos, tab_tabela, tab_api, tab_conta = st.tabs([
    "📍 Mapa Geoespacial",
    "📊 Gráficos & Tendências",
    "📋 Tabela de Ocorrências",
    "🔌 Backend API REST",
    "👤 Conta & Acesso",
])

with tab_mapa:
    regiao_foco = ra_selecionadas[0] if (ra_selecionadas and len(ra_selecionadas) == 1) else None
    render_map(
        pontos_calor=pontos_calor,
        ocorrencias=[],
        coropleto=coropleto.get("regioes", []),
        regioes_geo=regioes_meta,
        regiao_selecionada=regiao_foco,
        regioes_meta=regioes_meta,
        tipo_camada=tipo_camada,
        estilo_mapa=ESTILOS_MAPA.get(estilo_escolhido),
        top_naturezas=coropleto.get("top_naturezas", {}),
        detalhe_callback=_selecionar_regiao,
    )

    # Painel de detalhe da RA clicada no mapa
    ra_clicada = st.session_state.get("ra_detalhe")
    if ra_clicada:
        detalhe = client.get_detalhe_regiao(
            regiao=ra_clicada,
            naturezas=crimes_selecionados if crimes_selecionados else None,
            eixos=eixos_selecionados if eixos_selecionados else None,
            anos=anos_selecionados if anos_selecionados else None,
        )
        with st.container(border=True):
            col_tit, col_fechar = st.columns([0.85, 0.15])
            col_tit.subheader(f"📍 {ra_clicada}")
            if col_fechar.button("✕ Fechar", key="fechar-detalhe-ra", use_container_width=True):
                del st.session_state["ra_detalhe"]
                st.rerun()

            total_ra = int(detalhe.get("total_ocorrencias", 0))
            total_geral = int(stats.get("total_ocorrencias", 0))
            pct = (100.0 * total_ra / total_geral) if total_geral else 0.0
            por_nat = detalhe.get("por_natureza", {})

            k1, k2, k3 = st.columns(3)
            k1.metric("Ocorrências (filtros atuais)", f"{total_ra:,}".replace(",", "."))
            k2.metric("Participação no total do DF", f"{pct:.1f}%".replace(".", ","))
            k3.metric("Naturezas com registro", str(len(por_nat)))

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("**Crimes por natureza (top 10)**")
                if por_nat:
                    df_nat = pd.DataFrame(
                        [{"Natureza": k, "Ocorrências": v} for k, v in por_nat.items()]
                    ).head(10)
                    st.bar_chart(df_nat.set_index("Natureza"))
                else:
                    st.info("Sem registros para esta RA nos filtros atuais.")
            with col_g2:
                por_ano = detalhe.get("por_ano", {})
                st.markdown("**Ocorrências por ano**")
                if por_ano:
                    df_ano = pd.DataFrame(
                        [{"Ano": int(k), "Ocorrências": v} for k, v in por_ano.items()]
                    ).sort_values("Ano")
                    st.bar_chart(df_ano.set_index("Ano"))
                else:
                    st.info("Sem registros por ano para esta RA.")

            st.caption(
                f"Valores de **{ra_clicada}** considerando os filtros atuais da barra lateral "
                "(naturezas, eixos e anos). Clique em outra RA para trocar o detalhe."
            )

with tab_graficos:
    st.subheader("Análise Estatística da Criminalidade")
    render_charts(stats)

with tab_tabela:
    st.subheader("Registros Detalhados de Ocorrências")
    termo = st.text_input("🔍 Buscar por crime ou RA:", "")

    ocorrencias = client.get_ocorrencias(
        regioes=ra_selecionadas if ra_selecionadas else None,
        naturezas=crimes_selecionados if crimes_selecionados else None,
        eixos=eixos_selecionados if eixos_selecionados else None,
        anos=anos_selecionados if anos_selecionados else None,
        busca=termo if termo else None,
        limite=600,
    )

    if ocorrencias:
        df_tab = pd.DataFrame(ocorrencias)
        colunas_exibir = [
            c for c in ["regiao_administrativa", "natureza_crime", "eixo_indicador", "ano", "mes", "quantidade", "tipo_registro"]
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
    st.markdown(
        "A API roda na porta `8000` (ou embutida no app com EMBED_API=true). "
        "Documentação interativa em [http://localhost:8000/docs](http://localhost:8000/docs)."
    )
    st.code("""
GET  /api/health         -> Status do servidor e do banco (com fallback)
GET  /api/regioes        -> RAs com contornos GeoJSON
GET  /api/filtros        -> Opções dos filtros (RAs, crimes, eixos, anos)
GET  /api/heatmap        -> Ponto por RA [lat, lon, peso]
GET  /api/coropleto      -> Intensidade por RA + top naturezas (tooltip)
GET  /api/detalhe-regiao -> KPIs e distribuições de uma RA
GET  /api/ocorrencias    -> Listagem agregada RA/crime/ano/mês com busca
GET  /api/stats          -> Indicadores agregados e KPIs
POST /api/consolidar     -> Consolida as planilhas SSP-DF (ETL)
POST /api/carga-db       -> Carrega o CSV consolidado no PostgreSQL

--- Autenticação (header X-Auth-Token nas rotas protegidas) ---
POST /api/auth/registro          -> Cria conta e devolve token
POST /api/auth/login             -> Autentica (e-mail, senha, lembrar)
POST /api/auth/logout            -> Encerra a sessão
GET  /api/auth/eu                -> Dados do usuário autenticado
POST /api/auth/trocar-senha      -> Troca a própria senha
POST /api/auth/reset/solicitar   -> Gera token de redefinição
POST /api/auth/reset/confirmar   -> Redefine a senha com o token
GET  /api/auth/health            -> Status do subsistema de autenticação
    """, language="text")

with tab_conta:
    render_auth_tab()

st.sidebar.divider()
st.sidebar.caption("Dados mais recente: 08/2026 | Fonte: SSP-DF (Secretaria de Segurança Pública do Distrito Federal) | Projeto acadêmico UCB - Soluções Computacionais (8º Semestre)")

