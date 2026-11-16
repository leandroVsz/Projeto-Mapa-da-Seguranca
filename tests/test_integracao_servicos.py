"""Testes de integração com APIs e serviços — seção 4.2.2 do relatório.

Cobre os componentes externos usados pelo projeto:

TI05 — Cliente Streamlit (ApiClient) ↔ API FastAPI rodando em HTTP real
TI06 — Planilhas .xls/.xlsx da SSP-DF ↔ ETL (ingest_crimemap)
TI07 — GeoJSON público das RAs (geodata-distrito-federal-brasil) ↔ carga
TI08 — Gráficos ↔ exportação em CSV/PDF (pandas + matplotlib)

Os testes que dependem de rede são pulados se o recurso não responder;
os demais usam os arquivos reais versionados no projeto.
"""
import io
import json
import shutil
import socket
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
import requests
import uvicorn

from api.server import app
from api.services.data_service import DataService
from api.services.ingest_crimemap import consolidar
from app.api_client import ApiClient
from app.components.chart_export import gerar_csv, gerar_pdf, nome_arquivo
from db.load_csv import CSV_PADRAO, GEOJSON_PATH, extrair_poligonos_por_nome, preparar_dataframe

pytestmark = pytest.mark.integracao_servicos

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# TI05 — ApiClient (Streamlit) ↔ API FastAPI via HTTP real
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api_url():
    """Sobe a API em uma porta livre e derruba ao final do módulo."""
    porta = _porta_livre()
    config = uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="error")
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()

    limite = time.time() + 30
    while not servidor.started and time.time() < limite and thread.is_alive():
        time.sleep(0.1)
    if not servidor.started:  # pragma: no cover - depende do ambiente
        pytest.fail("A API local não iniciou dentro de 30s")

    yield f"http://127.0.0.1:{porta}"

    servidor.should_exit = True
    thread.join(timeout=10)


class TestTI05ClienteApi:
    def test_health_check_do_cliente(self, api_url):
        cliente = ApiClient(base_url=api_url)
        status = cliente.check_health()
        assert status["online"] is True
        assert status["data"]["status"] == "healthy"

    def test_contrato_dos_endpoints_consumidos_pelo_painel(self, api_url):
        cliente = ApiClient(base_url=api_url)

        filtros = cliente.get_filtros()
        assert {"regioes", "naturezas", "eixos", "anos"}.issubset(filtros)
        assert len(filtros["regioes"]) > 0

        stats = cliente.get_stats()
        assert stats["total_ocorrencias"] > 0
        assert len(stats["por_mes"]) > 0

        coropleto = cliente.get_coropleto()
        assert len(coropleto["regioes"]) > 0
        assert len(coropleto["top_naturezas"]) > 0

        pontos = cliente.get_heatmap()
        assert len(pontos) > 0 and len(pontos[0]) == 3

        linhas = cliente.get_ocorrencias(limite=10)
        assert 0 < len(linhas) <= 10
        assert {"regiao_administrativa", "natureza_crime", "quantidade"} <= set(linhas[0])

        detalhe = cliente.get_detalhe_regiao(filtros["regioes"][0])
        assert detalhe["regiao"] == filtros["regioes"][0]

    def test_mesmo_contrato_do_modo_offline(self, api_url):
        """O painel não quebra se a API cair: o fallback devolve o mesmo schema."""
        online = ApiClient(base_url=api_url)
        offline = ApiClient(base_url=f"http://127.0.0.1:{_porta_livre()}")

        stats_online = online.get_stats()
        stats_offline = offline.get_stats()
        assert set(stats_online) == set(stats_offline)
        assert stats_online["total_ocorrencias"] == stats_offline["total_ocorrencias"]

        assert set(online.get_filtros()) == set(offline.get_filtros())


# ---------------------------------------------------------------------------
# TI06 — Planilhas da SSP-DF ↔ ETL (consolidação)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def arquivos_reais(tmp_path_factory):
    """Amostra real do portal: DF, Ceilândia e Gama (2024)."""
    pasta = tmp_path_factory.mktemp("raw_sspdf")
    for nome in (
        "00_DISTRITO-FEDERAL_1_2024.xlsx",
        "09_CEILANDIA_2024.xlsx",
        "02_GAMA_2024.xlsx",
    ):
        origem = RAW_DIR / nome
        assert origem.exists(), f"planilha de amostra ausente: {nome}"
        shutil.copy2(origem, pasta / nome)
    return pasta


