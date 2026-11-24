"""
Consulta da Região Administrativa (RA) por endereço, CEP ou coordenadas.

Fluxo único para as três formas de entrada:

    CEP ──► ViaCEP ──► logradouro/bairro ─┐
    Endereço (texto) ─────────────────────┼─► geocodificação (Nominatim/OSM) ─► (lat, lon)
    Geolocalização do dispositivo ────────┘                                         │
                                                                                    ▼
                                                        RA que contém o ponto (PostGIS)

Para descobrir a RA do ponto, em ordem de preferência:
  1. PostGIS: ST_Intersects(contorno, ponto)            -> "poligono_postgis"
  2. GeoJSON local (data/geo/ra_df.geojson) com Shapely -> "poligono_geojson"
  3. Centroide mais próximo (banco ou JSON local)       -> "centroide_mais_proximo"
     (resultado aproximado, sinalizado com aproximado=True)
"""

from __future__ import annotations

import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import requests
from sqlalchemy import text

from api.db.session import SessionLocal

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
GEOJSON_PATH = ROOT_DIR / "data" / "geo" / "ra_df.geojson"

# Caixa envolvente aproximada do DF (com pequena margem): (mín, máx)
DF_LAT = (-16.08, -15.45)
DF_LON = (-48.35, -47.25)

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# A política de uso do Nominatim exige um User-Agent identificável.
USER_AGENT = os.getenv(
    "GEOCODER_USER_AGENT", "MapaSegurancaDF-UCB/2.0 (projeto academico)"
)
TIMEOUT = float(os.getenv("GEOCODER_TIMEOUT", "8"))
# Política do Nominatim: no máximo 1 requisição por segundo.
PAUSA_ENTRE_CHAMADAS = float(os.getenv("GEOCODER_PAUSA", "1.0"))
# place_rank do Nominatim: >= 26 é rua/edificação; abaixo disso é bairro, cidade etc.
RANK_NIVEL_RUA = 26


class LocalizacaoError(Exception):
    """Erro de negócio da consulta (carrega o status HTTP sugerido)."""

    def __init__(self, mensagem: str, status: int = 422):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


# ----------------------------------------------------------------------
# Validações
# ----------------------------------------------------------------------
def normalizar_cep(cep: str) -> str:
    """Remove máscara e valida: devolve 8 dígitos ou levanta LocalizacaoError."""
    digitos = re.sub(r"\D", "", cep or "")
    if len(digitos) != 8:
        raise LocalizacaoError("CEP inválido: informe 8 dígitos (ex.: 70040-010).")
    return digitos


def dentro_do_df(lat: float, lon: float) -> bool:
    return DF_LAT[0] <= lat <= DF_LAT[1] and DF_LON[0] <= lon <= DF_LON[1]


def _validar_df(lat: float, lon: float) -> None:
    if not dentro_do_df(lat, lon):
        raise LocalizacaoError(
            "A localização informada está fora do Distrito Federal.", status=422
        )


# ----------------------------------------------------------------------
# CEP e geocodificação (serviços externos)
# ----------------------------------------------------------------------
def consultar_cep(cep: str) -> Dict[str, Any]:
    """Consulta o ViaCEP. Devolve logradouro, bairro, localidade e uf."""
    digitos = normalizar_cep(cep)
    try:
        r = requests.get(VIACEP_URL.format(cep=digitos), timeout=TIMEOUT)
        r.raise_for_status()
        dados = r.json()
    except (requests.RequestException, ValueError):
        raise LocalizacaoError(
            "Não foi possível consultar o CEP agora (serviço ViaCEP indisponível).",
            status=503,
        )
    if dados.get("erro"):
        raise LocalizacaoError("CEP não encontrado.", status=404)
    if (dados.get("uf") or "").upper() != "DF":
        raise LocalizacaoError("O CEP informado não pertence ao Distrito Federal.")
    return dados


