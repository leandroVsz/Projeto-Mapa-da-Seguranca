"""Testes do serviço de dados fallback (api/services/data_service.py).

Usa um CSV pequeno em vez do consolidado real: o objetivo é testar a
lógica do serviço (derretimento, filtros, agregações), não os dados.
"""
import pandas as pd
import pytest

from api.services import data_service as ds_mod
from api.services.data_service import DataService, _derreter_para_longo

COLUNAS = [
    "regiao_administrativa", "codigo_ra_arquivo", "ano",
    "eixo_indicador", "tipo_registro", "natureza",
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez", "total_ano",
]


def _linha(ra, natureza, ano, tipo, eixo, meses):
    return [ra, None, ano, eixo, tipo, natureza, *meses, sum(meses)]


@pytest.fixture
def csv_pequeno(tmp_path):
    """CSV no formato do consolidado, colocado em processed/ocorrencias_df_master.csv
    (prioridade máxima na busca do DataService) com uma pasta de dados isolada."""
    linhas = [
        _linha("Ceilândia", "HOMICÍDIO DOLOSO", 2024, "OCORRENCIA", "C.V.L.I.", [3, 1] + [0] * 10),
        _linha("Ceilândia", "LATROCÍNIO", 2024, "OCORRENCIA", "C.V.L.I.", [1, 0] + [0] * 10),
        _linha("Gama", "ROUBO DE VEÍCULO", 2024, "OCORRENCIA", "C.C.P.", [4, 4] + [0] * 10),
        _linha("Ceilândia", "HOMICÍDIO DOLOSO", 2023, "OCORRENCIA", "C.V.L.I.", [2, 2] + [0] * 10),
        _linha("Ceilândia", "HOMICÍDIO DOLOSO", 2024, "VITIMA", "C.V.L.I.", [1, 1] + [0] * 10),
    ]
    processed = tmp_path / "processed"
    processed.mkdir()
    caminho = processed / "ocorrencias_df_master.csv"
    pd.DataFrame(linhas, columns=COLUNAS).to_csv(caminho, index=False, encoding="utf-8")
    svc = DataService(data_dir=tmp_path)
    return svc


class TestDerreterParaLongo:
    def test_uma_linha_por_mes(self, csv_pequeno):
        longo = csv_pequeno._longo()
        # 5 linhas do pivô x 12 meses
        assert len(longo) == 5 * 12
        colunas = {"regiao_administrativa", "natureza", "ano",
                   "tipo_registro", "mes", "quantidade"}
        assert colunas.issubset(longo.columns)

    def test_soma_preservada_apos_derretimento(self, csv_pequeno):
        longo = csv_pequeno._longo()
        pivo = csv_pequeno.carregar_dados()
        assert int(longo["quantidade"].sum()) == int(pivo["total_ano"].sum())


class TestFiltrar:
    def test_filtra_por_ano(self, csv_pequeno):
        df = csv_pequeno.filtrar(anos=[2023])
        assert set(df["ano"].unique()) == {2023}

    def test_filtra_por_tipo_registro(self, csv_pequeno):
        df = csv_pequeno.filtrar(tipo_registro="VITIMA")
        assert set(df["tipo_registro"].unique()) == {"VITIMA"}

    def test_filtra_por_regiao(self, csv_pequeno):
        df = csv_pequeno.filtrar(regioes=["Gama"])
        assert set(df["regiao_administrativa"].unique()) == {"Gama"}


class TestConsultas:
    def test_coropleto_soma_por_ra(self, csv_pequeno):
        dados = csv_pequeno.get_coropleto(anos=[2024])
        por_nome = {d["nome"]: d["total"] for d in dados}
        assert por_nome["Ceilândia"] == 5   # 3+1 homicídio + 1 latrocínio
        assert por_nome["Gama"] == 8        # 4+4 roubo

    def test_detalhe_regiao(self, csv_pequeno):
        det = csv_pequeno.get_detalhe_regiao("Ceilândia", anos=[2024])
        assert det["total_ocorrencias"] == 5
        assert det["por_natureza"]["HOMICÍDIO DOLOSO"] == 4
        assert det["por_ano"] == {2024: 5}

    def test_estatisticas(self, csv_pequeno):
        stats = csv_pequeno.get_estatisticas(anos=[2024])
        assert stats["total_ocorrencias"] == 13
        assert stats["ra_mais_afetada"] == "Gama"  # 8 ocorrências vs 5 de Ceilândia
        assert stats["crime_mais_frequente"] == "ROUBO DE VEÍCULO"

    def test_top_naturezas_ordenado(self, csv_pequeno):
        top = csv_pequeno.get_top_naturezas(anos=[2024])
        ceil = top["Ceilândia"]
        assert ceil[0]["natureza"] == "HOMICÍDIO DOLOSO"
        assert ceil[0]["total"] == 4

    def test_filtro_sem_resultado(self, csv_pequeno):
        stats = csv_pequeno.get_estatisticas(anos=[1999])
        assert stats["total_ocorrencias"] == 0
        assert stats["ra_mais_afetada"] == "N/A"
