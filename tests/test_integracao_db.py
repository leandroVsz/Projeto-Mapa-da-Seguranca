"""Testes de integração com o banco — seção 4.2.1 do relatório.

Cada teste executa uma operação real no PostgreSQL/PostGIS configurado no
`.env` do projeto (ou em TEST_DATABASE_URL) e confere o efeito por meio
das mesmas consultas usadas pela aplicação (DbService, AuthService e
RelatorioService).

Os dados são criados com nomes/ids únicos e removidos ao final de cada
teste — nenhum registro existente é alterado. Se o banco não estiver
acessível, os testes são pulados (não falham).
"""
import uuid

import pytest
from sqlalchemy import text

from api.services.auth_service import AuthService, AuthError
from api.services.db_service import DbService
from api.services.relatorio_service import RelatorioService, RelatorioError

pytestmark = pytest.mark.integracao_db

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]
ANO = 2030  # ano fictício, fora da série histórica real


# ---------------------------------------------------------------------------
# Fixtures: cenário de dados e usuário temporários
# ---------------------------------------------------------------------------
@pytest.fixture
def cenario(banco_teste):
    """Cria RA + natureza + 3 ocorrências mensais e remove tudo ao final."""
    sufixo = uuid.uuid4().hex[:8].upper()
    nome_ra = f"RA TESTE {sufixo}"
    nome_crime = f"CRIME TESTE {sufixo}"
    eixo = f"EIXO TESTE {sufixo}"
    codigo_ra = 900000 + int(uuid.uuid4().hex[:5], 16) % 90000

    with banco_teste.begin() as conexao:
        regiao_id = conexao.execute(text("""
            INSERT INTO regiao_administrativa (nome, codigo, centroide)
            VALUES (
                :nome, :codigo,
                ST_SetSRID(ST_MakePoint(-47.9000, -15.8000), 4326)
            )
            RETURNING id
        """), {"nome": nome_ra, "codigo": codigo_ra}).scalar_one()

        crime_id = conexao.execute(text("""
            INSERT INTO tipo_crime (nome, eixo_indicador, descricao)
            VALUES (:nome, :eixo, 'Registro temporário de teste de integração')
            RETURNING id
        """), {"nome": nome_crime, "eixo": eixo}).scalar_one()

        ocorrencias = {}
        for mes, tipo, quantidade in [
            (1, "OCORRENCIA", 5),
            (2, "OCORRENCIA", 4),
            (1, "VITIMA", 2),
        ]:
            ocorrencias[(mes, tipo)] = conexao.execute(text("""
                INSERT INTO ocorrencia_mensal
                    (regiao_id, tipo_crime_id, ano, mes, tipo_registro, quantidade)
                VALUES
                    (:regiao_id, :crime_id, :ano, :mes, :tipo, :quantidade)
                RETURNING id
            """), {
                "regiao_id": regiao_id, "crime_id": crime_id, "ano": ANO,
                "mes": mes, "tipo": tipo, "quantidade": quantidade,
            }).scalar_one()

    dados = {
        "sufixo": sufixo,
        "nome_ra": nome_ra,
        "nome_crime": nome_crime,
        "eixo": eixo,
        "codigo_ra": codigo_ra,
        "regiao_id": regiao_id,
        "crime_id": crime_id,
        "ocorrencias": ocorrencias,
    }
    yield dados

    with banco_teste.begin() as conexao:
        conexao.execute(text(
            "DELETE FROM ocorrencia_mensal WHERE regiao_id = :r OR tipo_crime_id = :c"
        ), {"r": regiao_id, "c": crime_id})
        conexao.execute(text("DELETE FROM regiao_administrativa WHERE id = :r"), {"r": regiao_id})
        conexao.execute(text("DELETE FROM tipo_crime WHERE id = :c"), {"c": crime_id})


@pytest.fixture
def usuario_db(banco_teste):
    """Cria um usuário real e o remove (com logs/sessões/relatórios) no final."""
    email = f"integracao.{uuid.uuid4().hex[:10]}@teste.local"
    senha = "SenhaIntegracao123"
    usuario = AuthService.registrar("Usuário Integração", email, senha)

    yield {"id": usuario["id"], "email": email, "senha": senha}

    with banco_teste.begin() as conexao:
        conexao.execute(text("DELETE FROM auth.log_acesso WHERE email = :e"), {"e": email})
        conexao.execute(text("DELETE FROM auth.usuario WHERE email = :e"), {"e": email})


