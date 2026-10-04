"""Testes dos normalizadores do pipeline de carga (db/load_csv.py)."""
import pandas as pd
import pytest

from db.load_csv import (
    limpar_eixo,
    limpar_natureza,
    normalizar_nome_regiao,
    preparar_dataframe,
    resolver_regiao,
    strip_accents,
)


class TestStripAccents:
    def test_remove_acentos_simples(self):
        assert strip_accents("Ceilândia") == "Ceilandia"

    def test_preserva_sem_acento(self):
        assert strip_accents("Gama") == "Gama"

    def test_string_vazia(self):
        assert strip_accents("") == ""


class TestNormalizarNomeRegiao:
    def test_title_case_basico(self):
        assert normalizar_nome_regiao("ceilândia") == "Ceilândia"

    def test_particulas_minusculas(self):
        assert normalizar_nome_regiao("riacho fundo") == "Riacho Fundo"
        assert normalizar_nome_regiao("núcleo de bandeirante") == "Núcleo de Bandeirante"

    def test_colapsa_espacos(self):
        assert normalizar_nome_regiao("Gama    Norte") == "Gama Norte"


class TestResolverRegiao:
    def test_alias_sem_acento(self):
        assert resolver_regiao("ceilandia") == "Ceilândia"

    def test_sufixo_de_redownload(self):
        # o portal repete downloads como 'Arniqueira (4)'
        assert resolver_regiao("Arniqueira (4)") == "Arniqueira"

    def test_grafia_oficial_inalterada(self):
        assert resolver_regiao("Ceilândia") == "Ceilândia"

    def test_separadores_hifen_e_barra(self):
        assert resolver_regiao("scia-estrutural") == "Scia Estrutural" or \
               resolver_regiao("scia-estrutural") == "SCIA/Estrutural"

    def test_desconhecida_cai_no_title_case(self):
        assert resolver_regiao("cidade nova") == "Cidade Nova"


class TestLimparEixo:
    def test_remove_prefixo_numerico(self):
        saida = limpar_eixo("2. C.C.P. -      CRIMES CONTRA O PATRIMÔNIO")
        assert saida == "C.C.P. - CRIMES CONTRA O PATRIMÔNIO"

    def test_total_vira_resumo(self):
        assert limpar_eixo("TOTAL") == "TOTAL (resumo)"

    def test_eixo_limpo_inalterado(self):
        eixo = "C.V.L.I. - CRIMES VIOLENTOS LETAIS INTENCIONAIS"
        assert limpar_eixo(eixo) == eixo


class TestLimparNatureza:
    def test_remove_asteriscos_de_rodape(self):
        assert limpar_natureza("HOMICÍDIO DOLOSO***") == "HOMICÍDIO DOLOSO"

    def test_colapsa_espacos(self):
        assert limpar_natureza("ROUBO   DE   VEÍCULO") == "ROUBO DE VEÍCULO"


class TestPrepararDataframe:
    @staticmethod
    def _csv(tmp_path, linhas):
        colunas = [
            "regiao_administrativa", "codigo_ra_arquivo", "ano",
            "eixo_indicador", "tipo_registro", "natureza",
            "jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez", "total_ano",
        ]
        df = pd.DataFrame(linhas, columns=colunas)
        caminho = tmp_path / "consolidado.csv"
        df.to_csv(caminho, index=False, encoding="utf-8")
        return caminho

    @staticmethod
    def _linha(ra, natureza, ano, tipo, meses):
        return [ra, "09", ano, "TOTAL", tipo, natureza, *meses, sum(meses)]

    def test_deduplicacao_agrega_pelo_maximo(self, tmp_path):
        csv = self._csv(tmp_path, [
            self._linha("Ceilândia", "HOMICÍDIO DOLOSO", 2024, "OCORRENCIA", [5, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
            self._linha("Ceilândia", "HOMICÍDIO DOLOSO", 2024, "OCORRENCIA", [4, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
        ])
        df = preparar_dataframe(csv)
        assert len(df) == 1
        assert df.iloc[0]["jan"] == 5   # máximo entre 5 e 4
        assert df.iloc[0]["fev"] == 6   # máximo entre 3 e 6

    def test_normaliza_regiao_e_tipo(self, tmp_path):
        csv = self._csv(tmp_path, [
            self._linha("ceilandia", "HOMICÍDIO DOLOSO", 2024, "Ocorrência",
                        [1] * 12),
        ])
        df = preparar_dataframe(csv)
        assert df.iloc[0]["regiao_normalizada"] == "Ceilândia"
        assert df.iloc[0]["tipo_registro_normalizado"] == "OCORRENCIA"

    def test_chaves_diferentes_nao_sao_agrupadas(self, tmp_path):
        csv = self._csv(tmp_path, [
            self._linha("Ceilândia", "LATROCÍNIO", 2024, "OCORRENCIA", [2] * 12),
            self._linha("Ceilândia", "LATROCÍNIO", 2023, "OCORRENCIA", [1] * 12),
        ])
        df = preparar_dataframe(csv)
        assert len(df) == 2
