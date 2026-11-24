"""
Rota de consulta da Região Administrativa por CEP, endereço ou coordenadas
(requisito 4 do projeto).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.services.localizacao_service import LocalizacaoError, localizar_regiao

router = APIRouter(prefix="/api", tags=["Localização"])


@router.get("/localizar", summary="Descobre a RA por CEP, endereço ou geolocalização")
def localizar(
    cep: Optional[str] = Query(None, description="CEP do DF, com ou sem hífen"),
    endereco: Optional[str] = Query(None, min_length=3, description="Endereço em texto livre"),
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="Ex.: do GPS do dispositivo"),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
):
    """Informe **uma** das formas de entrada (coordenadas têm prioridade, depois CEP,
    depois endereço). Devolve a RA que contém o ponto e como ela foi determinada."""
    try:
        return localizar_regiao(
            cep=cep, endereco=endereco, latitude=latitude, longitude=longitude
        )
    except LocalizacaoError as e:
        raise HTTPException(status_code=e.status, detail=e.mensagem)