# ---------------------------------------------------------------------------
# TI01 — Inserção
# ---------------------------------------------------------------------------
class TestTI01Insercao:
    def test_dimensoes_e_fato_persistidos(self, cenario, banco_teste):
        with banco_teste.connect() as conexao:
            regiao = conexao.execute(text("""
                SELECT nome, codigo, centroide IS NOT NULL AS tem_centroide
                FROM regiao_administrativa WHERE id = :id
            """), {"id": cenario["regiao_id"]}).one()
            crime = conexao.execute(text("""
                SELECT nome, eixo_indicador FROM tipo_crime WHERE id = :id
            """), {"id": cenario["crime_id"]}).one()
            fato = conexao.execute(text("""
                SELECT tipo_registro, SUM(quantidade) AS total, COUNT(*) AS linhas
                FROM ocorrencia_mensal
                WHERE regiao_id = :r AND tipo_crime_id = :c AND ano = :ano
                GROUP BY tipo_registro
                ORDER BY tipo_registro
            """), {"r": cenario["regiao_id"], "c": cenario["crime_id"], "ano": ANO}).all()

        assert regiao.nome == cenario["nome_ra"]
        assert regiao.codigo == cenario["codigo_ra"]
        assert regiao.tem_centroide is True

        assert crime.nome == cenario["nome_crime"]
        assert crime.eixo_indicador == cenario["eixo"]

        assert [(r.tipo_registro, int(r.total), r.linhas) for r in fato] == [
            ("OCORRENCIA", 9, 2),
            ("VITIMA", 2, 1),
        ]

    def test_usuario_e_relatorio_persistidos(self, banco_teste, usuario_db):
        with banco_teste.connect() as conexao:
            senha_hash = conexao.execute(text(
                "SELECT senha_hash FROM auth.usuario WHERE id = :id"
            ), {"id": usuario_db["id"]}).scalar_one()
            auditoria = conexao.execute(text("""
                SELECT COUNT(*) FROM auth.log_acesso
                WHERE email = :e AND acao = 'REGISTRO' AND sucesso
            """), {"e": usuario_db["email"]}).scalar_one()

        assert senha_hash.startswith("$2")           # bcrypt
        assert usuario_db["senha"] not in senha_hash   # senha nunca em texto puro
        assert auditoria == 1

        relatorio = RelatorioService.salvar(
            usuario_id=usuario_db["id"],
            titulo="Relatório de integração",
            dimensao="por_regiao",
            tipo_grafico="Barras",
            top_n=10,
            filtros={"anos": [ANO]},
        )
        assert relatorio["id"] > 0
        assert relatorio["filtros"] == {"anos": [ANO]}


