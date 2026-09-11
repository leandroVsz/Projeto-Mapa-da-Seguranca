"""
Modelos declarativos (SQLAlchemy) das tabelas do CrimeMap DF.

Espelham o schema em db/schema.sql:
  - regiao_administrativa  (dimensão geográfica, com PostGIS)
  - tipo_crime             (dimensão de naturezas/eixos)
  - ocorrencia_mensal      (fato: contagens por RA/crime/ano/mês)
"""

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RegiaoAdministrativa(Base):
    __tablename__ = "regiao_administrativa"

    id = Column(Integer, primary_key=True)
    nome = Column(String(120), unique=True, nullable=False)
    codigo = Column(Integer, unique=True, nullable=False)
    contorno = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326))
    centroide = Column(Geometry(geometry_type="POINT", srid=4326))

    def to_dict(self) -> dict:
        from api.db.geo import geometry_to_geojson

        return {
            "id": self.id,
            "nome": self.nome,
            "codigo": self.codigo,
            "contorno": geometry_to_geojson(self.contorno),
            "centroide": geometry_to_geojson(self.centroide),
        }


class TipoCrime(Base):
    __tablename__ = "tipo_crime"

    id = Column(Integer, primary_key=True)
    nome = Column(String(160), unique=True, nullable=False)
    eixo_indicador = Column(String(160), nullable=False)
    descricao = Column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "eixo_indicador": self.eixo_indicador,
            "descricao": self.descricao,
        }


class OcorrenciaMensal(Base):
    __tablename__ = "ocorrencia_mensal"
    __table_args__ = (
        UniqueConstraint(
            "regiao_id",
            "tipo_crime_id",
            "ano",
            "mes",
            "tipo_registro",
            name="uq_ocorrencia_mensal",
        ),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_ocorrencia_mes"),
        CheckConstraint(
            "tipo_registro IN ('OCORRENCIA', 'VITIMA')", name="ck_ocorrencia_tipo_registro"
        ),
    )

    id = Column(BigInteger, primary_key=True)
    regiao_id = Column(
        Integer, ForeignKey("regiao_administrativa.id", ondelete="CASCADE"), nullable=False
    )
    tipo_crime_id = Column(
        Integer, ForeignKey("tipo_crime.id", ondelete="CASCADE"), nullable=False
    )
    ano = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)
    tipo_registro = Column(String(20), nullable=False, default="OCORRENCIA")
    quantidade = Column(Integer, nullable=False, default=0)
