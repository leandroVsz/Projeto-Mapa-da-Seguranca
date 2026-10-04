"""Configuração compartilhada: path do projeto e DATABASE_URL dummy.

Os testes unitários não tocam no banco; o DATABASE_URL dummy evita que o
.env local (eventualmente apontando para um banco remoto) seja usado.
"""
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://crimemap:crimemap@localhost:5432/crimemap",
)
