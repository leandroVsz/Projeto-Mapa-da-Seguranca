"""Testes funcionais de caixa-preta — seção 4.1 do relatório.

Cada classe corresponde a um item TFxx/HUxx da tabela do relatório. Os
testes observam apenas entradas (requisições/arquivos), ações e saídas
(respostas HTTP/bytes), sem inspecionar a implementação interna.

CH01 — leitura de dados: exercitada no modo fallback (CSV consolidado),
        que é o modo de execução sem banco e usa a mesma fonte da carga.
CH02 — conta e relatórios: exercitados contra o PostgreSQL real com
        usuários temporários removidos ao final de cada teste.
"""
import io
import socket
import uuid

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.server import app
from app.api_client import ApiClient
from app.components.chart_export import gerar_csv, gerar_pdf, nome_arquivo

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


@pytest.fixture(scope="module")
def cliente():
    """Aplicação FastAPI pronta para receber requisições HTTP."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# TF01 — HU01: painel de indicadores e status do sistema
# ---------------------------------------------------------------------------
class TestTF01PainelIndicadores:
    def test_raiz_identifica_servico(self, cliente):
        resposta = cliente.get("/")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["status"] == "online"
        assert corpo["sistema"] == "Mapa da Segurança do Distrito Federal"

    def test_health_informa_totais_do_sistema(self, cliente):
        resposta = cliente.get("/api/health")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["status"] == "healthy"
        assert corpo["total_registros_ativos"] > 0
        assert corpo["total_regioes_mapeadas"] > 0
        assert "banco" in corpo

    def test_stats_retorna_os_quatro_kpis(self, cliente):
        resposta = cliente.get("/api/stats")
        assert resposta.status_code == 200
        stats = resposta.json()
        assert stats["total_ocorrencias"] > 0
        for chave in (
            "ra_mais_afetada", "crime_mais_frequente",
            "por_natureza", "por_regiao", "por_ano", "por_mes",
        ):
            assert chave in stats
        assert stats["ra_mais_afetada"] not in ("", "N/A")
        # 'Distrito Federal' é o agregado estadual, não uma RA do ranking
        assert stats["ra_mais_afetada"] != "Distrito Federal"
        assert stats["crime_mais_frequente"] not in ("", "N/A")
        assert sum(stats["por_mes"].values()) == stats["total_ocorrencias"]


# ---------------------------------------------------------------------------
# TF02 — HU02: mapa geoespacial (coropleto e mapa de calor)
# ---------------------------------------------------------------------------
class TestTF02MapaGeoespacial:
    def test_regioes_possuem_nome_e_coordenadas(self, cliente):
        resposta = cliente.get("/api/regioes")
        assert resposta.status_code == 200
        regioes = resposta.json()
        assert len(regioes) > 0
        nomes = [r["nome"] for r in regioes]
        assert len(nomes) == len(set(nomes))
        for regiao in regioes:
            # a API com banco também devolve `codigo`; o fallback local tem
            # `ra_numero` no metadado e usa lat/long para o heatmap
            assert regiao.get("codigo") is not None or regiao.get("ra_numero") is not None
            assert regiao.get("latitude") is not None
            assert regiao.get("longitude") is not None

    def test_heatmap_gera_pontos_validos(self, cliente):
        resposta = cliente.get("/api/heatmap")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["total_pontos"] == len(corpo["pontos"]) > 0
        for latitude, longitude, peso in corpo["pontos"]:
            assert -16.2 <= latitude <= -15.4          # limite do DF
            assert -48.4 <= longitude <= -47.2
            assert 0.0 <= peso <= 1.0
        assert max(p[2] for p in corpo["pontos"]) == 1.0

    def test_coropleto_retorna_intensidade_por_ra(self, cliente):
        resposta = cliente.get("/api/coropleto")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert {"online", "regioes", "top_naturezas"}.issubset(corpo)
        assert len(corpo["regioes"]) > 0
        for regiao in corpo["regioes"]:
            assert regiao["nome"]
            assert regiao["total"] >= 0
        assert isinstance(corpo["top_naturezas"], dict)


# ---------------------------------------------------------------------------
# TF03 — HU03: filtros combinados (RA, eixo, natureza e ano)
# ---------------------------------------------------------------------------
class TestTF03Filtros:
    def test_opcoes_de_filtro_disponiveis(self, cliente):
        resposta = cliente.get("/api/filtros")
        assert resposta.status_code == 200
        filtros = resposta.json()
        for chave in ("regioes", "naturezas", "eixos", "anos"):
            assert len(filtros[chave]) > 0
        assert filtros["anos"] == sorted(filtros["anos"], reverse=True)

    def test_filtro_por_regiao_e_ano_reduz_o_total(self, cliente):
        filtros = cliente.get("/api/filtros").json()
        base = cliente.get("/api/stats").json()
        regiao = filtros["regioes"][0]
        ano = filtros["anos"][0]

        filtrado = cliente.get(
            "/api/stats", params={"regiao": regiao, "ano": ano}
        ).json()

        assert 0 < filtrado["total_ocorrencias"] <= base["total_ocorrencias"]
        assert list(filtrado["por_ano"]) == [str(ano)]
        assert regiao in filtrado["por_regiao"]

    def test_filtro_por_eixo_indicador(self, cliente):
        filtros = cliente.get("/api/filtros").json()
        base = cliente.get("/api/stats").json()
        eixo = filtros["eixos"][0]

        filtrado = cliente.get("/api/stats", params={"eixo": eixo}).json()

        assert 0 < filtrado["total_ocorrencias"] <= base["total_ocorrencias"]

    def test_filtro_sem_correspondencia_retorna_zero(self, cliente):
        stats = cliente.get(
            "/api/stats", params={"regiao": "Região Inexistente"}
        ).json()
        assert stats["total_ocorrencias"] == 0
        assert stats["ra_mais_afetada"] == "N/A"
        assert stats["crime_mais_frequente"] == "N/A"


# ---------------------------------------------------------------------------
# TF04 — HU04: tabela de ocorrências, busca textual e exportação CSV
# ---------------------------------------------------------------------------
class TestTF04TabelaOcorrencias:
    def test_listagem_respeita_limite_e_schema(self, cliente):
        resposta = cliente.get("/api/ocorrencias", params={"limite": 20})
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert 0 < corpo["limite_retornado"] <= 20
        assert corpo["total_encontrado"] >= corpo["limite_retornado"]
        for linha in corpo["ocorrencias"]:
            assert linha["regiao_administrativa"]
            assert linha["natureza_crime"]
            assert isinstance(linha["ano"], int)
            assert linha["mes"] in MESES
            assert linha["quantidade"] >= 0

    def test_busca_textual_filtra_por_ra_ou_crime(self, cliente):
        termo = "Ceilândia"
        resposta = cliente.get("/api/ocorrencias", params={"busca": termo, "limite": 50})
        assert resposta.status_code == 200
        linhas = resposta.json()["ocorrencias"]
        assert len(linhas) > 0
        alvo = termo.lower()
        assert all(
            alvo in linha["regiao_administrativa"].lower()
            or alvo in linha["natureza_crime"].lower()
            for linha in linhas
        )

    def test_busca_sem_resultado_retorna_lista_vazia(self, cliente):
        corpo = cliente.get(
            "/api/ocorrencias", params={"busca": "zzzzzzzz"}
        ).json()
        assert corpo["total_encontrado"] == 0
        assert corpo["ocorrencias"] == []

    @pytest.mark.parametrize("limite", [0, 5001])
    def test_limite_fora_da_faixa_e_rejeitado(self, cliente, limite):
        resposta = cliente.get("/api/ocorrencias", params={"limite": limite})
        assert resposta.status_code == 422

    def test_filtro_por_ano_na_listagem(self, cliente):
        ano = cliente.get("/api/filtros").json()["anos"][0]
        linhas = cliente.get(
            "/api/ocorrencias", params={"ano": ano, "limite": 100}
        ).json()["ocorrencias"]
        assert linhas and all(linha["ano"] == ano for linha in linhas)


# ---------------------------------------------------------------------------
# TF05 — HU05: painel de detalhe da RA clicada no mapa
# ---------------------------------------------------------------------------
class TestTF05DetalheRegiao:
    def test_detalhe_consistente_com_o_coropleto(self, cliente):
        coropleto = cliente.get("/api/coropleto").json()["regioes"]
        alvo = coropleto[0]

        detalhe = cliente.get(
            "/api/detalhe-regiao", params={"regiao": alvo["nome"]}
        ).json()

        assert detalhe["regiao"] == alvo["nome"]
        assert detalhe["total_ocorrencias"] == alvo["total"]
        assert sum(detalhe["por_natureza"].values()) == alvo["total"]
        assert sum(detalhe["por_mes"].values()) == alvo["total"]
        assert sum(detalhe["por_ano"].values()) == alvo["total"]
        assert set(int(mes) for mes in detalhe["por_mes"]).issubset(range(1, 13))

    def test_ra_inexistente_retorna_estrutura_vazia(self, cliente):
        detalhe = cliente.get(
            "/api/detalhe-regiao", params={"regiao": "Região Inexistente"}
        ).json()
        assert detalhe["total_ocorrencias"] == 0
        assert detalhe["por_natureza"] == {}
        assert detalhe["por_mes"] == {}

    def test_regiao_e_obrigatoria(self, cliente):
        assert cliente.get("/api/detalhe-regiao").status_code == 422


# ---------------------------------------------------------------------------
# TF06 — HU06: cadastro, login, sessão e recuperação de senha
# ---------------------------------------------------------------------------
SENHA_FORTE = "SenhaTeste123"


def _novo_email(prefixo: str) -> str:
    return f"{prefixo}.{uuid.uuid4().hex[:10]}@teste.local"


@pytest.fixture
def usuario_teste(banco_teste, cliente):
    """Cria uma conta real e a remove (com logs) ao final do teste."""
    email = _novo_email("tf")
    resposta = cliente.post("/api/auth/registro", json={
        "nome": "Usuário de Teste", "email": email, "senha": SENHA_FORTE,
    })
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["token"]
    yield {"email": email, "senha": SENHA_FORTE, **dados}
    with banco_teste.begin() as conexao:
        conexao.execute(text("DELETE FROM auth.log_acesso WHERE email = :e"), {"e": email})
        conexao.execute(text("DELETE FROM auth.usuario WHERE email = :e"), {"e": email})


@pytest.mark.integracao_db
class TestTF06Autenticacao:
    def test_registro_rejeita_email_invalido(self, cliente, banco_teste):
        resposta = cliente.post("/api/auth/registro", json={
            "nome": "Fulano", "email": "email-invalido", "senha": SENHA_FORTE,
        })
        assert resposta.status_code == 422

    def test_registro_rejeita_senha_fraca(self, cliente, banco_teste):
        resposta = cliente.post("/api/auth/registro", json={
            "nome": "Fulano", "email": _novo_email("fraca"), "senha": "12345678",
        })
        assert resposta.status_code == 422
        assert "maiúscula" in resposta.json()["detail"]

    def test_registro_autentica_e_retorna_token(self, cliente, usuario_teste):
        assert usuario_teste["usuario"]["email"] == usuario_teste["email"]
        assert usuario_teste["usuario"]["papel"] == "usuario"
        assert usuario_teste["usuario"]["nome"] == "Usuário de Teste"

    def test_email_duplicado_e_rejeitado(self, cliente, usuario_teste):
        resposta = cliente.post("/api/auth/registro", json={
            "nome": "Outro Nome", "email": usuario_teste["email"], "senha": SENHA_FORTE,
        })
        assert resposta.status_code == 409

    def test_login_errado_e_generico(self, cliente, usuario_teste):
        errado = cliente.post("/api/auth/login", json={
            "email": usuario_teste["email"], "senha": "SenhaErrada999",
        })
        inexistente = cliente.post("/api/auth/login", json={
            "email": _novo_email("naoexiste"), "senha": "SenhaErrada999",
        })
        assert errado.status_code == inexistente.status_code == 401
        # a mensagem não revela se o e-mail existe
        assert errado.json()["detail"] == inexistente.json()["detail"]

    def test_login_correto_e_acesso_autenticado(self, cliente, usuario_teste):
        resposta = cliente.post("/api/auth/login", json={
            "email": usuario_teste["email"], "senha": SENHA_FORTE,
        })
        assert resposta.status_code == 200
        token = resposta.json()["token"]

        eu = cliente.get("/api/auth/eu", headers={"X-Auth-Token": token})
        assert eu.status_code == 200
        assert eu.json()["usuario"]["email"] == usuario_teste["email"]

        assert cliente.get("/api/auth/eu").status_code == 401
        assert cliente.get(
            "/api/auth/eu", headers={"X-Auth-Token": "token-invalido"}
        ).status_code == 401

    def test_logout_invalida_a_sessao(self, cliente, usuario_teste):
        token = usuario_teste["token"]
        assert cliente.post(
            "/api/auth/logout", headers={"X-Auth-Token": token}
        ).status_code == 200
        assert cliente.get(
            "/api/auth/eu", headers={"X-Auth-Token": token}
        ).status_code == 401

    def test_redefinicao_de_senha_por_token(self, cliente, usuario_teste):
        solicitacao = cliente.post("/api/auth/reset/solicitar", json={
            "email": usuario_teste["email"],
        })
        assert solicitacao.status_code == 200
        token = solicitacao.json()["token_dev"]

        nova = "NovaSenhaForte456"
        confirmacao = cliente.post("/api/auth/reset/confirmar", json={
            "token": token, "nova_senha": nova,
        })
        assert confirmacao.status_code == 200

        assert cliente.post("/api/auth/login", json={
            "email": usuario_teste["email"], "senha": SENHA_FORTE,
        }).status_code == 401
        assert cliente.post("/api/auth/login", json={
            "email": usuario_teste["email"], "senha": nova,
        }).status_code == 200


# ---------------------------------------------------------------------------
# TF07 — HU07: salvar, listar e excluir relatórios na conta
# ---------------------------------------------------------------------------
RELATORIO_VALIDO = {
    "titulo": "Ocorrências por região",
    "dimensao": "por_regiao",
    "tipo_grafico": "Barras",
    "top_n": 10,
    "filtros": {"regioes": ["Ceilândia"], "anos": [2024]},
}


@pytest.mark.integracao_db
class TestTF07RelatoriosSalvos:
    def test_rotas_exigem_autenticacao(self, cliente, banco_teste):
        assert cliente.post("/api/relatorios", json=RELATORIO_VALIDO).status_code == 401
        assert cliente.get("/api/relatorios").status_code == 401
        assert cliente.delete("/api/relatorios/1").status_code == 401

    def test_salvar_e_listar(self, cliente, usuario_teste):
        token = usuario_teste["token"]
        headers = {"X-Auth-Token": token}

        criado = cliente.post("/api/relatorios", json=RELATORIO_VALIDO, headers=headers)
        assert criado.status_code == 200
        relatorio = criado.json()
        assert relatorio["titulo"] == RELATORIO_VALIDO["titulo"]
        assert relatorio["filtros"] == RELATORIO_VALIDO["filtros"]
        assert isinstance(relatorio["id"], int)

        lista = cliente.get("/api/relatorios", headers=headers)
        assert lista.status_code == 200
        assert any(item["id"] == relatorio["id"] for item in lista.json())

    def test_titulo_duplicado_e_rejeitado(self, cliente, usuario_teste):
        headers = {"X-Auth-Token": usuario_teste["token"]}
        cliente.post("/api/relatorios", json=RELATORIO_VALIDO, headers=headers)
        duplicado = cliente.post("/api/relatorios", json=RELATORIO_VALIDO, headers=headers)
        assert duplicado.status_code == 409

    @pytest.mark.parametrize("campo,valor", [
        ("top_n", 2),
        ("dimensao", "por_bairro"),
        ("tipo_grafico", "Dispersão"),
    ])
    def test_payload_invalido_e_rejeitado(self, cliente, usuario_teste, campo, valor):
        payload = {**RELATORIO_VALIDO, campo: valor}
        resposta = cliente.post(
            "/api/relatorios", json=payload,
            headers={"X-Auth-Token": usuario_teste["token"]},
        )
        assert resposta.status_code == 422

    def test_excluir_relatorio(self, cliente, usuario_teste):
        headers = {"X-Auth-Token": usuario_teste["token"]}
        criado = cliente.post("/api/relatorios", json=RELATORIO_VALIDO, headers=headers).json()

        assert cliente.delete(
            f"/api/relatorios/{criado['id']}", headers=headers
        ).status_code == 200
        assert cliente.delete(
            f"/api/relatorios/{criado['id']}", headers=headers
        ).status_code == 404
        assert cliente.get("/api/relatorios", headers=headers).json() == []

    def test_usuario_nao_exclui_relatorio_de_outro(self, cliente, usuario_teste, banco_teste):
        headers_a = {"X-Auth-Token": usuario_teste["token"]}
        email_b = _novo_email("tf07b")
        registro_b = cliente.post("/api/auth/registro", json={
            "nome": "Usuário B", "email": email_b, "senha": SENHA_FORTE,
        })
        assert registro_b.status_code == 200
        headers_b = {"X-Auth-Token": registro_b.json()["token"]}

        try:
            criado = cliente.post(
                "/api/relatorios", json=RELATORIO_VALIDO, headers=headers_a
            ).json()

            assert cliente.delete(
                f"/api/relatorios/{criado['id']}", headers=headers_b
            ).status_code == 404
            assert cliente.get("/api/relatorios", headers=headers_b).json() == []
            assert any(
                item["id"] == criado["id"]
                for item in cliente.get("/api/relatorios", headers=headers_a).json()
            )
        finally:
            with banco_teste.begin() as conexao:
                conexao.execute(
                    text("DELETE FROM auth.log_acesso WHERE email = :e"),
                    {"e": email_b},
                )
                conexao.execute(
                    text("DELETE FROM auth.usuario WHERE email = :e"),
                    {"e": email_b},
                )


# ---------------------------------------------------------------------------
# TF08 — HU08: exportação dos gráficos em CSV e PDF
# ---------------------------------------------------------------------------
class TestTF08Exportacao:
    @pytest.fixture
    def dados(self):
        return pd.DataFrame({
            "Categoria": ["Ceilândia", "Gama", "Taguatinga"],
            "Ocorrências": [1234, 567, 89],
        })

    def test_csv_exportado_pode_ser_reaberto(self, dados):
        conteudo = gerar_csv(dados)
        assert conteudo.startswith(b"\xef\xbb\xbf")  # BOM para o Excel

        lido = pd.read_csv(io.BytesIO(conteudo), sep=";")
        assert list(lido.columns) == ["Categoria", "Ocorrências"]
        assert lido["Categoria"].tolist() == dados["Categoria"].tolist()
        assert lido["Ocorrências"].tolist() == dados["Ocorrências"].tolist()

    def test_pdf_exportado_e_valido(self, dados):
        conteudo = gerar_pdf(dados, "Barras", "Ocorrências por região")
        assert conteudo.startswith(b"%PDF")
        assert len(conteudo) > 1500

    def test_nome_de_arquivo_sem_acentos_ou_espacos(self):
        assert nome_arquivo(
            "Ocorrências por região", "Barras horizontais", "pdf"
        ) == "ocorrencias_por_regiao_barras_horizontais.pdf"

    def test_endpoint_de_consolidacao_esta_publicado(self, cliente):
        caminhos = cliente.get("/openapi.json").json()["paths"]
        assert "/api/consolidar" in caminhos
        assert "/api/carga-db" in caminhos


# ---------------------------------------------------------------------------
# TF09 — HU09: modo direto local (fallback sem a API)
# ---------------------------------------------------------------------------
def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="class")
def api_offline():
    return ApiClient(base_url=f"http://127.0.0.1:{_porta_livre()}")


class TestTF09ModoFallback:
    """Sem API no ar, o painel deve continuar exibindo os mesmos dados do CSV."""

    def test_backend_reportado_offline(self, api_offline):
        assert api_offline.check_health()["online"] is False
        assert api_offline.is_online() is False

    def test_filtros_e_indicadores_vem_do_csv(self, api_offline):
        filtros = api_offline.get_filtros()
        assert len(filtros["regioes"]) > 0
        assert len(filtros["anos"]) > 0

        stats = api_offline.get_stats()
        assert stats["total_ocorrencias"] > 0
        assert stats["ra_mais_afetada"] not in ("", "N/A")

    def test_mapa_e_tabela_funcionam_offline(self, api_offline):
        coropleto = api_offline.get_coropleto()
        assert coropleto["online"] is False
        assert len(coropleto["regioes"]) > 0

        pontos = api_offline.get_heatmap()
        assert len(pontos) > 0

        linhas = api_offline.get_ocorrencias(limite=5)
        assert len(linhas) == 5

    def test_detalhe_de_ra_offline(self, api_offline):
        stats = api_offline.get_stats()
        regiao = next(iter(stats["por_regiao"]))
        detalhe = api_offline.get_detalhe_regiao(regiao)
        assert detalhe["regiao"] == regiao
        assert detalhe["total_ocorrencias"] > 0


# ---------------------------------------------------------------------------
# TF10 — HU10: consistência entre os indicadores exibidos
# ---------------------------------------------------------------------------
class TestTF10ConsistenciaIndicadores:
    def test_soma_do_coropleto_igual_ao_total_geral(self, cliente):
        stats = cliente.get("/api/stats").json()
        coropleto = cliente.get("/api/coropleto").json()["regioes"]
        assert sum(r["total"] for r in coropleto) == stats["total_ocorrencias"]

    def test_detalhe_bate_com_coropleto_e_com_as_listagens(self, cliente):
        stats = cliente.get("/api/stats").json()
        coropleto = cliente.get("/api/coropleto").json()["regioes"]

        detalhe = cliente.get(
            "/api/detalhe-regiao", params={"regiao": coropleto[0]["nome"]}
        ).json()
        assert detalhe["total_ocorrencias"] == coropleto[0]["total"]
        assert sum(detalhe["por_natureza"].values()) == detalhe["total_ocorrencias"]

        assert 0 < sum(stats["por_regiao"].values()) <= stats["total_ocorrencias"]
        assert sum(stats["por_ano"].values()) == stats["total_ocorrencias"]

    def test_listagem_bate_com_os_indicadores_do_mesmo_filtro(self, cliente):
        filtros = cliente.get("/api/filtros").json()
        regiao = filtros["regioes"][0]
        ano = filtros["anos"][0]
        params = {"regiao": regiao, "ano": ano}

        stats = cliente.get("/api/stats", params=params).json()
        corpo = cliente.get(
            "/api/ocorrencias", params={**params, "limite": 1000}
        ).json()

        assert corpo["total_encontrado"] < 1000, "o limite truncaria a conferência"
        assert sum(
            linha["quantidade"] for linha in corpo["ocorrencias"]
        ) == stats["total_ocorrencias"]