def geocodificar(consulta: str) -> Optional[Tuple[float, float, str, int]]:
    """Geocodifica um texto com o Nominatim (OpenStreetMap), restrito ao DF.

    Retorna (latitude, longitude, nome_encontrado, place_rank) ou None se nada foi
    achado. O place_rank diz o nível do que foi achado: >= 26 é rua/edificação,
    abaixo disso é só bairro, cidade ou região (o ponto é o "centro" da área).
    """
    params: Dict[str, Any] = {
        "q": consulta,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "br",
        # viewbox = esquerda,topo,direita,base (lon_min,lat_max,lon_max,lat_min)
        "viewbox": f"{DF_LON[0]},{DF_LAT[1]},{DF_LON[1]},{DF_LAT[0]}",
        "bounded": 1,
    }
    try:
        r = requests.get(
            NOMINATIM_URL, params=params,
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
        )
        r.raise_for_status()
        achados = r.json()
    except (requests.RequestException, ValueError):
        raise LocalizacaoError(
            "Não foi possível localizar o endereço agora (serviço de mapas indisponível).",
            status=503,
        )
    if not achados:
        return None
    a = achados[0]
    rank = int(a.get("place_rank", 30))  # sem a informação, assume nível de rua
    return float(a["lat"]), float(a["lon"]), a.get("display_name", consulta), rank


def geocodificar_melhor(
    tentativas: List[Tuple[str, str]],
) -> Optional[Tuple[float, float, str, str]]:
    """Tenta várias formas de escrever o endereço, da mais específica à menos.

    `tentativas` = [(texto, nivel)], com nivel "endereco" ou "bairro".
    Devolve (lat, lon, nome, precisao). Se nenhuma tentativa chegar ao nível de
    rua, devolve a primeira que achou algo, marcada como precisao="bairro"
    (o ponto é o centro do bairro: CEPs diferentes do mesmo bairro caem no mesmo lugar).
    """
    reserva: Optional[Tuple[float, float, str, str]] = None
    for i, (texto, nivel) in enumerate(tentativas):
        if i > 0 and PAUSA_ENTRE_CHAMADAS > 0:
            time.sleep(PAUSA_ENTRE_CHAMADAS)
        achado = geocodificar(texto)
        if not achado:
            continue
        lat, lon, nome, rank = achado
        if nivel == "endereco" and rank >= RANK_NIVEL_RUA:
            return lat, lon, nome, "endereco"
        if reserva is None:
            reserva = (lat, lon, nome, "bairro")
    return reserva


# ----------------------------------------------------------------------
# Ponto -> Região Administrativa
# ----------------------------------------------------------------------
def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _regiao_postgis(lat: float, lon: float) -> Optional[Tuple[str, str]]:
    ponto = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)"
    with SessionLocal() as s:
        nome = s.execute(text(
            "SELECT nome FROM regiao_administrativa "
            f"WHERE contorno IS NOT NULL AND ST_Intersects(contorno, {ponto}) "
            "ORDER BY nome LIMIT 1"
        ), {"lat": lat, "lon": lon}).scalar()
        if nome:
            return nome, "poligono_postgis"
        nome = s.execute(text(
            "SELECT nome FROM regiao_administrativa WHERE centroide IS NOT NULL "
            f"ORDER BY centroide <-> {ponto} LIMIT 1"
        ), {"lat": lat, "lon": lon}).scalar()
        if nome:
            return nome, "centroide_mais_proximo"
    return None


_cache_poligonos: Optional[Dict[str, Dict[str, Any]]] = None


def _regiao_geojson(lat: float, lon: float) -> Optional[Tuple[str, str]]:
    global _cache_poligonos
    if not GEOJSON_PATH.exists():
        return None
    try:
        if _cache_poligonos is None:
            import json
            from db.load_csv import extrair_poligonos_por_nome  # pyright: ignore[reportUnknownVariableType]

            geojson = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
            _cache_poligonos = cast(
                Dict[str, Dict[str, Any]], extrair_poligonos_por_nome(geojson)
            )
        from shapely.geometry import Point

        ponto = Point(lon, lat)
        for nome, dados in sorted(_cache_poligonos.items()):
            if dados["polygon"].intersects(ponto):
                return nome, "poligono_geojson"
    except Exception:
        return None
    return None


