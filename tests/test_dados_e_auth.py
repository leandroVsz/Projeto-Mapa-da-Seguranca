"""Testes do gerador da base de demonstração e da validação de senha."""
import json
from pathlib import Path

import pytest

from api.services.data_ingestion import JSON_RAS_PATH, _pesos_por_populacao, gerar_dados_amostra
from api.services.auth_service import validar_forca_senha


def _regioes_do_metadado():
    with open(JSON_RAS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["regioes"]

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


class TestPesosPorPopulacao:
    def test_peso_e_fatia_da_populacao_total_do_df(self):
        # o peso é a fatia da RA na população de TODAS as RAs do metadado,
        # não da lista passada (por isso a soma fica < 1 com poucas RAs)
        pesos = _pesos_por_populacao(["Ceilândia", "Gama", "Plano Piloto"])
        total = _pesos_por_populacao(
            [r["nome"] for r in _regioes_do_metadado()]
        )
        assert sum(total.values()) == pytest.approx(1.0)
        for ra, peso in pesos.items():
            assert peso == pytest.approx(total[ra])

    def test_ra_ausente_no_metadado_recebe_zero(self):
        pesos = _pesos_por_populacao(["Ceilândia", "RA Inexistente"])
        assert pesos["RA Inexistente"] == 0.0
        assert pesos["Ceilândia"] > 0

    def test_ceilandia_pesa_mais_que_gama(self):
        # Ceilândia tem ~432 mil hab. no metadado; Gama ~137 mil
        pesos = _pesos_por_populacao(["Ceilândia", "Gama"])
        assert pesos["Ceilândia"] > pesos["Gama"]


class TestGerarDadosAmostra:
    def test_esquema_igual_ao_csv_real(self, tmp_path):
        saida = tmp_path / "demo.csv"
        df = gerar_dados_amostra(caminho_saida=saida, ano_inicio=2024, ano_fim=2024)
        esperadas = {
            "regiao_administrativa", "codigo_ra_arquivo", "ano",
            "eixo_indicador", "tipo_registro", "natureza", "total_ano",
        } | set(MESES)
        assert esperadas.issubset(df.columns)
        assert (df["ano"] == 2024).all()

    def test_sem_campos_da_base_simulada_antiga(self, tmp_path):
        # período do dia, peso de severidade e lat/long não existem na base real
        df = gerar_dados_amostra(
            caminho_saida=tmp_path / "demo.csv", ano_inicio=2024, ano_fim=2024,
        )
        proibidas = {
            "latitude", "longitude", "peso_severidade",
            "periodo_dia", "hora", "data", "logradouro_detalhe",
        }
        assert proibidas.isdisjoint(df.columns)

    def test_total_ano_consistente_com_meses(self, tmp_path):
        df = gerar_dados_amostra(
            caminho_saida=tmp_path / "demo.csv", ano_inicio=2023, ano_fim=2023,
        )
        soma_meses = df[MESES].sum(axis=1)
        assert (soma_meses == df["total_ano"]).all()


class TestValidarForcaSenha:
    def test_senha_forte_sem_problemas(self):
        assert validar_forca_senha("Senha@Forte123") == []

    def test_senha_curta(self):
        problemas = validar_forca_senha("Ab1")
        assert any("8 caracteres" in p for p in problemas)

    def test_sem_maiuscula(self):
        problemas = validar_forca_senha("senhafraca123")
        assert any("maiúscula" in p for p in problemas)

    def test_sem_numero(self):
        problemas = validar_forca_senha("SenhaForteSemNumero")
        assert any("número" in p for p in problemas)

    def test_acumula_problemas(self):
        problemas = validar_forca_senha("abc")
        assert len(problemas) >= 3
