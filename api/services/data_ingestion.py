"""
Módulo de Ingestão e Consolidação de Dados de Segurança Pública do Distrito Federal.

Suporta:
1. Geração de base inicial/sintética para testes rápidos.
2. Consolidação de arquivos anuais por Região Administrativa (RA / Cidade):
   - Une múltiplos anos de uma mesma cidade em um arquivo consolidado por cidade.
   - Une todas as cidades consolidadas em um arquivo mestre global.
"""

from pathlib import Path
import json
import random
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"

COLUNAS_PADRAO = [
    "id",
    "regiao_administrativa",
    "natureza_crime",
    "data",
    "ano",
    "mes",
    "hora",
    "periodo_dia",
    "latitude",
    "longitude",
    "logradouro_detalhe",
    "peso_severidade",
]

SEVERIDADE_CRIME = {
    "Homicídio Doloso": 10,
    "Latrocínio": 10,
    "Roubo de Veículo": 7,
    "Roubo a Transeunte": 6,
    "Roubo a Comércio": 6,
    "Roubo em Coletivo": 6,
    "Violência Doméstica": 8,
    "Tráfico de Drogas": 5,
    "Furto de Veículo": 4,
    "Furto a Transeunte": 3,
}


def carregar_metadados_ras(caminho_json: Path = None) -> list:
    """Carrega as RAs e suas coordenadas centrais."""
    if caminho_json is None:
        caminho_json = DATA_DIR / "regioes_administrativas.json"

    if not caminho_json.exists():
        return []

    with open(caminho_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("regioes", [])


def gerar_dados_amostra(
    caminho_saida: Path = None,
    num_registros: int = 2000,
    ano_inicio: int = 2022,
    ano_fim: int = 2024
) -> pd.DataFrame:
    """Gera um dataset representativo para demonstração imediata do DF."""
    if caminho_saida is None:
        caminho_saida = DATA_DIR / "ocorrencias_df.csv"

    regioes = carregar_metadados_ras()

    pesos_ra = {
        "Ceilândia": 0.22,
        "Taguatinga": 0.14,
        "Samambaia": 0.14,
        "Plano Piloto": 0.13,
        "Gama": 0.08,
        "Guará": 0.06,
        "Santa Maria": 0.06,
        "Planaltina": 0.05,
        "Águas Claras": 0.04,
        "Recanto das Emas": 0.03,
        "Sobradinho": 0.02,
        "São Sebastião": 0.02,
        "Vicente Pires": 0.01,
    }

    lista_ras = [r["nome"] for r in regioes if r["nome"] in pesos_ra]
    if not lista_ras:
        lista_ras = ["Plano Piloto", "Ceilândia", "Taguatinga", "Samambaia", "Gama"]
        probs_ras = [0.2, 0.2, 0.2, 0.2, 0.2]
    else:
        probs_ras = [pesos_ra[nome] for nome in lista_ras]
        soma = sum(probs_ras)
        probs_ras = [p / soma for p in probs_ras]

    coords_dict = {r["nome"]: (r["latitude"], r["longitude"]) for r in regioes}

    naturezas = list(SEVERIDADE_CRIME.keys())
    pesos_naturezas = [0.03, 0.01, 0.16, 0.32, 0.08, 0.09, 0.12, 0.07, 0.06, 0.06]

    periodos = ["Madrugada", "Manhã", "Tarde", "Noite"]
    pesos_periodos = [0.15, 0.20, 0.30, 0.35]

    data_base_inicio = datetime(ano_inicio, 1, 1)
    data_base_fim = datetime(ano_fim, 12, 31)
    dias_totais = (data_base_fim - data_base_inicio).days

    registros = []
    for i in range(1, num_registros + 1):
        ra_escolhida = random.choices(lista_ras, weights=probs_ras, k=1)[0]
        lat_centro, lon_centro = coords_dict.get(ra_escolhida, (-15.7942, -47.8822))

        lat = lat_centro + np.random.normal(0, 0.013)
        lon = lon_centro + np.random.normal(0, 0.014)

        natureza = random.choices(naturezas, weights=pesos_naturezas, k=1)[0]
        periodo = random.choices(periodos, weights=pesos_periodos, k=1)[0]

        data_rand = data_base_inicio + timedelta(days=random.randint(0, dias_totais))
        if periodo == "Madrugada":
            hora_val = random.randint(0, 5)
        elif periodo == "Manhã":
            hora_val = random.randint(6, 11)
        elif periodo == "Tarde":
            hora_val = random.randint(12, 17)
        else:
            hora_val = random.randint(18, 23)
        hora_str = f"{hora_val:02d}:{random.randint(0, 59):02d}"

        registros.append({
            "id": f"DF-{data_rand.year}-{i:05d}",
            "regiao_administrativa": ra_escolhida,
            "natureza_crime": natureza,
            "data": data_rand.strftime("%Y-%m-%d"),
            "ano": int(data_rand.year),
            "mes": int(data_rand.month),
            "hora": hora_str,
            "periodo_dia": periodo,
            "latitude": round(float(lat), 6),
            "longitude": round(float(lon), 6),
            "logradouro_detalhe": f"Quadra {random.randint(100, 800)} - {ra_escolhida}",
            "peso_severidade": SEVERIDADE_CRIME.get(natureza, 5),
        })

    df = pd.DataFrame(registros)
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho_saida, index=False, encoding="utf-8")
    return df


