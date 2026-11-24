# pyright: basic
"""Testes do requisito 4 — consulta da região por endereço, CEP ou geolocalização.

Serviços externos (ViaCEP e Nominatim) são simulados: os testes são herméticos
e não dependem de rede. O banco é o SQLite dummy do conftest, então o ponto →
RA exercita os fallbacks (GeoJSON local e centroide mais próximo).
"""
import json

import pytest
import requests
from fastapi.testclient import TestClient

from api.server import app
from api.services import localizacao_service as svc
from app.api_client import ApiClient

PLANO_PILOTO = (-15.7942, -47.8822)
CEILANDIA = (-15.8202, -48.1105)


class _Resp:
    def __init__(self, dados, status=200):
        self._dados, self.status_code = dados, status

    def json(self):
        return self._dados

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


@pytest.fixture
def web(monkeypatch):
    """Simula ViaCEP e Nominatim; devolve o dicionário de respostas editáveis."""
    estado = {
        "viacep": {"logradouro": "Quadra CNB 12", "bairro": "Taguatinga Norte",
                   "localidade": "Brasília", "uf": "DF"},
        "nominatim": [{"lat": "-15.8335", "lon": "-48.0567", "display_name": "CNB 12, Taguatinga"}],
        "nominatim_seq": [],        # respostas consumidas em ordem, uma por chamada
        "chamadas_nominatim": 0,
        "cair": False,
    }

    def fake_get(url, **kw):
        if estado["cair"]:
            raise requests.ConnectionError("sem rede")
        if "viacep" in url:
            return _Resp(estado["viacep"])
        estado["chamadas_nominatim"] += 1
        if estado["nominatim_seq"]:
            return _Resp(estado["nominatim_seq"].pop(0))
        return _Resp(estado["nominatim"])

    monkeypatch.setattr(svc.requests, "get", fake_get)
    monkeypatch.setattr(svc, "PAUSA_ENTRE_CHAMADAS", 0)
    return estado


@pytest.fixture
def cliente():
    return TestClient(app)


class TestValidacoes:
    @pytest.mark.parametrize("cep", ["70040-010", "70040010", " 70.040-010 "])
    def test_cep_valido_remove_mascara(self, cep):
        assert svc.normalizar_cep(cep) == "70040010"

    @pytest.mark.parametrize("cep", ["", "123", "abcdefgh", "7004001"])
    def test_cep_invalido(self, cep):
        with pytest.raises(svc.LocalizacaoError):
            svc.normalizar_cep(cep)

    def test_limites_do_df(self):
        assert svc.dentro_do_df(*PLANO_PILOTO)
        assert not svc.dentro_do_df(-23.55, -46.63)  # São Paulo


class TestPontoParaRegiao:
    def test_centroide_mais_proximo_sem_banco(self):
        assert svc.regiao_por_coordenadas(*PLANO_PILOTO) == ("Plano Piloto", "centroide_mais_proximo")
        assert svc.regiao_por_coordenadas(*CEILANDIA)[0] == "Ceilândia"

    def test_fora_do_df(self):
        with pytest.raises(svc.LocalizacaoError) as e:
            svc.regiao_por_coordenadas(-23.55, -46.63)
        assert e.value.status == 422

    def test_geojson_local_tem_prioridade_sobre_centroide(self, tmp_path, monkeypatch):
        # Quadrado em volta do Plano Piloto, mas com nome de outra RA: se o
        # polígono for usado, o resultado precisa ser o nome do polígono.
        quadrado = {"type": "Polygon", "coordinates": [[
            [-47.90, -15.82], [-47.86, -15.82], [-47.86, -15.77], [-47.90, -15.77], [-47.90, -15.82]]]}
        arq = tmp_path / "ra.geojson"
        arq.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"nome": "Guará"}, "geometry": quadrado}]}))
        monkeypatch.setattr(svc, "GEOJSON_PATH", arq)
        monkeypatch.setattr(svc, "_cache_poligonos", None)
        nome, metodo = svc.regiao_por_coordenadas(*PLANO_PILOTO)
        assert metodo == "poligono_geojson" and nome == "Guará"


