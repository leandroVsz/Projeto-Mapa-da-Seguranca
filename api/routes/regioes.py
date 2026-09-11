"""
Rotas para Regiões Administrativas e Filtros.

Prioriza dados do PostgreSQL (DbService); cai no fallback CSV/simulado
(DataService) se o banco não estiver acessível.
"""

from fastapi import APIRouter
from api.services.data_service import DataService
from api.services.db_service import DbService, DbServiceError

router = APIRouter(prefix="/api", tags=["Regiões e Filtros"])
_service = DbService()
_fallback = DataService()


@router.get("/regioes", summary="Lista de Regiões Administrativas (com contornos GeoJSON)")
def listar_regioes():
    """Retorna todas as RAs do banco com contorno GeoJSON e centroide."""
    try:
        return _service.get_regioes()
    except DbServiceError:
        return _fallback.get_regioes()


@router.get("/filtros", summary="Opções de Filtro Disponíveis (do banco)")
def listar_filtros():
    """Retorna listas únicas de RAs, naturezas, eixos indicadores e anos."""
    try:
        return _service.get_opcoes_filtros()
    except DbServiceError:
        return _fallback.get_opcoes_filtros()