def _regiao_centroide(lat: float, lon: float) -> Optional[Tuple[str, str]]:
    from api.services.data_service import DataService

    candidatas: List[Dict[str, Any]] = [
        r for r in DataService().get_regioes()
        if r.get("latitude") is not None and r.get("longitude") is not None
    ]
    if not candidatas:
        return None
    melhor = min(
        candidatas,
        key=lambda r: _haversine_km(lat, lon, r["latitude"], r["longitude"]),
    )
    return melhor["nome"], "centroide_mais_proximo"


def regiao_por_coordenadas(lat: float, lon: float) -> Tuple[str, str]:
    """Devolve (nome_da_RA, método). Levanta LocalizacaoError se fora do DF."""
    _validar_df(lat, lon)
    try:
        achou = _regiao_postgis(lat, lon)
        if achou:
            return achou
    except Exception:
        pass  # banco offline: segue para os fallbacks
    achou = _regiao_geojson(lat, lon) or _regiao_centroide(lat, lon)
    if not achou:
        raise LocalizacaoError("Não foi possível determinar a região.", status=503)
    return achou


# ----------------------------------------------------------------------
# Orquestração
# ----------------------------------------------------------------------
def localizar_regiao(
    cep: Optional[str] = None,
    endereco: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolve a RA a partir de UMA das três entradas (coordenadas > CEP > endereço)."""
    tem_coord = latitude is not None and longitude is not None
    if (latitude is None) != (longitude is None):
        raise LocalizacaoError("Informe latitude e longitude juntas.")
    if not (tem_coord or (cep and cep.strip()) or (endereco and endereco.strip())):
        raise LocalizacaoError("Informe um CEP, um endereço ou as coordenadas.")

    precisao: str
    encontrado: Optional[str] = None

    if latitude is not None and longitude is not None:
        entrada, consulta, precisao = "coordenadas", f"{latitude}, {longitude}", "coordenadas"
        lat, lon = float(latitude), float(longitude)
    elif cep and cep.strip():
        entrada, consulta = "cep", normalizar_cep(cep)
        via = consultar_cep(cep)
        logradouro = (via.get("logradouro") or "").strip()
        bairro = (via.get("bairro") or "").strip()
        cidade = (via.get("localidade") or "Brasília").strip()
        tentativas: List[Tuple[str, str]] = []
        if logradouro:
            tentativas.append((f"{logradouro}, {bairro}, {cidade}, DF", "endereco"))
            tentativas.append((f"{logradouro}, {cidade}, DF", "endereco"))
        if bairro:
            tentativas.append((f"{bairro}, {cidade}, DF", "bairro"))
        achado = geocodificar_melhor(tentativas)
        if not achado:
            raise LocalizacaoError(
                "Não foi possível obter a posição desse CEP no mapa.", status=404
            )
        lat, lon, encontrado, precisao = achado
    else:
        entrada, consulta = "endereco", (endereco or "").strip()
        achado = geocodificar_melhor([(f"{consulta}, Distrito Federal, Brasil", "endereco")])
        if not achado:
            raise LocalizacaoError("Endereço não encontrado no Distrito Federal.", status=404)
        lat, lon, encontrado, precisao = achado

    regiao, metodo = regiao_por_coordenadas(lat, lon)
    return {
        "entrada": entrada,
        "consulta": consulta,
        "endereco_encontrado": encontrado,
        "latitude": lat,
        "longitude": lon,
        "regiao": regiao,
        "metodo": metodo,
        "precisao": precisao,
        "aproximado": metodo == "centroide_mais_proximo" or precisao == "bairro",
    }
