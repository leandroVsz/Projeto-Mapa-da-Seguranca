"""
Serviço central de dados e regras de negócio para a Segurança Pública do DF.
Localização dos dados: pasta data/ na raiz do projeto.
"""

from pathlib import Path
import json
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"


class DataService:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.csv_path = self.data_dir / "ocorrencias_df.csv"
        self.json_ras_path = self.data_dir / "regioes_administrativas.json"

        self._df: Optional[pd.DataFrame] = None
        self._regioes_meta: Optional[List[Dict[str, Any]]] = None
        self.carregar_dados()

    def carregar_dados(self, forcar_recarga: bool = False) -> pd.DataFrame:
        """Carrega ou gera a base de ocorrências."""
        if self._df is not None and not forcar_recarga:
            return self._df

        # 1. Carregar Regiões Administrativas
        if self.json_ras_path.exists():
            with open(self.json_ras_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                self._regioes_meta = meta.get("regioes", [])
        else:
            self._regioes_meta = []

        # 2. Carregar Ocorrências (prioriza o mestre se existir, senão usa ocorrencias_df.csv)
        master_path = self.data_dir / "processed" / "ocorrencias_df_master.csv"
        alvo_csv = master_path if master_path.exists() else self.csv_path

        if not alvo_csv.exists():
            from api.services.data_ingestion import gerar_dados_amostra
            self._df = gerar_dados_amostra(self.csv_path, num_registros=2000)
        else:
            try:
                self._df = pd.read_csv(alvo_csv, encoding="utf-8")
            except UnicodeDecodeError:
                self._df = pd.read_csv(alvo_csv, encoding="latin1")

        # Sanitização de tipos
        self._df["latitude"] = pd.to_numeric(self._df["latitude"], errors="coerce")
        self._df["longitude"] = pd.to_numeric(self._df["longitude"], errors="coerce")
        self._df["ano"] = pd.to_numeric(self._df["ano"], errors="coerce").fillna(2023).astype(int)
        self._df = self._df.dropna(subset=["latitude", "longitude"])

        return self._df

    def get_regioes(self) -> List[Dict[str, Any]]:
        """Retorna metadados das Regiões Administrativas."""
        if not self._regioes_meta:
            self.carregar_dados()
        return self._regioes_meta or []

    def get_opcoes_filtros(self) -> Dict[str, List[Any]]:
        """Retorna listas para preenchimento dos filtros na interface."""
        df = self.carregar_dados()
        return {
            "regioes": sorted(df["regiao_administrativa"].dropna().unique().tolist()),
            "naturezas": sorted(df["natureza_crime"].dropna().unique().tolist()),
            "anos": sorted(df["ano"].dropna().unique().tolist(), reverse=True),
            "periodos": ["Madrugada", "Manhã", "Tarde", "Noite"],
        }

    def filtrar_ocorrencias(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        periodos: Optional[List[str]] = None,
        termo_busca: Optional[str] = None,
    ) -> pd.DataFrame:
        """Aplica filtros combinados."""
        df = self.carregar_dados().copy()

        if regioes:
            df = df[df["regiao_administrativa"].isin(regioes)]
        if naturezas:
            df = df[df["natureza_crime"].isin(naturezas)]
        if anos:
            df = df[df["ano"].isin(anos)]
        if periodos:
            df = df[df["periodo_dia"].isin(periodos)]
        if termo_busca:
            termo = termo_busca.lower()
            df = df[
                df["logradouro_detalhe"].astype(str).str.lower().str.contains(termo, na=False)
                | df["regiao_administrativa"].astype(str).str.lower().str.contains(termo, na=False)
                | df["natureza_crime"].astype(str).str.lower().str.contains(termo, na=False)
            ]

        return df

    def get_pontos_calor(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        periodos: Optional[List[str]] = None,
        ponderar_severidade: bool = True,
    ) -> List[List[float]]:
        """
        Retorna matriz de coordenadas [latitude, longitude, peso]
        otimizada para renderização do mapa de calor.
        """
        df = self.filtrar_ocorrencias(regioes, naturezas, anos, periodos)
        pontos = []

        for _, row in df.iterrows():
            peso = float(row.get("peso_severidade", 1)) if ponderar_severidade else 1.0
            intensidade = min(1.0, max(0.2, peso / 10.0))
            pontos.append([
                float(row["latitude"]),
                float(row["longitude"]),
                round(intensidade, 2),
            ])

        return pontos

    def get_estatisticas(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        periodos: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Calcula indicadores-chave (KPIs) e resumos estatísticos."""
        df = self.filtrar_ocorrencias(regioes, naturezas, anos, periodos)
        total = len(df)

        if total == 0:
            return {
                "total_ocorrencias": 0,
                "ra_mais_afetada": "N/A",
                "crime_mais_frequente": "N/A",
                "periodo_mais_critico": "N/A",
                "por_natureza": {},
                "por_regiao": {},
                "por_periodo": {},
                "por_ano": {},
            }

        return {
            "total_ocorrencias": total,
            "ra_mais_afetada": df["regiao_administrativa"].value_counts().index[0],
            "crime_mais_frequente": df["natureza_crime"].value_counts().index[0],
            "periodo_mais_critico": df["periodo_dia"].value_counts().index[0],
            "por_natureza": df["natureza_crime"].value_counts().to_dict(),
            "por_regiao": df["regiao_administrativa"].value_counts().head(10).to_dict(),
            "por_periodo": df["periodo_dia"].value_counts().to_dict(),
            "por_ano": df["ano"].value_counts().sort_index().to_dict(),
        }

