"""
Rotas para Ocorrências, Mapa de Calor, Coropleto e Estatísticas.

Prioriza dados do PostgreSQL (DbService); cai no fallback CSV/simulado
(DataService) se o banco não estiver acessível.
"""

from typing import List, Optional
from fastapi import APIRouter, Query
from api.services.data_service import DataService
from api.services.db_service import DbService, DbServiceError
from api.services.ingest_crimemap import consolidar

router = APIRouter(prefix="/api", tags=["Ocorrências e Mapa"])
_service = DbService()
_fallback = DataService()


@router.get("/heatmap", summary="Pontos do Mapa de Calor (um por RA, peso = total)")
def obter_pontos_calor(
    regiao: Optional[List[str]] = Query(None),
    natureza: Optional[List[str]] = Query(None),
    eixo: Optional[List[str]] = Query(None, description="Filtrar por Eixo Indicador"),
    ano: Optional[List[int]] = Query(None),
    tipo_registro: str = Query("OCORRENCIA", description="OCORRENCIA ou VITIMA"),
):
    """Retorna `[latitude, longitude, peso]` por RA (um ponto por região,
    peso proporcional ao total de ocorrências nos filtros)."""
    try:
        pontos = _service.get_pontos_calor(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
    except DbServiceError:
        pontos = _fallback.get_pontos_calor(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
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
        top_nat = None  # preenchido abaixo
    except DbServiceError:
        # Fallback: mesmo cálculo do DataService (soma de quantidade por RA)
        dados = _fallback.get_coropleto(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
        online = False
        top_nat = _fallback.get_top_naturezas(
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
    else:
        try:
            top_nat = _service.get_top_naturezas(
                regioes=regiao, naturezas=natureza, eixos=eixo,
                anos=ano, tipo_registro=tipo_registro,
            )
        except DbServiceError:
            top_nat = {}
    return {"online": online, "regioes": dados, "top_naturezas": top_nat}


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
        df = _fallback.filtrar(
            regioes=regiao, naturezas=natureza, eixos=eixo, anos=ano,
            tipo_registro=tipo_registro, termo_busca=busca,
        )
        df = df.sort_values(["ano", "mes", "quantidade"], ascending=[False, True, False]).head(limite)
        meses = ["jan", "fev", "mar", "abr", "mai", "jun",
                 "jul", "ago", "set", "out", "nov", "dez"]
        ocorrencias = [
            {"regiao_administrativa": r["regiao_administrativa"],
             "natureza_crime": r["natureza"],
             "eixo_indicador": r.get("eixo_limpo"),
             "ano": int(r["ano"]),
             "mes": meses[int(r["mes"]) - 1],
             "tipo_registro": r["tipo_registro"],
             "quantidade": int(r["quantidade"])}
            for _, r in df.iterrows()
        ]
        total = len(ocorrencias)
    return {
        "total_encontrado": total,
        "limite_retornado": len(ocorrencias),
        "ocorrencias": ocorrencias,
    }


@router.get("/detalhe-regiao", summary="Detalhe de uma RA (painel ao clicar no mapa)")
def detalhe_regiao(
    regiao: str = Query(..., description="Nome da Região Administrativa"),
    natureza: Optional[List[str]] = Query(None),
    eixo: Optional[List[str]] = Query(None),
    ano: Optional[List[int]] = Query(None),
    tipo_registro: str = Query("OCORRENCIA"),
):
    """KPIs + distribuições (natureza, ano, mês) de UMA RA, sob os filtros atuais do painel.
    Usado pelo painel de detalhe exibido ao clicar em uma região no mapa."""
    try:
        return _service.get_detalhe_regiao(
            regiao=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )
    except DbServiceError:
        return _fallback.get_detalhe_regiao(
            regiao=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )


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
            regioes=regiao, naturezas=natureza, eixos=eixo,
            anos=ano, tipo_registro=tipo_registro,
        )@router.post("/consolidar", summary="Disparar Consolidação das Planilhas SSP-DF (ETL)")
def consolidar_dados():
    """Roda o ingest_crimemap sobre data/raw/ e gera o CSV consolidado
    (mesmo esquema da base real: pivô jan..dez por RA/crime/ano)."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    return consolidar(raiz / "data" / "raw", raiz / "api" / "services" / "output" / "crimemap_consolidadov2.csv")


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