def consolidar_arquivos_por_cidade(
    diretorio_raw: Path = None,
    diretorio_processado: Path = None,
    padrao_nome: str = "*.csv"
) -> dict:
    """Consolida os arquivos anuais brutos de cada cidade e gera a base consolidada mestre."""
    if diretorio_raw is None:
        diretorio_raw = DATA_DIR / "raw"
    if diretorio_processado is None:
        diretorio_processado = DATA_DIR / "processed"

    diretorio_raw = Path(diretorio_raw)
    diretorio_processado = Path(diretorio_processado)
    dir_cidades = diretorio_processado / "cidades"
    dir_cidades.mkdir(parents=True, exist_ok=True)

    arquivos = list(diretorio_raw.glob(padrao_nome))
    if not arquivos:
        return {"status": "nenhum_arquivo", "mensagem": f"Nenhum arquivo CSV encontrado em {diretorio_raw}"}

    grupos_cidade = {}
    for arq in arquivos:
        stem = arq.stem.lower()
        partes = stem.split("_")
        cidade_chave = partes[0]
        if cidade_chave not in grupos_cidade:
            grupos_cidade[cidade_chave] = []
        grupos_cidade[cidade_chave].append(arq)

    dataframes_cidades = []
    resumo = {}

    for cidade, lista_arqs in grupos_cidade.items():
        dfs_ano = []
        for a in lista_arqs:
            try:
                try:
                    df_ano = pd.read_csv(a, encoding="utf-8", sep=None, engine="python")
                except UnicodeDecodeError:
                    df_ano = pd.read_csv(a, encoding="latin1", sep=None, engine="python")
                dfs_ano.append(df_ano)
            except Exception as e:
                print(f"Erro ao ler {a.name}: {e}")

        if dfs_ano:
            df_cidade = pd.concat(dfs_ano, ignore_index=True)
            df_cidade.drop_duplicates(inplace=True)
            saida_cidade = dir_cidades / f"{cidade}_consolidado.csv"
            df_cidade.to_csv(saida_cidade, index=False, encoding="utf-8")
            dataframes_cidades.append(df_cidade)
            resumo[cidade] = {
                "arquivos_originais": len(lista_arqs),
                "total_registros": len(df_cidade),
                "caminho": str(saida_cidade),
            }

    if dataframes_cidades:
        df_master = pd.concat(dataframes_cidades, ignore_index=True)
        df_master.drop_duplicates(inplace=True)
        saida_master = diretorio_processado / "ocorrencias_df_master.csv"
        df_master.to_csv(saida_master, index=False, encoding="utf-8")
        resumo["_master_"] = {
            "total_geral": len(df_master),
            "caminho": str(saida_master),
        }

    return resumo

