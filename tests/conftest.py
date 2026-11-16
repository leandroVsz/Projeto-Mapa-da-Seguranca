"""Configuração compartilhada dos testes.

- Torna a raiz do projeto importável.
- Mantém os testes unitários herméticos com um DATABASE_URL dummy.
- Oferece a fixture `banco_teste`, que usa o PostgreSQL real (variável
  TEST_DATABASE_URL ou o `.env` do projeto) para os testes de integração,
  pulando-os automaticamente quando o banco não está acessível.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# SQLite em memória (sem tabelas): qualquer consulta falha instantaneamente
# e a aplicação cai no fallback CSV, sem tentar conexões de rede demoradas.
os.environ.setdefault("DATABASE_URL", "sqlite://")


def _url_banco_real() -> str | None:
    """URL do banco usada pelos testes de integração.

    Precedência: TEST_DATABASE_URL (explícita para a suíte) → DATABASE_URL
    do arquivo `.env` do projeto. O dummy definido acima serve apenas para
    manter os testes unitários longe de qualquer banco real.
    """
    from dotenv import dotenv_values

    url = os.getenv("TEST_DATABASE_URL")
    if url:
        return url
    arquivo_env = ROOT_DIR / ".env"
    if arquivo_env.exists():
        return dotenv_values(arquivo_env).get("DATABASE_URL")
    return None


@pytest.fixture(scope="session")
def banco_teste():
    """Engine do PostgreSQL real, com o SessionLocal dos serviços redirecionado.

    Vários módulos fazem `from api.db.session import SessionLocal` no import,
    então cada um precisa ser re-apontado para a sessão de teste. A fixture
    restaura os valores originais ao final da sessão.

    Se o schema `auth` ainda não existir no banco, ele é criado de forma
    idempotente (mesmo DDL de db/auth_schema.sql) — é o pré-requisito
    documentado no README para login e relatórios salvos.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    url = _url_banco_real()
    if not url:
        pytest.skip("Nenhum PostgreSQL configurado (TEST_DATABASE_URL/.env).")

    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as erro:  # pragma: no cover - depende do ambiente
        engine.dispose()
        pytest.skip(f"PostgreSQL indisponível para testes de integração: {type(erro).__name__}")

    SessaoTeste = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    import api.db.session as sessao_mod
    import api.services.auth_service as auth_mod
    import api.services.db_service as db_mod
    import api.services.relatorio_service as rel_mod

    alvos = (sessao_mod, auth_mod, db_mod, rel_mod)
    originais = [(modulo, modulo.SessionLocal) for modulo in alvos]
    engine_original = sessao_mod.engine

    for modulo in alvos:
        modulo.SessionLocal = SessaoTeste
    sessao_mod.engine = engine

    try:
        # Pré-requisito do subsistema de autenticação (DDL idempotente).
        with engine.connect() as conexao:
            existe_auth = conexao.execute(text(
                "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = 'auth'"
            )).scalar()
        if not existe_auth:  # pragma: no cover - banco novo sem o schema
            auth_mod.AuthService.criar_schema()

        yield engine
    finally:
        for modulo, original in originais:
            modulo.SessionLocal = original
        sessao_mod.engine = engine_original
        engine.dispose()
