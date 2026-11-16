"""Testes de validação e serialização do RelatorioService (sem banco).

Cobrem as mesmas regras do CHECK em db/auth_schema.sql, verificadas em
RelatorioService._validar antes de tocar no banco — e a serialização de
uma linha de auth.relatorio_salvo em _to_dict (filtros em JSON/dict,
criado_em em datetime/string). Testes que envolvem banco de verdade
(CRUD completo, isolamento entre usuários) estão em
db/relatorio_smoke_test.py, seguindo o mesmo padrão de
db/auth_smoke_test.py.
"""
from datetime import datetime

import pytest

from api.services.relatorio_service import (
    DIMENSOES_VALIDAS,
    TIPOS_GRAFICO_VALIDOS,
    TOP_N_MAX,
    TOP_N_MIN,
    TITULO_MAX,
    RelatorioError,
    RelatorioService,
    _to_dict,
)


class _LinhaFake:
    """Simula uma linha retornada pelo SQLAlchemy (atributos por nome)."""

    def __init__(self, id=1, titulo="Teste", dimensao="por_regiao",
                 tipo_grafico="Barras", top_n=10, filtros=None, criado_em=None):
        self.id = id
        self.titulo = titulo
        self.dimensao = dimensao
        self.tipo_grafico = tipo_grafico
        self.top_n = top_n
        self.filtros = filtros
        self.criado_em = criado_em


class TestValidar:
    def test_combinacao_valida_nao_levanta_erro(self):
        titulo = RelatorioService._validar("Gama - Barras", "por_regiao", "Barras", 10)
        assert titulo == "Gama - Barras"

    def test_titulo_com_espacos_e_normalizado(self):
        titulo = RelatorioService._validar("  Meu relatorio  ", "por_ano", "Linha", 5)
        assert titulo == "Meu relatorio"

    def test_titulo_vazio_rejeitado(self):
        with pytest.raises(RelatorioError) as exc:
            RelatorioService._validar("   ", "por_regiao", "Barras", 10)
        assert exc.value.codigo == "validacao"

    def test_titulo_maior_que_limite_rejeitado(self):
        with pytest.raises(RelatorioError) as exc:
            RelatorioService._validar("x" * (TITULO_MAX + 1), "por_regiao", "Barras", 10)
        assert exc.value.codigo == "validacao"

    def test_titulo_no_limite_maximo_e_aceito(self):
        titulo = RelatorioService._validar("x" * TITULO_MAX, "por_regiao", "Barras", 10)
        assert len(titulo) == TITULO_MAX

    def test_dimensao_invalida_rejeitada(self):
        with pytest.raises(RelatorioError) as exc:
            RelatorioService._validar("Titulo", "por_bairro", "Barras", 10)
        assert exc.value.codigo == "validacao"

    @pytest.mark.parametrize("dimensao", DIMENSOES_VALIDAS)
    def test_todas_dimensoes_validas_sao_aceitas(self, dimensao):
        RelatorioService._validar("Titulo", dimensao, "Barras", 10)

    def test_tipo_grafico_invalido_rejeitado(self):
        with pytest.raises(RelatorioError) as exc:
            RelatorioService._validar("Titulo", "por_regiao", "Radar", 10)
        assert exc.value.codigo == "validacao"

    @pytest.mark.parametrize("tipo", TIPOS_GRAFICO_VALIDOS)
    def test_todos_tipos_de_grafico_validos_sao_aceitos(self, tipo):
        RelatorioService._validar("Titulo", "por_regiao", tipo, 10)

    def test_top_n_abaixo_do_minimo_rejeitado(self):
        with pytest.raises(RelatorioError) as exc:
            RelatorioService._validar("Titulo", "por_regiao", "Barras", TOP_N_MIN - 1)
        assert exc.value.codigo == "validacao"

    def test_top_n_acima_do_maximo_rejeitado(self):
        with pytest.raises(RelatorioError) as exc:
            RelatorioService._validar("Titulo", "por_regiao", "Barras", TOP_N_MAX + 1)
        assert exc.value.codigo == "validacao"

    def test_top_n_nos_limites_e_aceito(self):
        RelatorioService._validar("Titulo", "por_regiao", "Barras", TOP_N_MIN)
        RelatorioService._validar("Titulo", "por_regiao", "Barras", TOP_N_MAX)


class TestToDict:
    def test_filtros_como_string_json_e_decodificado(self):
        linha = _LinhaFake(filtros='{"regioes": ["Gama"]}')
        d = _to_dict(linha)
        assert d["filtros"] == {"regioes": ["Gama"]}

    def test_filtros_none_vira_dict_vazio(self):
        linha = _LinhaFake(filtros=None)
        d = _to_dict(linha)
        assert d["filtros"] == {}

    def test_filtros_ja_como_dict_e_mantido(self):
        linha = _LinhaFake(filtros={"anos": [2024]})
        d = _to_dict(linha)
        assert d["filtros"] == {"anos": [2024]}

    def test_criado_em_datetime_vira_isoformat(self):
        agora = datetime(2026, 11, 16, 10, 0, 0)
        linha = _LinhaFake(criado_em=agora)
        d = _to_dict(linha)
        assert d["criado_em"] == agora.isoformat()

    def test_criado_em_ja_como_string_e_mantido(self):
        linha = _LinhaFake(criado_em="2026-11-16T10:00:00")
        d = _to_dict(linha)
        assert d["criado_em"] == "2026-11-16T10:00:00"

    def test_ids_viram_int(self):
        linha = _LinhaFake(id="7", top_n="10")
        d = _to_dict(linha)
        assert d["id"] == 7 and isinstance(d["id"], int)
        assert d["top_n"] == 10 and isinstance(d["top_n"], int)