class TestConsultaCompleta:
    def test_por_coordenadas(self):
        r = svc.localizar_regiao(latitude=CEILANDIA[0], longitude=CEILANDIA[1])
        assert r["entrada"] == "coordenadas" and r["regiao"] == "Ceilândia"
        assert r["precisao"] == "coordenadas"

    def test_por_cep(self, web):
        r = svc.localizar_regiao(cep="72115-070")
        assert r["entrada"] == "cep" and r["regiao"] == "Taguatinga"
        assert r["endereco_encontrado"] and r["precisao"] == "endereco"

    def test_por_cep_sem_logradouro_usa_bairro_e_sinaliza_aproximado(self, web):
        web["viacep"]["logradouro"] = ""
        r = svc.localizar_regiao(cep="72115070")
        assert r["precisao"] == "bairro" and r["aproximado"] is True

    def test_cep_so_acha_o_bairro_avisa_e_tenta_as_variacoes(self, web):
        """Caso real de Samambaia: o mapa não conhece a rua, devolve o bairro (rank 20)."""
        bairro = {"lat": "-15.8678", "lon": "-48.0994", "display_name": "Samambaia Norte", "place_rank": 20}
        web["viacep"] = {"logradouro": "QR 302 Conjunto 1", "bairro": "Samambaia Norte",
                         "localidade": "Brasília", "uf": "DF"}
        web["nominatim"] = [bairro]
        r = svc.localizar_regiao(cep="72321-002")
        assert r["precisao"] == "bairro" and r["aproximado"] is True
        assert web["chamadas_nominatim"] == 3  # 2 variações da rua + 1 do bairro

    def test_cep_acha_a_rua_na_segunda_variacao(self, web):
        bairro = {"lat": "-15.8678", "lon": "-48.0994", "display_name": "Samambaia Norte", "place_rank": 20}
        rua = {"lat": "-15.8791", "lon": "-48.0902", "display_name": "QR 302 Conjunto 1", "place_rank": 27}
        web["viacep"] = {"logradouro": "QR 302 Conjunto 1", "bairro": "Samambaia Norte",
                         "localidade": "Brasília", "uf": "DF"}
        web["nominatim_seq"] = [[bairro], [rua]]
        r = svc.localizar_regiao(cep="72321-002")
        assert r["precisao"] == "endereco" and r["latitude"] == -15.8791
        assert web["chamadas_nominatim"] == 2

    def test_ceps_diferentes_com_rua_achada_dao_pontos_diferentes(self, web):
        web["nominatim"] = [{"lat": "-15.8791", "lon": "-48.0902", "display_name": "a", "place_rank": 27}]
        a = svc.localizar_regiao(cep="72321-002")
        web["nominatim"] = [{"lat": "-15.8702", "lon": "-48.1010", "display_name": "b", "place_rank": 27}]
        b = svc.localizar_regiao(cep="72322-004")
        assert (a["latitude"], a["longitude"]) != (b["latitude"], b["longitude"])

    def test_por_endereco(self, web):
        r = svc.localizar_regiao(endereco="CNB 12 lote 3, Taguatinga")
        assert r["entrada"] == "endereco" and r["regiao"] == "Taguatinga"

    def test_cep_inexistente(self, web):
        web["viacep"] = {"erro": True}
        with pytest.raises(svc.LocalizacaoError) as e:
            svc.localizar_regiao(cep="99999999")
        assert e.value.status == 404

    def test_cep_de_outro_estado(self, web):
        web["viacep"]["uf"] = "SP"
        with pytest.raises(svc.LocalizacaoError, match="Distrito Federal"):
            svc.localizar_regiao(cep="01001000")

    def test_endereco_nao_encontrado(self, web):
        web["nominatim"] = []
        with pytest.raises(svc.LocalizacaoError) as e:
            svc.localizar_regiao(endereco="rua que nao existe 999")
        assert e.value.status == 404

    def test_servico_externo_fora_do_ar(self, web):
        web["cair"] = True
        with pytest.raises(svc.LocalizacaoError) as e:
            svc.localizar_regiao(endereco="Asa Norte")
        assert e.value.status == 503

    def test_ponto_geocodificado_fora_do_df_e_rejeitado(self, web):
        web["nominatim"] = [{"lat": "-23.55", "lon": "-46.63", "display_name": "São Paulo"}]
        with pytest.raises(svc.LocalizacaoError, match="fora do Distrito Federal"):
            svc.localizar_regiao(endereco="Avenida Paulista")

    def test_entrada_vazia_ou_incompleta(self):
        with pytest.raises(svc.LocalizacaoError):
            svc.localizar_regiao()
        with pytest.raises(svc.LocalizacaoError):
            svc.localizar_regiao(latitude=-15.8)