class TestTI06EtlPlanilhas:
    def test_consolidacao_das_planilhas_reais(self, arquivos_reais, tmp_path):
        saida = tmp_path / "consolidado.csv"
        resumo = consolidar(arquivos_reais, saida)

        assert resumo["status"] == "ok"
        assert resumo["linhas"] > 0
        assert resumo["regioes"] >= 2
        # o ano válido é o da aba interna da planilha (pode diferir do nome)
        assert resumo["anos"]
        assert all(2014 <= ano <= 2030 for ano in resumo["anos"])

        df = pd.read_csv(saida, encoding="utf-8-sig")
        esperadas = {
            "regiao_administrativa", "codigo_ra_arquivo", "ano",
            "eixo_indicador", "tipo_registro", "natureza", "total_ano",
            *MESES,
        }
        assert esperadas.issubset(df.columns)
        assert (df["total_ano"] >= 0).all()

        # o parser preserva os 12 meses e o total declarado pela planilha
        consistentes = (df[MESES].sum(axis=1) - df["total_ano"]).abs() <= 1
        assert consistentes.mean() > 0.95

    def test_consolidacao_e_idempotente(self, arquivos_reais, tmp_path):
        primeira = tmp_path / "a.csv"
        segunda = tmp_path / "b.csv"
        r1 = consolidar(arquivos_reais, primeira)
        r2 = consolidar(arquivos_reais, segunda)

        assert r1["linhas"] == r2["linhas"]
        assert r1["anos"] == r2["anos"]
        assert pd.read_csv(primeira, encoding="utf-8-sig").equals(
            pd.read_csv(segunda, encoding="utf-8-sig")
        )

    def test_csv_consolidado_alimenta_a_normalizacao_da_carga(self, arquivos_reais, tmp_path):
        saida = tmp_path / "consolidado.csv"
        consolidar(arquivos_reais, saida)

        preparado = preparar_dataframe(saida)
        assert "regiao_normalizada" in preparado.columns
        assert "natureza_limpa" in preparado.columns
        assert "tipo_registro_normalizado" in preparado.columns
        regioes = set(preparado["regiao_normalizada"])
        assert {"Ceilândia", "Gama"}.issubset(regioes)
        assert preparado["ano"].nunique() >= 1

    def test_consolidado_versionado_tem_o_mesmo_layout(self):
        assert CSV_PADRAO.exists()
        df = pd.read_csv(CSV_PADRAO, encoding="utf-8-sig")
        assert len(df) > 5000  # mesma base usada pela carga do banco
        assert {"regiao_administrativa", "natureza", "total_ano", *MESES} <= set(df.columns)


# ---------------------------------------------------------------------------
# TI07 — GeoJSON público das RAs ↔ carga PostGIS
# ---------------------------------------------------------------------------
class TestTI07GeoJson:
    def test_arquivo_geojson_e_uma_colecao_de_feicoes(self):
        if not GEOJSON_PATH.exists():  # pragma: no cover - cache regenerável
            pytest.skip("GeoJSON ainda não baixado (python -m db.load_csv)")
        dados = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
        assert dados["type"] == "FeatureCollection"
        assert len(dados["features"]) > 30

    def test_mapeamento_das_sub_regioes_para_as_ras_oficiais(self):
        if not GEOJSON_PATH.exists():  # pragma: no cover
            pytest.skip("GeoJSON ainda não baixado")
        dados = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
        poligonos = extrair_poligonos_por_nome(dados)

        assert len(poligonos) >= 25
        assert "Ceilândia" in poligonos
        assert "Plano Piloto" in poligonos or "Brasília" in poligonos

        geometria = poligonos["Ceilândia"]["polygon"]
        assert geometria.is_valid
        assert geometria.area > 0
        centro = geometria.centroid
        assert -16.2 <= centro.y <= -15.4
        assert -48.4 <= centro.x <= -47.2

    def test_fonte_publica_responde(self):
        """A carga baixa os contornos deste repositório público."""
        url = (
            "https://raw.githubusercontent.com/caefleury/"
            "geodata-distrito-federal-brasil/main/geojson-data/01-gama.geo.json"
        )
        try:
            resposta = requests.get(url, timeout=15)
        except requests.RequestException as erro:  # pragma: no cover - rede
            pytest.skip(f"Fonte GeoJSON indisponível: {type(erro).__name__}")

        assert resposta.status_code == 200
        features = resposta.json().get("features", [])
        assert features


# ---------------------------------------------------------------------------
# TI08 — Gráficos ↔ exportação CSV/PDF
# ---------------------------------------------------------------------------
class TestTI08Exportacao:
    @pytest.fixture
    def serie(self):
        return pd.DataFrame({
            "Categoria": ["jan", "fev", "mar", "abr"],
            "Ocorrências": [10234, 9876, 11045, 7654],
        })

    def test_csv_exportado_compativel_com_excel_brasileiro(self, serie):
        conteudo = gerar_csv(serie)
        assert conteudo.startswith(b"\xef\xbb\xbf")
        assert b";" in conteudo.splitlines()[0]

        lido = pd.read_csv(io.BytesIO(conteudo), sep=";")
        assert lido["Ocorrências"].sum() == serie["Ocorrências"].sum()

    def test_pdf_gerado_com_duas_paginas(self, serie):
        conteudo = gerar_pdf(serie, "Linha", "Evolução mensal")
        assert conteudo.startswith(b"%PDF")
        # gráfico + tabela de dados
        assert conteudo.count(b"/Type /Page") >= 2
        assert len(conteudo) > 2000

    def test_nome_do_arquivo_e_seguro(self):
        nome = nome_arquivo("Evolução mensal / DF", "Barras", "pdf")
        assert nome == "evolucao_mensal_df_barras.pdf"
        assert " " not in nome and "/" not in nome

    def test_exportacao_usa_os_dados_do_painel(self, serie, tmp_path):
        """Fluxo completo: stats → DataFrame → CSV em disco."""
        stats = DataService().get_estatisticas(anos=[2024])
        assert stats["total_ocorrencias"] > 0

        df = pd.DataFrame(
            list(stats["por_regiao"].items()), columns=["Categoria", "Ocorrências"]
        ).head(10)
        destino = tmp_path / nome_arquivo("Top regiões", "Barras", "csv")
        destino.write_bytes(gerar_csv(df))

        lido = pd.read_csv(destino, sep=";")
        assert len(lido) == len(df)
        assert lido["Ocorrências"].sum() <= stats["total_ocorrencias"]
