"""Testes do parser do ETL das planilhas da SSP-DF (ingest_crimemap.py).

As fixtures reproduzem o layout real das planilhas: células de título nas
primeiras linhas, âncora 'EIXOS INDICADORES', cabeçalho
EIXO / NATUREZA / TOTAL / <ano>, meses nas colunas seguintes e linhas de
subtotal 'TOTAL' misturadas com as de detalhe.
"""
import pandas as pd
import pytest

from api.services.ingest_crimemap import (
    ParseWarning,
    extract_year,
    find_cell,
    parse_sheet,
)

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


def _planilha_ssp(df_com_linhas, ano=2024, com_tipo=False):
    """Monta um DataFrame no layout das planilhas da SSP-DF.
    Colunas: 0=eixo, 1=natureza, 2=TOTAL, 3..14=meses."""
    n_cols = 3 + 12
    grade = [[None] * n_cols for _ in range(10)]
    grade[0][0] = "GOVERNO DO DISTRITO FEDERAL"
    grade[1][0] = "RA IX - CEILÂNDIA"
    grade[2][0] = "Balanço Criminal"
    grade[4][0] = "EIXOS INDICADORES"
    grade[4][1] = "NATUREZA"
    grade[4][2] = "TOTAL"
    grade[4][3] = ano
    for i, (eixo, natureza, meses) in enumerate(df_com_linhas, start=6):
        grade[i][0] = eixo
        grade[i][1] = natureza
        grade[i][2] = sum(meses)  # TOTAL
        for j, v in enumerate(meses):
            grade[i][3 + j] = v
    grade[9][0] = "TOTAL GERAL"
    return pd.DataFrame(grade)


class TestFindCell:
    def test_localiza_ancora(self):
        df = _planilha_ssp([])
        assert find_cell(df, "EIXOS INDICADORES") == (4, 0)

    def test_nao_encontra_retorna_none(self):
        df = pd.DataFrame([["nada aqui"]])
        assert find_cell(df, "EIXOS INDICADORES") is None


class TestExtractYear:
    def test_ano_direto_no_cabecalho(self):
        df = _planilha_ssp([], ano=2024)
        linha, _ = find_cell(df, "EIXOS INDICADORES")
        assert extract_year(df, linha, 3, "aba") == 2024

    def test_ano_do_nome_da_aba_como_fallback(self):
        df = pd.DataFrame({0: ["EIXOS INDICADORES", "NATUREZA"], 1: [None, None]})
        with pytest.raises(ParseWarning):
            extract_year(df, 0, 1, "sem-ano")
        df2 = pd.DataFrame({0: ["EIXOS INDICADORES", None], 1: [None, None]})
        assert extract_year(df2, 0, 1, "PPV (mensal)2019") == 2019


class TestParseSheet:
    def test_extrai_linhas_de_detalhe(self):
        df = _planilha_ssp([
            ("C.V.L.I.", "HOMICÍDIO DOLOSO", [2, 1] + [0] * 10),
            ("C.C.P.", "ROUBO DE VEÍCULO", [10, 5] + [0] * 10),
        ])
        saida = parse_sheet(df, "09_CEILANDIA_2024.xlsx", "PPV (mensal)2024")
        assert len(saida) == 2
        linha = saida[saida["natureza"] == "HOMICÍDIO DOLOSO"].iloc[0]
        assert linha["regiao_administrativa"] == "Ceilândia"
        assert linha["ano"] == 2024
        assert linha["jan"] == 2
        assert linha["total_ano"] == 3
        assert linha["codigo_ra_arquivo"] == "09"

    def test_preenche_celula_mergulhada_do_eixo(self):
        # segunda linha herda o eixo da primeira (célula mesclada no Excel)
        df = _planilha_ssp([
            ("C.V.L.I.", "HOMICÍDIO DOLOSO", [1] + [0] * 11),
            (None, "LATROCÍNIO", [1] + [0] * 11),
        ])
        saida = parse_sheet(df, "09_CEILANDIA_2024.xlsx", "aba")
        assert (saida["eixo_indicador"] == "C.V.L.I.").all()

    def test_descarta_linha_de_subtotal(self):
        df = _planilha_ssp([
            ("1.TOTAL C.V.L.I.", None, [9] + [0] * 11),
            ("C.V.L.I.", "HOMICÍDIO DOLOSO", [2] + [0] * 11),
        ])
        saida = parse_sheet(df, "arquivo.xlsx", "aba")
        assert len(saida) == 1
        assert saida.iloc[0]["natureza"] == "HOMICÍDIO DOLOSO"

    def test_arquivo_sem_ancora_levanta_erro(self):
        df = pd.DataFrame([[None] * 16])
        with pytest.raises(ParseWarning):
            parse_sheet(df, "arquivo.xlsx", "aba")

    def test_sem_linhas_de_detalhe_levanta_erro(self):
        # só linha de rodapé (TOTAL na coluna do eixo) -> nada aproveitável
        df = _planilha_ssp([
            ("1.TOTAL C.V.L.I.", None, [9] + [0] * 11),
        ])
        with pytest.raises(ParseWarning):
            parse_sheet(df, "arquivo.xlsx", "aba")
