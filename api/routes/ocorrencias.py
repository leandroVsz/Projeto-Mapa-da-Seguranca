"""
Rotas para Ocorrências, Mapa de Calor, Coropleto e Estatísticas.

Prioriza dados do PostgreSQL (DbService); cai no fallback CSV/simulado
(DataService) se o banco não estiver acessível.
"""

from typing import List, Optional
from fastapi import APIRouter, Query
from api.services.data_service import DataService
from api.services.db_service import DbService, DbServiceError
from api.services.data_ingestion import consolidar_arquivos_por_cidade

router = APIRouter(prefix="/api", tags=["Ocorrências e Mapa"])
_service = DbService()
_fallback = DataService()


@router.get("/heatmap", summary="Pontos do Mapa de Calor (centroides ponderados)")
def obter_pontos_calor(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    eixo: Optional[List[str]] = Query(None, description="Filtrar por Eixo Indicador"),
    ano: Optional[List[int]] = Query(None),
    tipo_registro: str = Query("OCORRENCIA", description="OCORRENCIA ou VITIMA"),
):
    """Retorna `[latitude, longitude, peso]` por centroide de RA, ponderado
    pela soma de ocorrências filtradas."""
    try:
        pontos = _service.get_pontos_calor(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
    except DbServiceError:
        pontos = _fallback.get_pontos_calor(
            regioes=regiao, naturezas=natureza, anos=ano,
        )
    return {"total_pontos": len(pontos), "pontos": pontos}


@router.get("/coropleto", summary="Intensidade por RA (para mapa coropleto)")
def obter_coropleto(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    eixo: Optional[List[str]] = Query(None),
    ano: Optional[List[int]] = Query(None),
    tipo_registro: str = Query("OCORRENCIA"),
):
    """Retorna `[{nome, total}]` por RA — intensidade para pintar o polígono."""
    try:
        dados = _service.get_coropleto(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
        online = True
    except DbServiceError:
        # Fallback: calcula por RA a partir dos dados simulados (aproximação)
        df = _fallback.filtrar_ocorrencias(regioes=regiao, naturezas=natureza, anos=ano)
        dados = [
            {"nome": nome, "total": int(total)}
            for nome, total in df["regiao_administrativa"].value_counts().items()
        ]
        online = False
    return {"online": online, "regioes": dados}


@router.get("/ocorrencias", summary="Listagem de Ocorrências Agregadas (RA/crime/mês)")
def listar_ocorrencias(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    eixo: Optional[List[str]] = Query(None),
    ano: Optional[List[int]] = Query(None),
    tipo_registro: str = Query("OCORRENCIA"),
    busca: Optional[str] = Query(None, description="Busca textual em RA ou crime"),
    limite: int = Query(500, ge=1, le=5000),
):
    """Retorna registros agregados por RA/crime/ano/mês com filtros combinados."""
    try:
        ocorrencias = _service.listar_ocorrencias(
            regioes=regiao, naturezas=natureza, eixos=eixo, anos=ano,
            tipo_registro=tipo_registro, termo_busca=busca, limite=limite,
        )
        total = len(ocorrencias)
    except DbServiceError:
        df = _fallback.filtrar_ocorrencias(
            regioes=regiao, naturezas=natureza, anos=ano, termo_busca=busca,
        ).head(limite)
        ocorrencias = df.to_dict(orient="records")
        total = len(ocorrencias)
    return {
        "total_encontrado": total,
        "limite_retornado": len(ocorrencias),
        "ocorrencias": ocorrencias,
    }


@router.get("/stats", summary="Indicadores e KPIs Estatísticos")
def obter_estatisticas(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    eixo: Optional[List[str]] = Query(None),
    ano: Optional[List[int]] = Query(None),
    tipo_registro: str = Query("OCORRENCIA"),
):
    """Retorna métricas agregadas: total, RA mais crítica, crime mais incidente e distribuições."""
    try:
        return _service.get_estatisticas(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
    except DbServiceError:
        return _fallback.get_estatisticas(
            regioes=regiao, naturezas=natureza, anos=ano,
        )


@router.post("/consolidar", summary="Disparar Consolidação de Arquivos Brutos (ETL)")
def consolidar_dados():
    """Executa o pipeline que une múltiplos anos de cada cidade em data/raw/."""
    return consolidar_arquivos_por_cidade()


@router.post("/carga-db", summary="Carregar CSV consolidado + contornos no PostgreSQL")
def carga_db():
    """Executa o pipeline db/load_csv.py: dimensões + fato + polígonos (idempotente)."""
    import importlib

    try:
        modulo = importlib.import_module("db.load_csv")
        importlib.reload(modulo)
        resumo = modulo.carregar_base()
        return {"status": "sucesso", "resumo": resumo}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)[:300]}
