"""
Serviço de dados fallback (sem PostgreSQL), no mesmo esquema da base real.

Lê o CSV consolidado da SSP-DF (pivô jan..dez) com os mesmos normalizadores
da carga do banco (db/load_csv.py), então o modo sem-banco mostra os mesmos
totais do modo com-banco. Sem contornos: eles só existem no banco.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


def _strip_accents(valor: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(valor))
        if unicodedata.category(c) != "Mn"
    )


def _limpar_eixo(eixo_bruto: Any) -> str:
    """Remove prefixos numéricos do eixo (ex: '1. C.V.L.I. - ...')."""
    eixo = re.sub(r"^\s*\d+\.\s*", "", str(eixo_bruto))
    eixo = re.sub(r"\s+", " ", eixo).strip()
    return "TOTAL (resumo)" if eixo.upper() == "TOTAL" else eixo


def _limpar_natureza(nat: Any) -> str:
    nat = re.sub(r"\s*\*+\s*$", "", str(nat))
    return re.sub(r"\s+", " ", nat).strip()


def _derreter_para_longo(df_pivo: pd.DataFrame) -> pd.DataFrame:
    """Converte o pivô (jan..dez em colunas) em formato longo:
    uma linha por (RA, natureza, ano, tipo_registro, mês) com quantidade.
    Usa EXATAMENTE os mesmos normalizadores da carga real (db/load_csv.py):
    resolver_regiao (aliases + Title Case), limpar_natureza, limpar_eixo."""
    from db.load_csv import resolver_regiao, limpar_natureza, limpar_eixo

    df = df_pivo.copy()
    df["regiao_administrativa"] = df["regiao_administrativa"].apply(resolver_regiao)
    df["natureza"] = df["natureza"].apply(limpar_natureza)
    if "eixo_indicador" in df.columns:
        df["eixo_limpo"] = df["eixo_indicador"].apply(limpar_eixo)
        # Remapeia 'TOTAL (resumo)' pelo conteúdo da natureza (como na carga)
        mask_total = df["eixo_limpo"] == "TOTAL (resumo)"
        df.loc[mask_total & df["natureza"].str.contains("C.V.L.I.", na=False), "eixo_limpo"] = (
            "C.V.L.I. - CRIMES VIOLENTOS LETAIS INTENCIONAIS"
        )
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df = df.dropna(subset=["ano"])
    df["ano"] = df["ano"].astype(int)
    df["tipo_registro"] = (
        df["tipo_registro"].astype(str).apply(_strip_accents).str.upper().str.strip()
    )
    df.loc[~df["tipo_registro"].isin(["OCORRENCIA", "VITIMA"]), "tipo_registro"] = "OCORRENCIA"

    # Deduplicação idêntica à carga real (db/load_csv.py): re-downloads do
    # portal repetem a mesma chave (RA, natureza, ano, tipo); agrega pelo
    # MÁXIMO por mês, preservando o primeiro eixo visto.
    agregacoes = {m: "max" for m in MESES}
    if "total_ano" in df.columns:
        agregacoes["total_ano"] = "max"
    if "eixo_limpo" in df.columns:
        agregacoes["eixo_limpo"] = "first"
    df = df.groupby(
        ["regiao_administrativa", "natureza", "ano", "tipo_registro"],
        as_index=False,
    ).agg(agregacoes)

    derretido = df.melt(
        id_vars=["regiao_administrativa", "natureza", "ano", "tipo_registro"]
        + (["eixo_limpo"] if "eixo_limpo" in df.columns else []),
        value_vars=MESES, var_name="mes_nome", value_name="quantidade",
    )
    derretido["mes"] = derretido["mes_nome"].map({m: i for i, m in enumerate(MESES, 1)})
    derretido["quantidade"] = pd.to_numeric(derretido["quantidade"], errors="coerce").fillna(0)
    return derretido.drop(columns=["mes_nome"])


class DataService:
    """Fallback CSV/simulado com o mesmo esquema da base real."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.json_ras_path = self.data_dir / "regioes_administrativas.json"

        self._df: Optional[pd.DataFrame] = None          # pivô jan..dez
        self._df_longo: Optional[pd.DataFrame] = None    # derretido (1 linha/mês)
        self._regioes_meta: Optional[List[Dict[str, Any]]] = None
        self.carregar_dados()

    # ------------------------------------------------------------------
    # Carga / normalização (espelha db/load_csv.preparar_dataframe)
    # ------------------------------------------------------------------
    def carregar_dados(self, forcar_recarga: bool = False) -> pd.DataFrame:
        if self._df is not None and not forcar_recarga:
            return self._df

        if self.json_ras_path.exists():
            with open(self.json_ras_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self._regioes_meta = meta.get("regioes", [])
        else:
            self._regioes_meta = []

        master = self.data_dir / "processed" / "ocorrencias_df_master.csv"
        consolidado = ROOT_DIR / "api" / "services" / "output" / "crimemap_consolidadov2.csv"
        demonstracao = self.data_dir / "ocorrencias_df.csv"

        if master.exists():
            alvo = master
        elif consolidado.exists():
            alvo = consolidado  # mesma fonte da carga real
        elif demonstracao.exists():
            alvo = demonstracao
        else:
            from api.services.data_ingestion import gerar_dados_amostra
            alvo = demonstracao
            gerar_dados_amostra(caminho_saida=alvo)

        self._df = pd.read_csv(alvo, encoding="utf-8-sig")
        self._df_longo = _derreter_para_longo(self._df)
        return self._df

    def _longo(self) -> pd.DataFrame:
        if self._df_longo is None:
            self.carregar_dados()
        return self._df_longo

    def get_regioes(self) -> List[Dict[str, Any]]:
        """Metadado local das RAs (sem contornos, que só existem no banco)."""
        if self._regioes_meta is None:
            self.carregar_dados()
        return self._regioes_meta or []

    def get_opcoes_filtros(self) -> Dict[str, List[Any]]:
        df = self._longo()
        eixos = (
            sorted(df["eixo_limpo"].dropna().unique().tolist())
            if "eixo_limpo" in df.columns else []
        )
        return {
            "regioes": sorted(df["regiao_administrativa"].dropna().unique().tolist()),
            "naturezas": sorted(df["natureza"].dropna().unique().tolist()),
            "eixos": eixos,
            "anos": sorted(df["ano"].dropna().unique().tolist(), reverse=True),
            "periodos": [],  # não existe na base real
        }

    def filtrar(
        self,
        regioes: Optional[List[str]] = None,
        naturezas: Optional[List[str]] = None,
        eixos: Optional[List[str]] = None,
        anos: Optional[List[int]] = None,
        tipo_registro: str = "OCORRENCIA",
        termo_busca: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self._longo()
        if tipo_registro:
            df = df[df["tipo_registro"] == tipo_registro]
        if regioes:
            df = df[df["regiao_administrativa"].isin(regioes)]
        if naturezas:
            df = df[df["natureza"].isin(naturezas)]
        if eixos and "eixo_limpo" in df.columns:
            df = df[df["eixo_limpo"].isin(eixos)]
        if anos:
            df = df[df["ano"].isin([int(a) for a in anos])]
        if termo_busca:
            t = termo_busca.lower()
            df = df[
                df["regiao_administrativa"].astype(str).str.lower().str.contains(t, na=False)
                | df["natureza"].astype(str).str.lower().str.contains(t, na=False)
            ]
        return df

    def get_pontos_calor(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> List[List[float]]:
        """Heatmap: um ponto por RA (centroide do metadado), peso = total."""
        df = self.filtrar(regioes, naturezas, eixos, anos, tipo_registro)
        agg = df.groupby("regiao_administrativa")["quantidade"].sum().reset_index()
        centroides = {
            r["nome"]: (r["latitude"], r["longitude"])
            for r in (self._regioes_meta or [])
        }
        max_total = float(agg["quantidade"].max()) if not agg.empty else 0.0
        pontos = []
        for _, row in agg.iterrows():
            centro = centroides.get(row["regiao_administrativa"])
            if not centro:
                continue
            peso = 0.2 + 0.8 * (float(row["quantidade"]) / max_total) if max_total > 0 else 0.2
            pontos.append([round(centro[0], 6), round(centro[1], 6), round(peso, 3)])
        return pontos

    def get_coropleto(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> List[Dict[str, Any]]:
        df = self.filtrar(regioes, naturezas, eixos, anos, tipo_registro)
        agg = df.groupby("regiao_administrativa")["quantidade"].sum()
        return [{"nome": nome, "total": int(total)} for nome, total in agg.items()]

    def get_top_naturezas(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> Dict[str, List[Dict[str, Any]]]:
        df = self.filtrar(regioes, naturezas, eixos, anos, tipo_registro)
        agg = (
            df.groupby(["regiao_administrativa", "natureza"])["quantidade"].sum()
            .reset_index()
            .sort_values("quantidade", ascending=False)
        )
        top: Dict[str, List[Dict[str, Any]]] = {}
        for _, row in agg.iterrows():
            if int(row["quantidade"]) <= 0:
                continue
            top.setdefault(row["regiao_administrativa"], []).append(
                {"natureza": row["natureza"], "total": int(row["quantidade"])}
            )
        return top

    def get_detalhe_regiao(
        self,
        regiao: str,
        naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> Dict[str, Any]:
        df = self.filtrar(regioes=[regiao], naturezas=naturezas,
                          eixos=eixos, anos=anos, tipo_registro=tipo_registro)
        if df.empty:
            return {"regiao": regiao, "total_ocorrencias": 0,
                    "por_natureza": {}, "por_ano": {}, "por_mes": {}}
        return {
            "regiao": regiao,
            "total_ocorrencias": int(df["quantidade"].sum()),
            "por_natureza": {
                k: int(v) for k, v in
                df.groupby("natureza")["quantidade"].sum()
                .sort_values(ascending=False).items()
            },
            "por_ano": {
                int(k): int(v) for k, v in
                df.groupby("ano")["quantidade"].sum().sort_index().items()
            },
            "por_mes": {
                int(k): int(v) for k, v in
                df.groupby("mes")["quantidade"].sum().sort_index().items()
            },
        }

    def get_estatisticas(
        self,
        regioes=None, naturezas=None, eixos=None, anos=None,
        tipo_registro: str = "OCORRENCIA",
    ) -> Dict[str, Any]:
        df = self.filtrar(regioes, naturezas, eixos, anos, tipo_registro)
        if df.empty:
            return {"total_ocorrencias": 0, "ra_mais_afetada": "N/A",
                    "crime_mais_frequente": "N/A", "por_natureza": {},
                    "por_regiao": {}, "por_ano": {}, "por_mes": {}}
        por_natureza = df.groupby("natureza")["quantidade"].sum().sort_values(ascending=False)
        por_regiao = df.groupby("regiao_administrativa")["quantidade"].sum().sort_values(ascending=False)
        return {
            "total_ocorrencias": int(df["quantidade"].sum()),
            "ra_mais_afetada": str(por_regiao.index[0]),
            "crime_mais_frequente": str(por_natureza.index[0]),
            "por_natureza": {k: int(v) for k, v in por_natureza.items()},
            "por_regiao": {k: int(v) for k, v in por_regiao.items()},
            "por_ano": {int(k): int(v) for k, v in
                        df.groupby("ano")["quantidade"].sum().sort_index().items()},
            "por_mes": {int(k): int(v) for k, v in
                        df.groupby("mes")["quantidade"].sum().sort_index().items()},
        }
