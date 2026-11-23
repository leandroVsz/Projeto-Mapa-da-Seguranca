"""
Rotas para Regiões Administrativas e Filtros.

Prioriza dados do PostgreSQL (DbService); cai no fallback CSV/simulado
(DataService) se o banco não estiver acessível.
"""

from fastapi import APIRouter, Response
from api.services.cache_ttl import get_or_set
from api.services.data_service import DataService
from api.services.db_service import DbService, DbServiceError

router = APIRouter(prefix="/api", tags=["Regiões e Filtros"])
_service = DbService()
_fallback = DataService()

# Contornos e opções de filtro só mudam numa carga/ETL: cache curto em
# memória evita que cada ação do dashboard pague o custo de ir ao banco
# (e de serializar ~340 KB de GeoJSON) de novo.
_CACHE_SEGUNDOS = 300


def _contornos():
    try:
        return _service.get_regioes()
    except DbServiceError:
        return _fallback.get_regioes()


def _opcoes():
    try:
        return _service.get_opcoes_filtros()
    except DbServiceError:
        return _fallback.get_opcoes_filtros()


@router.get("/regioes", summary="Lista de Regiões Administrativas (com contornos GeoJSON)")
def listar_regioes(response: Response):
    """Retorna todas as RAs do banco com contorno GeoJSON e centroide."""
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_SEGUNDOS}"
    return get_or_set("regioes", _contornos, ttl=_CACHE_SEGUNDOS)


@router.get("/filtros", summary="Opções de Filtro Disponíveis (do banco)")
def listar_filtros(response: Response):
    """Retorna listas únicas de RAs, naturezas, eixos indicadores e anos."""
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_SEGUNDOS}"
    return get_or_set("filtros", _opcoes, ttl=_CACHE_SEGUNDOS)
