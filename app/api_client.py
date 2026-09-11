"""
Cliente HTTP para consumo da API REST do backend (FastAPI).
Possui fallback transparente para o DataService caso a API esteja offline.
"""

from typing import Dict, List, Any, Optional
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
    def __init__(self, base_url: str = DEFAULT_API_URL):
        self.base_url = base_url.rstrip("/")
        self._fallback_service = DataService()
        self._api_online = None

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

    def get_regioes(self) -> List[Dict[str, Any]]:
        """Busca lista de Regiões Administrativas."""
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
        """Busca intensidade por RA para o mapa coropleto."""
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
        # Fallback: conta ocorrências simuladas por RA
        df = self._fallback_service.filtrar_ocorrencias(
            regioes=regioes, naturezas=naturezas, anos=anos,
        )
        return {
            "online": False,
            "regioes": [
                {"nome": nome, "total": int(total)}
                for nome, total in df["regiao_administrativa"].value_counts().items()
            ],
        }

    def get_heatmap(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        periodos: Optional[List[str]] = None,
        ponderar: bool = True,
    ) -> List[List[float]]:
        """Busca pontos do mapa de calor (centroides ponderados)."""
        if self.is_online():
            try:
                params = {"ponderar": ponderar}
                if regioes:
                    params["regiao"] = regioes
                if naturezas:
                    params["natureza"] = naturezas
                if eixos:
                    params["eixo"] = eixos
                if anos:
                    params["ano"] = anos
                if periodos:
                    params["periodo"] = periodos

                res = requests.get(f"{self.base_url}/api/heatmap", params=params, timeout=4.0)
                if res.status_code == 200:
                    return res.json().get("pontos", [])
            except Exception:
                pass
        return self._fallback_service.get_pontos_calor(
            regioes=regioes,
            naturezas=naturezas,
            anos=anos,
            periodos=periodos,
            ponderar_severidade=ponderar,
        )

    def get_stats(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        periodos: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Busca estatísticas e indicadores agregados."""
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
                if periodos:
                    params["periodo"] = periodos

                res = requests.get(f"{self.base_url}/api/stats", params=params, timeout=3.0)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return self._fallback_service.get_estatisticas(
            regioes=regioes,
            naturezas=naturezas,
            anos=anos,
            periodos=periodos,
        )

    def get_ocorrencias(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        periodos: Optional[List[str]] = None,
        busca: Optional[str] = None,
        limite: int = 500,
    ) -> List[Dict[str, Any]]:
        """Busca listagem filtrada de ocorrências."""
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
                if periodos:
                    params["periodo"] = periodos
                if busca:
                    params["busca"] = busca

                res = requests.get(f"{self.base_url}/api/ocorrencias", params=params, timeout=4.0)
                if res.status_code == 200:
                    return res.json().get("ocorrencias", [])
            except Exception:
                pass

        df = self._fallback_service.filtrar_ocorrencias(
            regioes=regioes,
            naturezas=naturezas,
            anos=anos,
            periodos=periodos,
            termo_busca=busca,
        )
        return df.head(limite).to_dict(orient="records")

