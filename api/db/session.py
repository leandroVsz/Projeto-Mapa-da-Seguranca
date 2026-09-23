"""
Sessão do SQLAlchemy para o banco PostgreSQL/PostGIS do CrimeMap DF.

A URL de conexão vem da variável de ambiente DATABASE_URL. Caso não
esteja definida, usa o padrão do docker-compose (.env.example).

Exemplo:
    DATABASE_URL=postgresql+psycopg2://crimemap:crimemap@localhost:5432/crimemap
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Garante que a raiz do projeto está no path e carrega o .env (se existir)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://crimemap:crimemap@localhost:5432/crimemap",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """Retorna uma nova sessão SQLAlchemy (caller fecha)."""
    return SessionLocal()
