"""
Serviço de consulta aos dados reais no PostgreSQL/PostGIS.

Substitui a agregação em pandas por consultas SQL (GROUP BY) para os
endpoints do backend. Contratos mantidos próximos ao DataService para
minimizar quebra no frontend.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.db.session import SessionLocal


class DbServiceError(Exception):
    """Banco indisponível ou erro de consulta."""


def _query(fn, *args, **kwargs):
    """Executa uma função que usa o banco; converte qualquer erro de
    conexão/SQL em DbServiceError para o fallback do router funcionar."""
    try:
        return fn(*args, **kwargs)
    except (SQLAlchemyError, OSError) as e:
        raise DbServiceError(str(e)[:300]) from e


def db_query(fn):
    """Decorator: aplica _query a métodos de instância do DbService."""
    import functools

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        return _query(fn, self, *args, **kwargs)

    return wrapper


def _fmt_list(valores: Optional[List[Any]]) -> Optional[List[Any]]:
    return valores if valores else None


class DbService:
    """Consultas agregadas no banco. Todas lançam DbServiceError se o
    banco não estiver acessível (caller decide cair no fallback)."""

    # ------------------------------------------------------------------
    # Filtros comuns
    # ------------------------------------------------------------------
    @staticmethod
    def _where(
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        tipo_registro: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        params = params if params is not None else {}
        cond = []
        if regioes:
            cond.append("r.nome = ANY(:regioes)")
            params["regioes"] = list(regioes)
        if naturezas:
            cond.append("t.nome = ANY(:naturezas)")
            params["naturezas"] = list(naturezas)
        if eixos:
            cond.append("t.eixo_indicador = ANY(:eixos)")
            params["eixos"] = list(eixos)
        if anos:
            cond.append("f.ano = ANY(:anos)")
            params["anos"] = [int(a) for a in anos]
        if tipo_registro:
            cond.append("f.tipo_registro = :tipo_registro")
            params["tipo_registro"] = tipo_registro
        return ("WHERE " + " AND ".join(cond)) if cond else ""

    # ------------------------------------------------------------------
    # Regiões (com GeoJSON do contorno)
    # ------------------------------------------------------------------
    @db_query
    def get_regioes(self) -> List[Dict[str, Any]]:
        from api.db.geo import geometry_to_geojson

        with SessionLocal() as s:
            rows = s.execute(text(
                "SELECT id, nome, codigo, contorno, centroide FROM regiao_administrativa ORDER BY nome"
            )).all()

        out = []
        for r in rows:
            contorno = geometry_to_geojson(r[3])
            centroide = geometry_to_geojson(r[4])
            lat = lon = None
            if centroide:
                coords = centroide.get("coordinates") or [None, None]
                lon, lat = coords[0], coords[1]
            out.append({
                "id": r[0], "nome": r[1], "codigo": r[2],
                "contorno": contorno,
                "latitude": lat, "longitude": lon,
            })
        return out

    # ------------------------------------------------------------------
    # Filtros disponíveis
    # ------------------------------------------------------------------
    @db_query
    def get_opcoes_filtros(self) -> Dict[str, List[Any]]:
        with SessionLocal() as s:
            regioes = [r[0] for r in s.execute(text(
                "SELECT DISTINCT r.nome FROM ocorrencia_mensal f "
                "JOIN regiao_administrativa r ON r.id = f.regiao_id ORDER BY 1"
            )).all()]
            naturezas = [r[0] for r in s.execute(text(
                "SELECT DISTINCT t.nome FROM ocorrencia_mensal f "
                "JOIN tipo_crime t ON t.id = f.tipo_crime_id ORDER BY 1"
            )).all()]
            eixos = [r[0] for r in s.execute(text(
                "SELECT DISTINCT t.eixo_indicador FROM ocorrencia_mensal f "
                "JOIN tipo_crime t ON t.id = f.tipo_crime_id ORDER BY 1"
            )).all()]
            anos = [int(r[0]) for r in s.execute(text(
                "SELECT DISTINCT ano FROM ocorrencia_mensal ORDER BY 1 DESC"
            )).all()]
        return {"regioes": regioes, "naturezas": naturezas,
                "eixos": eixos, "anos": anos,
                "periodos": []}

    # ------------------------------------------------------------------
    # Coropleto: intensidade por RA
    # ------------------------------------------------------------------
    @db_query
    def get_coropleto(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> List[Dict[str, Any]]:
        with SessionLocal() as s:
            params: Dict[str, Any] = {}
            where = self._where(regioes, naturezas, eixos, anos, tipo_registro, params)
            rows = s.execute(text(f"""
                SELECT ra.nome, COALESCE(agg.total, 0) AS total
                FROM regiao_administrativa ra
                LEFT JOIN (
                    SELECT f.regiao_id, SUM(f.quantidade) AS total
                    FROM ocorrencia_mensal f
                    JOIN regiao_administrativa r ON r.id = f.regiao_id
                    JOIN tipo_crime t ON t.id = f.tipo_crime_id
                    {where}
                    GROUP BY f.regiao_id
                ) agg ON agg.regiao_id = ra.id
                ORDER BY total DESC
            """), params).all()
        return [{"nome": r[0], "total": int(r[1])} for r in rows]

    # ------------------------------------------------------------------
    # Top naturezas por RA (tooltip do coropleto)
    # ------------------------------------------------------------------
    @db_query
    def get_top_naturezas(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Mapa RA → [{natureza, total}] ordenado por total desc,
        sob os mesmos filtros do coropleto."""
        with SessionLocal() as s:
            params: Dict[str, Any] = {}
            where = self._where(regioes, naturezas, eixos, anos, tipo_registro, params)
            rows = s.execute(text(f"""
                SELECT r.nome, t.nome, SUM(f.quantidade) AS q
                FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where}
                GROUP BY r.nome, t.nome
                ORDER BY r.nome, q DESC
            """), params).all()
        top: Dict[str, List[Dict[str, Any]]] = {}
        for ra, nat, q in rows:
            if int(q) <= 0:
                continue
            top.setdefault(ra, []).append({"natureza": nat, "total": int(q)})
        return top

    # ------------------------------------------------------------------
    # Heatmap: um ponto por RA, peso = total
    # ------------------------------------------------------------------
    @db_query
    def get_pontos_calor(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> List[List[float]]:
        from api.db.geo import geometry_to_geojson

        with SessionLocal() as s:
            params: Dict[str, Any] = {}
            where = self._where(regioes, naturezas, eixos, anos, tipo_registro, params)
            rows = s.execute(text(f"""
                SELECT r.centroide, SUM(f.quantidade) AS total
                FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                {where}
                {'AND' if where else 'WHERE'} r.nome <> 'Distrito Federal'
                GROUP BY r.centroide, r.nome
                HAVING SUM(f.quantidade) > 0
            """), params).all()

        max_total = max((int(r[1]) for r in rows), default=0) or 1
        pontos = []
        for r in rows:
            geo = geometry_to_geojson(r[0])
            if not geo:
                continue
            lon, lat = geo["coordinates"]
            # peso normalizado 0.2–1.0 para o heatmap
            peso = 0.2 + 0.8 * (int(r[1]) / max_total)
            pontos.append([round(float(lat), 6), round(float(lon), 6), round(peso, 3)])
        return pontos

    # ------------------------------------------------------------------
    # Listagem detalhada (agregada por RA/crime/ano/mês)
    # ------------------------------------------------------------------
    @db_query
    def listar_ocorrencias(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
        termo_busca: Optional[str] = None,
        limite: int = 500,
    ) -> List[Dict[str, Any]]:
        with SessionLocal() as s:
            params: Dict[str, Any] = {"limite": limite}
            where = self._where(regioes, naturezas, eixos, anos, tipo_registro, params)
            if termo_busca:
                where += (" AND " if where else "WHERE ")
                where += "(r.nome ILIKE :busca OR t.nome ILIKE :busca)"
                params["busca"] = f"%{termo_busca}%"

            rows = s.execute(text(f"""
                SELECT r.nome AS ra, t.nome AS natureza, t.eixo_indicador,
                       f.ano, f.mes, f.tipo_registro, f.quantidade
                FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where}
                ORDER BY f.ano DESC, f.mes, f.quantidade DESC
                LIMIT :limite
            """), params).all()

        meses = ["jan", "fev", "mar", "abr", "mai", "jun",
                 "jul", "ago", "set", "out", "nov", "dez"]
        return [{
            "regiao_administrativa": r[0],
            "natureza_crime": r[1],
            "eixo_indicador": r[2],
            "ano": int(r[3]),
            "mes": meses[r[4] - 1],
            "tipo_registro": r[5],
            "quantidade": int(r[6]),
        } for r in rows]

    # ------------------------------------------------------------------
    # Estatísticas / KPIs
    # ------------------------------------------------------------------
    @db_query
    def get_estatisticas(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> Dict[str, Any]:
        with SessionLocal() as s:
            params: Dict[str, Any] = {}
            where = self._where(regioes, naturezas, eixos, anos, tipo_registro, params)

            total = int(s.execute(text(f"""
                SELECT COALESCE(SUM(f.quantidade), 0) FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where}
            """), params).scalar() or 0)

            if total == 0:
                return {"total_ocorrencias": 0, "ra_mais_afetada": "N/A",
                        "crime_mais_frequente": "N/A", "por_natureza": {},
                        "por_regiao": {}, "por_ano": {}, "por_mes": {}}

            ra = s.execute(text(f"""
                SELECT r.nome, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} {'AND' if where else 'WHERE'} r.nome <> 'Distrito Federal'
                GROUP BY r.nome ORDER BY q DESC LIMIT 1
            """), params).first()

            crime = s.execute(text(f"""
                SELECT t.nome, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} GROUP BY t.nome ORDER BY q DESC LIMIT 1
            """), params).first()

            por_regiao = {r[0]: int(r[1]) for r in s.execute(text(f"""
                SELECT r.nome, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} {'AND' if where else 'WHERE'} r.nome <> 'Distrito Federal'
                GROUP BY r.nome ORDER BY q DESC
            """), params).all()}

            por_natureza = {r[0]: int(r[1]) for r in s.execute(text(f"""
                SELECT t.nome, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} GROUP BY t.nome ORDER BY q DESC
            """), params).all()}

            por_ano = {int(r[0]): int(r[1]) for r in s.execute(text(f"""
                SELECT f.ano, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} GROUP BY f.ano ORDER BY f.ano
            """), params).all()}

            por_mes = {int(r[0]): int(r[1]) for r in s.execute(text(f"""
                SELECT f.mes, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} GROUP BY f.mes ORDER BY f.mes
            """), params).all()}

        return {
            "total_ocorrencias": total,
            "ra_mais_afetada": ra[0] if ra else "N/A",
            "crime_mais_frequente": crime[0] if crime else "N/A",
            "por_natureza": por_natureza,
            "por_regiao": por_regiao,
            "por_ano": por_ano,
            "por_mes": por_mes,
        }

    # ------------------------------------------------------------------
    # Detalhe de uma RA (painel ao clicar no mapa)
    # ------------------------------------------------------------------
    @db_query
    def get_detalhe_regiao(
        self,
        regiao: str,
        naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> Dict[str, Any]:
        """KPIs e distribuições de uma RA, sob os filtros do painel."""
        with SessionLocal() as s:
            params: Dict[str, Any] = {}
            where = self._where(None, naturezas, eixos, anos, tipo_registro, params)
            params["ra"] = regiao
            where_ra = ("AND " if where else "") + "r.nome = :ra"

            total = int(s.execute(text(f"""
                SELECT COALESCE(SUM(f.quantidade), 0) FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} {where_ra}
            """), params).scalar() or 0)

            por_natureza = {r[0]: int(r[1]) for r in s.execute(text(f"""
                SELECT t.nome, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} {where_ra}
                GROUP BY t.nome ORDER BY q DESC
            """), params).all()}

            por_ano = {int(r[0]): int(r[1]) for r in s.execute(text(f"""
                SELECT f.ano, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} {where_ra}
                GROUP BY f.ano ORDER BY f.ano
            """), params).all()}

            por_mes = {int(r[0]): int(r[1]) for r in s.execute(text(f"""
                SELECT f.mes, SUM(f.quantidade) q FROM ocorrencia_mensal f
                JOIN regiao_administrativa r ON r.id = f.regiao_id
                JOIN tipo_crime t ON t.id = f.tipo_crime_id
                {where} {where_ra}
                GROUP BY f.mes ORDER BY f.mes
            """), params).all()}

        return {
            "regiao": regiao,
            "total_ocorrencias": total,
            "por_natureza": por_natureza,
            "por_ano": por_ano,
            "por_mes": por_mes,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        try:
            with SessionLocal() as s:
                total = int(s.execute(text(
                    "SELECT COUNT(*) FROM ocorrencia_mensal"
                )).scalar() or 0)
                regioes = int(s.execute(text(
                    "SELECT COUNT(*) FROM regiao_administrativa"
                )).scalar() or 0)
                crimes = int(s.execute(text(
                    "SELECT COUNT(*) FROM tipo_crime"
                )).scalar() or 0)
                com_contorno = int(s.execute(text(
                    "SELECT COUNT(*) FROM regiao_administrativa WHERE contorno IS NOT NULL"
                )).scalar() or 0)
            return {"db_online": True, "total_registros": total,
                    "total_regioes": regioes, "com_contorno": com_contorno,
                    "total_crimes": crimes}
        except SQLAlchemyError as e:
            return {"db_online": False, "erro": str(e)[:200]}
