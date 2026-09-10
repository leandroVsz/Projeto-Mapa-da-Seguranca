"""
Rotas para Ocorrências Criminais, Mapa de Calor e Estatísticas.
"""

from typing import List, Optional
from fastapi import APIRouter, Query
from api.services.data_service import DataService
from api.services.data_ingestion import consolidar_arquivos_por_cidade

router = APIRouter(prefix="/api", tags=["Ocorrências e Mapa de Calor"])
_service = DataService()


@router.get("/heatmap", summary="Pontos do Mapa de Calor")
def obter_pontos_calor(
    regiao: Optional[List[str]] = Query(None, description="Filtrar por Região Administrativa"),
    natureza: Optional[List[str]] = Query(None, description="Filtrar por Natureza do Crime"),
    ano: Optional[List[int]] = Query(None, description="Filtrar por Ano"),
    periodo: Optional[List[str]] = Query(None, description="Filtrar por Período do Dia"),
    ponderar: bool = Query(True, description="Ponderar intensidade pela gravidade da infração"),
):
    """
    Retorna pontos geográficos no formato `[[latitude, longitude, peso], ...]`
    adequados para visualização de densidade e mapa de calor.
    """
    pontos = _service.get_pontos_calor(
        regioes=regiao,
        naturezas=natureza,
        anos=ano,
        periodos=periodo,
        ponderar_severidade=ponderar,
    )
    return {
        "total_pontos": len(pontos),
        "pontos": pontos,
    }


@router.get("/ocorrencias", summary="Listagem de Ocorrências Filtradas")
def listar_ocorrencias(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    ano: Optional[List[int]] = Query(None),
    periodo: Optional[List[str]] = Query(None),
    busca: Optional[str] = Query(None, description="Busca textual em logradouro, crime ou RA"),
    limite: int = Query(500, ge=1, le=5000, description="Limite máximo de registros"),
):
    """Retorna lista tabular de ocorrências criminais com suporte a filtros combinados."""
    df = _service.filtrar_ocorrencias(
        regioes=regiao,
        naturezas=natureza,
        anos=ano,
        periodos=periodo,
        termo_busca=busca,
    )
    df_resultado = df.head(limite)
    return {
        "total_encontrado": len(df),
        "limite_retornado": len(df_resultado),
        "ocorrencias": df_resultado.to_dict(orient="records"),
    }


@router.get("/stats", summary="Indicadores e KPIs Estatísticos")
def obter_estatisticas(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    ano: Optional[List[int]] = Query(None),
    periodo: Optional[List[str]] = Query(None),
):
    """Retorna métricas agregadas: total, RA mais crítica, crime mais incidente e distribuições."""
    return _service.get_estatisticas(
        regioes=regiao,
        naturezas=natureza,
        anos=ano,
        periodos=periodo,
    )


@router.post("/consolidar", summary="Disparar Consolidação de Arquivos Brutos (ETL)")
def consolidar_dados():
    """
    Executa o pipeline que une múltiplos anos de cada cidade presente em data/raw/
    e gera a base consolidada mestre.
    """
    resultado = consolidar_arquivos_por_cidade()
    _service.carregar_dados(forcar_recarga=True)
    return {
        "status": "sucesso",
        "mensagem": "Pipeline de consolidação executado com sucesso.",
        "resultado": resultado,
    }

