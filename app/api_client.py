"""
Cliente HTTP da API REST (FastAPI), com fallback transparente para o
DataService quando a API está offline.
"""

from typing import Any, Dict, List, Optional

import requests
from pathlib import Path
import sys

# Garante path para import do fallback local
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from api.services.data_service import DataService

DEFAULT_API_URL = "http://localhost:8000"


class ApiClient:
    def __init__(self, base_url: Optional[str] = None):
        # Lido em tempo de chamada: permite que api/embedded.py redirecione
        # a porta em runtime (API embutida no deploy em nuvem).
        self.base_url = (base_url or DEFAULT_API_URL).rstrip("/")
        self._fallback_service = DataService()
        self._api_online = None
        self._ultima_tentativa = 0.0

    def check_health(self) -> Dict[str, Any]:
        """Verifica se a API FastAPI está ativa."""
        try:
            res = requests.get(f"{self.base_url}/api/health", timeout=1.5)
            if res.status_code == 200:
                self._api_online = True
                return {"online": True, "data": res.json()}
        except Exception:
            pass

        self._api_online = False
        return {"online": False, "data": None}

    def is_online(self) -> bool:
        if self._api_online is None:
            self.check_health()
        return bool(self._api_online)

    def _tentar_api_online_novamente(self) -> None:
        """Re-tenta conectar (no máx. a cada 10s) se a API estava offline —
        cobre o caso da API subir depois do app (ex: API embutida no deploy)."""
        if self._api_online is False:
            import time

            agora = time.monotonic()
            if agora - self._ultima_tentativa > 10.0:
                self._ultima_tentativa = agora
                self.check_health()

    def get_regioes(self) -> List[Dict[str, Any]]:
        """Busca lista de Regiões Administrativas (com contornos, se houver banco)."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                res = requests.get(f"{self.base_url}/api/regioes", timeout=2.5)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return self._fallback_service.get_regioes()

    def get_filtros(self) -> Dict[str, List[Any]]:
        """Busca opções de preenchimento dos filtros."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                res = requests.get(f"{self.base_url}/api/filtros", timeout=2.5)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return self._fallback_service.get_opcoes_filtros()

    def get_coropleto(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Busca intensidade por RA + top naturezas (tooltip) do coropleto."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                params = {}
                if regioes:
                    params["regiao"] = regioes
                if naturezas:
                    params["natureza"] = naturezas
                if eixos:
                    params["eixo"] = eixos
                if anos:
                    params["ano"] = anos
                res = requests.get(f"{self.base_url}/api/coropleto", params=params, timeout=4.0)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return {
            "online": False,
            "regioes": self._fallback_service.get_coropleto(
                regioes=regioes, naturezas=naturezas, eixos=eixos, anos=anos,
            ),
            "top_naturezas": self._fallback_service.get_top_naturezas(
                regioes=regioes, naturezas=naturezas, eixos=eixos, anos=anos,
            ),
        }

    def get_heatmap(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
    ) -> List[List[float]]:
        """Busca pontos do mapa de calor (um por RA, peso = total da RA)."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                params = {}
                if regioes:
                    params["regiao"] = regioes
                if naturezas:
                    params["natureza"] = naturezas
                if eixos:
                    params["eixo"] = eixos
                if anos:
                    params["ano"] = anos
                res = requests.get(f"{self.base_url}/api/heatmap", params=params, timeout=4.0)
                if res.status_code == 200:
                    return res.json().get("pontos", [])
            except Exception:
                pass
        return self._fallback_service.get_pontos_calor(
            regioes=regioes, naturezas=naturezas, eixos=eixos, anos=anos,
        )

    def get_detalhe_regiao(
        self,
        regiao: str,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """KPIs e distribuições de UMA RA sob os filtros atuais.
        Usado no painel de detalhe ao clicar numa região do mapa."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                params = {"regiao": regiao}
                if naturezas:
                    params["natureza"] = naturezas
                if eixos:
                    params["eixo"] = eixos
                if anos:
                    params["ano"] = anos
                res = requests.get(f"{self.base_url}/api/detalhe-regiao", params=params, timeout=4.0)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return self._fallback_service.get_detalhe_regiao(
            regiao=regiao, naturezas=naturezas, eixos=eixos, anos=anos,
        )

    def get_stats(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Busca estatísticas e indicadores agregados."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                params = {}
                if regioes:
                    params["regiao"] = regioes
                if naturezas:
                    params["natureza"] = naturezas
                if eixos:
                    params["eixo"] = eixos
                if anos:
                    params["ano"] = anos
                res = requests.get(f"{self.base_url}/api/stats", params=params, timeout=3.0)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return self._fallback_service.get_estatisticas(
            regioes=regioes, naturezas=naturezas, eixos=eixos, anos=anos,
        )

    def get_ocorrencias(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        busca: Optional[str] = None,
        limite: int = 500,
    ) -> List[Dict[str, Any]]:
        """Busca listagem filtrada de ocorrências agregadas RA/crime/ano/mês."""
        self._tentar_api_online_novamente()
        if self.is_online():
            try:
                params = {"limite": limite}
                if regioes:
                    params["regiao"] = regioes
                if naturezas:
                    params["natureza"] = naturezas
                if eixos:
                    params["eixo"] = eixos
                if anos:
                    params["ano"] = anos
                if busca:
                    params["busca"] = busca

                res = requests.get(f"{self.base_url}/api/ocorrencias", params=params, timeout=4.0)
                if res.status_code == 200:
                    return res.json().get("ocorrencias", [])
            except Exception:
                pass

        df = self._fallback_service.filtrar(
            regioes=regioes, naturezas=naturezas, eixos=eixos,
            anos=anos, termo_busca=busca,
        )
        df = df.sort_values(
            ["ano", "mes", "quantidade"], ascending=[False, True, False]
        ).head(limite)
        meses = ["jan", "fev", "mar", "abr", "mai", "jun",
                 "jul", "ago", "set", "out", "nov", "dez"]
        return [
            {
                "regiao_administrativa": r["regiao_administrativa"],
                "natureza_crime": r["natureza"],
                "eixo_indicador": r.get("eixo_limpo"),
                "ano": int(r["ano"]),
                "mes": meses[int(r["mes"]) - 1],
                "tipo_registro": r["tipo_registro"],
                "quantidade": int(r["quantidade"]),
            }
            for _, r in df.iterrows()
        ]
