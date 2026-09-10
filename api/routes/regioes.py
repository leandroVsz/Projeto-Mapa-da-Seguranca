"""
Rotas para Regiões Administrativas e Filtros.
"""

from fastapi import APIRouter
from api.services.data_service import DataService

router = APIRouter(prefix="/api", tags=["Regiões e Filtros"])
_service = DataService()


@router.get("/regioes", summary="Lista de Regiões Administrativas")
def listar_regioes():
    """Retorna todas as RAs cadastradas com coordenadas e zoom recomendado."""
    return _service.get_regioes()


@router.get("/filtros", summary="Opções de Filtro Disponíveis")
def listar_filtros():
    """Retorna listas únicas de RAs, tipos de crime, anos e períodos disponíveis na base."""
    return _service.get_opcoes_filtros()