# ---------------------------------------------------------------------------
# TI02 — Consulta
# ---------------------------------------------------------------------------
class TestTI02Consulta:
    def test_coropleto_e_estatisticas_refletem_o_registro(self, cenario):
        servico = DbService()
        coropleto = {r["nome"]: r["total"] for r in servico.get_coropleto(
            regioes=[cenario["nome_ra"]], anos=[ANO]
        )}
        assert coropleto[cenario["nome_ra"]] == 9  # padrão: tipo_registro=OCORRENCIA

        vitimas = {r["nome"]: r["total"] for r in servico.get_coropleto(
            regioes=[cenario["nome_ra"]], anos=[ANO], tipo_registro="VITIMA"
        )}
        assert vitimas[cenario["nome_ra"]] == 2

        stats = servico.get_estatisticas(regioes=[cenario["nome_ra"]], anos=[ANO])
        assert stats["total_ocorrencias"] == 9
        assert stats["ra_mais_afetada"] == cenario["nome_ra"]
        assert stats["crime_mais_frequente"] == cenario["nome_crime"]
        assert stats["por_natureza"][cenario["nome_crime"]] == 9
        assert stats["por_ano"] == {ANO: 9}
        assert stats["por_mes"] == {1: 5, 2: 4}

    def test_detalhe_e_listagem_da_regiao(self, cenario):
        servico = DbService()

        detalhe = servico.get_detalhe_regiao(cenario["nome_ra"], anos=[ANO])
        assert detalhe["total_ocorrencias"] == 9
        assert detalhe["por_mes"] == {1: 5, 2: 4}

        vitimas = servico.get_detalhe_regiao(
            cenario["nome_ra"], anos=[ANO], tipo_registro="VITIMA"
        )
        assert vitimas["total_ocorrencias"] == 2

        linhas = servico.listar_ocorrencias(
            regioes=[cenario["nome_ra"]], anos=[ANO]
        )
        assert len(linhas) == 2
        assert {linha["mes"] for linha in linhas} == {"jan", "fev"}
        assert {linha["natureza_crime"] for linha in linhas} == {cenario["nome_crime"]}

    def test_filtros_disponiveis_incluem_os_novos_valores(self, cenario):
        filtros = DbService().get_opcoes_filtros()
        assert cenario["nome_ra"] in filtros["regioes"]
        assert cenario["nome_crime"] in filtros["naturezas"]
        assert cenario["eixo"] in filtros["eixos"]
        assert ANO in filtros["anos"]

    def test_sessao_do_usuario_e_consultada(self, banco_teste, usuario_db):
        sessao = AuthService.criar_sessao(usuario_db["id"], lembrar=False)
        usuario = AuthService.validar_sessao(sessao["token"])

        assert usuario is not None
        assert usuario["id"] == usuario_db["id"]
        assert usuario["email"] == usuario_db["email"]
        assert AuthService.obter_por_id(usuario_db["id"])["nome"] == "Usuário Integração"
        assert any(
            u["id"] == usuario_db["id"]
            for u in AuthService.listar_usuarios()
        )

        with banco_teste.connect() as conexao:
            # o banco guarda apenas o SHA-256 do token, nunca o token em claro
            token_em_claro = conexao.execute(text(
                "SELECT COUNT(*) FROM auth.sessao_usuario WHERE token_hash = :t"
            ), {"t": sessao["token"]}).scalar_one()
        assert token_em_claro == 0


# ---------------------------------------------------------------------------
# TI03 — Atualização
# ---------------------------------------------------------------------------
class TestTI03Atualizacao:
    def test_upsert_atualiza_sem_duplicar(self, cenario, banco_teste):
        """Mesma operação idempotente usada por db/load_csv.py."""
        with banco_teste.begin() as conexao:
            conexao.execute(text("""
                INSERT INTO ocorrencia_mensal
                    (regiao_id, tipo_crime_id, ano, mes, tipo_registro, quantidade)
                VALUES
                    (:r, :c, :ano, 1, 'OCORRENCIA', 8),
                    (:r, :c, :ano, 3, 'OCORRENCIA', 3)
                ON CONFLICT ON CONSTRAINT uq_ocorrencia_mensal
                DO UPDATE SET quantidade = EXCLUDED.quantidade
            """), {"r": cenario["regiao_id"], "c": cenario["crime_id"], "ano": ANO})

        with banco_teste.connect() as conexao:
            linhas = conexao.execute(text("""
                SELECT mes, quantidade FROM ocorrencia_mensal
                WHERE regiao_id = :r AND tipo_crime_id = :c
                  AND ano = :ano AND tipo_registro = 'OCORRENCIA'
                ORDER BY mes
            """), {"r": cenario["regiao_id"], "c": cenario["crime_id"], "ano": ANO}).all()

        # janeiro foi atualizado (5 → 8), março inserido e nada foi duplicado
        assert [(r.mes, r.quantidade) for r in linhas] == [(1, 8), (2, 4), (3, 3)]
        assert DbService().get_detalhe_regiao(
            cenario["nome_ra"], anos=[ANO], tipo_registro="OCORRENCIA"
        )["total_ocorrencias"] == 15

    def test_atualizacao_de_dimensao_e_refletida_nas_consultas(self, cenario, banco_teste):
        novo_eixo = cenario["eixo"] + " (revisado)"
        with banco_teste.begin() as conexao:
            conexao.execute(text(
                "UPDATE tipo_crime SET eixo_indicador = :eixo WHERE id = :id"
            ), {"eixo": novo_eixo, "id": cenario["crime_id"]})

        stats = DbService().get_estatisticas(
            regioes=[cenario["nome_ra"]], eixos=[novo_eixo], anos=[ANO]
        )
        assert stats["total_ocorrencias"] == 9

    def test_troca_de_senha_e_status_do_usuario(self, usuario_db):
        AuthService.trocar_senha(usuario_db["id"], usuario_db["senha"], "NovaSenhaForte456")

        with pytest.raises(AuthError) as erro_antigo:
            AuthService.autenticar(usuario_db["email"], usuario_db["senha"])
        assert erro_antigo.value.codigo == "credenciais"

        usuario = AuthService.autenticar(usuario_db["email"], "NovaSenhaForte456")
        assert usuario["id"] == usuario_db["id"]

        AuthService.alterar_status(usuario_db["id"], False)
        with pytest.raises(AuthError) as erro_inativo:
            AuthService.autenticar(usuario_db["email"], "NovaSenhaForte456")
        assert erro_inativo.value.codigo == "inativo"

        AuthService.alterar_status(usuario_db["id"], True)
        assert AuthService.autenticar(usuario_db["email"], "NovaSenhaForte456")