class TestRotaHttp:
    def test_coordenadas_200(self, cliente):
        r = cliente.get("/api/localizar", params={"latitude": PLANO_PILOTO[0], "longitude": PLANO_PILOTO[1]})
        assert r.status_code == 200 and r.json()["regiao"] == "Plano Piloto"

    def test_cep_200(self, cliente, web):
        r = cliente.get("/api/localizar", params={"cep": "72115-070"})
        assert r.status_code == 200 and r.json()["regiao"] == "Taguatinga"

    def test_sem_parametros_422(self, cliente):
        assert cliente.get("/api/localizar").status_code == 422

    def test_cep_malformado_422(self, cliente):
        assert cliente.get("/api/localizar", params={"cep": "12"}).status_code == 422

    def test_endereco_curto_422(self, cliente):
        assert cliente.get("/api/localizar", params={"endereco": "ab"}).status_code == 422

    def test_nao_encontrado_404(self, cliente, web):
        web["nominatim"] = []
        r = cliente.get("/api/localizar", params={"endereco": "lugar nenhum de verdade"})
        assert r.status_code == 404 and "não encontrado" in r.json()["detail"].lower()

    def test_publicada_no_openapi(self, cliente):
        assert "/api/localizar" in cliente.get("/openapi.json").json()["paths"]


class TestApiClientOffline:
    def test_sem_api_chama_o_servico_direto(self):
        c = ApiClient("http://127.0.0.1:9")  # porta fechada: API offline
        r = c.localizar_regiao(latitude=CEILANDIA[0], longitude=CEILANDIA[1])
        assert r["regiao"] == "Ceilândia"

    def test_sem_api_erro_vira_dicionario(self):
        c = ApiClient("http://127.0.0.1:9")
        assert "erro" in c.localizar_regiao(cep="12")


class TestTelaCompleta:
    """A RA encontrada deve atualizar o filtro lateral (e não só o painel de detalhe)."""

    def test_regiao_encontrada_ajusta_filtro_lateral(self, monkeypatch):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest

        resposta = {
            "entrada": "endereco", "consulta": "cnb 12 taguatinga",
            "endereco_encontrado": "CNB 12, Taguatinga", "latitude": -15.83,
            "longitude": -48.05, "regiao": "Taguatinga",
            "metodo": "poligono_postgis", "precisao": "endereco", "aproximado": False,
        }
        monkeypatch.setattr(ApiClient, "localizar_regiao", lambda self, **k: resposta)

        main = Path(__file__).resolve().parent.parent / "app" / "main.py"
        at = AppTest.from_file(str(main), default_timeout=60).run()
        assert not at.exception

        campo = next(t for t in at.text_input if t.label == "Endereço")
        campo.set_value("cnb 12 taguatinga")
        botao = next(b for b in at.button if b.label == "Buscar região")
        botao.click().run()

        assert not at.exception
        assert at.session_state["filtro_ra"] == ["Taguatinga"]
        assert at.session_state["ra_detalhe"] == "Taguatinga"
        assert at.sidebar.multiselect[0].value == ["Taguatinga"]


