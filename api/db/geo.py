"""
Utilitários geoespaciais: conversão entre geometrias Shapely/WKT/GeoJSON.

Usado pelo pipeline de carga (db/load_csv.py) e pelos modelos
(api/db/models.py) para serializar contornos e centroides das RAs.
"""

import json
from typing import Any, Optional

from shapely import wkb
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


def parse_contorno(raw: Any) -> Optional[BaseGeometry]:
    """Converte o valor bruto de um contorno (WKB hex, WKT, GeoJSON dict
    ou string JSON) em uma geometria Shapely. Retorna None se inválido."""
    if raw is None:
        return None
    if isinstance(raw, BaseGeometry):
        return raw
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return wkb.loads(bytes(raw))
    if isinstance(raw, dict):
        return shape(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.startswith("{"):
            return shape(json.loads(text))
        # Formato EWKT do PostGIS: 'SRID=4326;MULTIPOLYGON(...)'
        if ";" in text:
            text = text.split(";", 1)[1].strip()
        # WKB hex (psycopg2/geoalchemy costumam devolver nesse formato)
        try:
            return wkb.loads(text, hex=True)
        except Exception:
            pass
        try:
            return wkb.loads(text)
        except Exception:
            pass
        # WKT como último recurso
        from shapely import from_wkt

        return from_wkt(text)
    return None


def geometry_to_geojson(raw: Any) -> Optional[dict]:
    """Serializa uma geometria (WKB hex / Shapely / GeoJSON) em GeoJSON dict."""
    geom = parse_contorno(raw)
    if geom is None:
        return None
    return mapping(geom)


def centroide_latlon(raw: Any) -> Optional[tuple]:
    """Extrai (latitude, longitude) do centroide de uma geometria."""
    geom = parse_contorno(raw)
    if geom is None:
        return None
    c = geom.centroid
    return (c.y, c.x)