# ---------------------------------------------------------------------------
# TI04 — Exclusão
# ---------------------------------------------------------------------------
class TestTI04Exclusao:
    def test_exclusao_de_ocorrencia_e_cascata_da_regiao(self, cenario, banco_teste):
        with banco_teste.begin() as conexao:
            conexao.execute(text(
                "DELETE FROM ocorrencia_mensal WHERE id = :id"
            ), {"id": cenario["ocorrencias"][(2, "OCORRENCIA")]})
            restantes = conexao.execute(text("""
                SELECT COUNT(*) FROM ocorrencia_mensal
                WHERE regiao_id = :r AND tipo_crime_id = :c
            """), {"r": cenario["regiao_id"], "c": cenario["crime_id"]}).scalar_one()
        assert restantes == 2

        # ON DELETE CASCADE: remover a RA apaga o fato vinculado
        with banco_teste.begin() as conexao:
            conexao.execute(text(
                "DELETE FROM regiao_administrativa WHERE id = :id"
            ), {"id": cenario["regiao_id"]})
            orfaos = conexao.execute(text("""
                SELECT COUNT(*) FROM ocorrencia_mensal WHERE regiao_id = :id
            """), {"id": cenario["regiao_id"]}).scalar_one()
        assert orfaos == 0

        assert DbService().get_estatisticas(
            regioes=[cenario["nome_ra"]], anos=[ANO]
        )["total_ocorrencias"] == 0

    def test_exclusao_de_relatorio_e_do_usuario(self, banco_teste, usuario_db):
        RelatorioService.salvar(
            usuario_id=usuario_db["id"],
            titulo="Relatório descartável",
            dimensao="por_mes",
            tipo_grafico="Linha",
            top_n=10,
        )
        relatorio = RelatorioService.listar(usuario_db["id"])[0]

        RelatorioService.excluir(usuario_db["id"], relatorio["id"])
        assert RelatorioService.listar(usuario_db["id"]) == []
        with pytest.raises(RelatorioError) as erro:
            RelatorioService.excluir(usuario_db["id"], relatorio["id"])
        assert erro.value.codigo == "nao_encontrado"

        # recria e confere a cascata ao remover a conta
        RelatorioService.salvar(
            usuario_id=usuario_db["id"],
            titulo="Relatório em cascata",
            dimensao="por_ano",
            tipo_grafico="Área",
            top_n=5,
        )
        with banco_teste.begin() as conexao:
            conexao.execute(text(
                "DELETE FROM auth.usuario WHERE id = :id"
            ), {"id": usuario_db["id"]})
            restantes = conexao.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM auth.relatorio_salvo WHERE usuario_id = :id) AS relatorios,
                    (SELECT COUNT(*) FROM auth.sessao_usuario WHERE usuario_id = :id) AS sessoes
            """), {"id": usuario_db["id"]}).one()
        assert (restantes.relatorios, restantes.sessoes) == (0, 0)