# Polígono simples (quadrado) usado como "RA" nos testes do mapa
_RA_TESTE = {
    "nome": "Taguatinga", "latitude": -15.83, "longitude": -48.06, "zoom": 12,
    "contorno": {"type": "Polygon", "coordinates": [[
        [-48.10, -15.86], [-48.01, -15.86], [-48.01, -15.80], [-48.10, -15.80], [-48.10, -15.86]]]},
}


class TestMarcadorNoMapa:
    """O local achado (CEP/endereço/GPS) vira um ponto vermelho no mapa, com zoom."""

    def _renderizar(self, monkeypatch, **extra):
        from app.components import map_view

        capturado = {}
        monkeypatch.setattr(
            map_view.st, "pydeck_chart",
            lambda deck, **kw: capturado.setdefault("deck", deck),
        )
        map_view.render_map(
            pontos_calor=[], ocorrencias=[],
            coropleto=[{"nome": "Taguatinga", "total": 10}],
            regioes_geo=[_RA_TESTE], regioes_meta=[_RA_TESTE], **extra,
        )
        return capturado["deck"]

    def test_com_ponto_adiciona_camadas_e_da_zoom(self, monkeypatch):
        deck = self._renderizar(
            monkeypatch, ponto_consulta={"latitude": -15.8335, "longitude": -48.0567}
        )
        ids = [c.id for c in deck.layers]
        assert "ponto-consulta" in ids and "ponto-consulta-halo" in ids
        vista = deck.initial_view_state
        assert round(vista.latitude, 4) == -15.8335 and vista.zoom == 13

    def test_ponto_nao_interfere_no_clique_das_ras(self, monkeypatch):
        deck = self._renderizar(
            monkeypatch, ponto_consulta={"latitude": -15.8335, "longitude": -48.0567}
        )
        marcadores = [c for c in deck.layers if c.id.startswith("ponto-consulta")]
        assert marcadores and all(not c.pickable for c in marcadores)

    def test_sem_ponto_nao_ha_marcador_e_o_mapa_segue_normal(self, monkeypatch):
        deck = self._renderizar(monkeypatch)
        ids = [c.id for c in deck.layers]
        assert "ra-coropleto" in ids
        assert not any(i.startswith("ponto-consulta") for i in ids)


class TestMarcadorNaTela:
    """main.py só passa o ponto ao mapa enquanto o filtro está na RA encontrada."""

    def _rodar(self, monkeypatch, filtro):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        from app.components import map_view

        chamadas = []
        monkeypatch.setattr(map_view, "render_map", lambda **kw: chamadas.append(kw))
        at = AppTest.from_file(
            str(Path(__file__).resolve().parent.parent / "app" / "main.py"), default_timeout=60
        )
        at.session_state["loc_resultado"] = {
            "regiao": "Taguatinga", "latitude": -15.8335, "longitude": -48.0567,
            "metodo": "poligono_postgis", "aproximado": False,
        }
        at.session_state["filtro_ra"] = filtro
        at.run()
        assert not at.exception
        return chamadas

    def test_ponto_enviado_quando_filtro_esta_na_regiao_achada(self, monkeypatch):
        chamadas = self._rodar(monkeypatch, ["Taguatinga"])
        assert chamadas[-1]["ponto_consulta"] == {"latitude": -15.8335, "longitude": -48.0567}

    def test_ponto_omitido_quando_filtro_muda_de_regiao(self, monkeypatch):
        chamadas = self._rodar(monkeypatch, ["Samambaia"])
        assert chamadas[-1]["ponto_consulta"] is None
