"""
Gerador de base de demonstração (modo fallback sem CSV e sem banco).

Produz o mesmo esquema do CSV consolidado da SSP-DF: pivô (RA, natureza,
ano, tipo_registro) × jan..dez + total_ano, sem nenhum campo inexistente
na base real (período do dia, peso de severidade, lat/long por crime).
"""

import json
import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
JSON_RAS_PATH = DATA_DIR / "regioes_administrativas.json"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]

NATUREZAS_CVLI = [
    "HOMICÍDIO DOLOSO",
    "LATROCÍNIO",
    "LESÃO CORPORAL SEGUIDA DE MORTE",
]
NATUREZAS_CCP = [
    "ROUBO A TRANSEUNTE",
    "ROUBO DE VEÍCULO",
    "ROUBO EM COLETIVO",
    "ROUBO A COMÉRCIO",
    "FURTO A TRANSEUNTE",
    "FURTO DE VEÍCULO",
    "VIOLENCIA DOMESTICA",
    "TRAFICO DE DROGAS",
]

# Volume médio mensal por natureza (mesma ordem das listas acima), calibrado
# para ficar na mesma ordem de grandeza dos dados reais da SSP-DF.
VOLUME_MEDIO_MENSAL = [3.0, 0.4, 1.2, 90.0, 45.0, 8.0, 25.0, 70.0, 60.0, 20.0, 55.0, 18.0]


def _carregar_ras() -> list[str]:
    """Nomes das RAs do metadado local (regioes_administrativas.json)."""
    if JSON_RAS_PATH.exists():
        try:
            with open(JSON_RAS_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return [r["nome"] for r in meta.get("regioes", [])]
        except Exception:
            pass
    return ["Plano Piloto", "Ceilândia", "Taguatinga", "Samambaia", "Gama"]


def _pesos_por_populacao(ras: list[str]) -> dict[str, float]:
    """Peso de cada RA proporcional à população estimada do metadado.
    Usado apenas na base de demonstração — os dados reais têm as contagens
    verdadeiras da SSP-DF e nunca passam por aqui."""
    pops = {}
    if JSON_RAS_PATH.exists():
        try:
            with open(JSON_RAS_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
            pops = {r["nome"]: float(r.get("populacao_estimada", 0))
                    for r in meta.get("regioes", [])}
        except Exception:
            pops = {}
    if not pops:
        # fallback uniforme se o metadado não estiver disponível
        return {ra: 1.0 for ra in ras}
    total_pop = sum(pops.values()) or 1.0
    return {ra: pops.get(ra, 0.0) / total_pop for ra in ras}


def gerar_dados_amostra(
    caminho_saida: Path = None,
    ano_inicio: int = 2022,
    ano_fim: int = None,
) -> pd.DataFrame:
    """Gera a base simulada no mesmo esquema do CSV consolidado real."""
    if caminho_saida is None:
        caminho_saida = DATA_DIR / "ocorrencias_df.csv"
    if ano_fim is None:
        ano_fim = datetime.now().year - 1  # anos completos apenas

    ras = [r for r in _carregar_ras() if r]
    pesos = _pesos_por_populacao(ras)
    probs = np.array([pesos.get(ra, 0.0) for ra in ras], dtype=float)
    if probs.sum() == 0:
        probs = np.ones(len(ras))
    probs /= probs.sum()

    naturezas = NATUREZAS_CVLI + NATUREZAS_CCP
    volumes = np.array(VOLUME_MEDIO_MENSAL, dtype=float)

    registros = []
    for ano in range(ano_inicio, ano_fim + 1):
        for ra in ras:
            fator_ano = 1.0 + np.random.uniform(-0.15, 0.20)
            for natureza, vol_base in zip(naturezas, volumes):
                if random.random() > 0.92:  # nem toda natureza ocorre em toda RA
                    continue
                # escala o volume pela participação da RA na população do DF
                vol = vol_base * (pesos.get(ra, 0.0) / 0.10) * fator_ano
                contagens = np.random.poisson(max(vol, 0.05), size=12)
                if contagens.sum() == 0 and vol_base >= 1:
                    contagens[random.randint(0, 11)] = 1
                linha = {
                    "regiao_administrativa": ra,
                    "codigo_ra_arquivo": None,
                    "ano": ano,
                    "eixo_indicador": (
                        "C.V.L.I. - CRIMES VIOLENTOS LETAIS INTENCIONAIS"
                        if natureza in NATUREZAS_CVLI
                        else "C.C.P. - CRIMES CONTRA O PATRIMÔNIO"
                    ),
                    "tipo_registro": "OCORRENCIA",
                    "natureza": natureza,
                }
                for i, mes in enumerate(MESES):
                    linha[mes] = int(contagens[i])
                linha["total_ano"] = int(contagens.sum())
                registros.append(linha)

    df = pd.DataFrame(registros)
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho_saida, index=False, encoding="utf-8")
    return df
