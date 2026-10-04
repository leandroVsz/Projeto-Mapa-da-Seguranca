#!/usr/bin/env python3
"""
ingest_crimemap.py
-------------------
Consolida os arquivos .xls/.xlsx do Balanço Criminal da SSP-DF
(baixados manualmente por RA e por ano) em um único CSV.

Uso:
    python ingest_crimemap.py --input raw_data/ --output output/crimemap_consolidado.csv

Layout esperado dos arquivos-fonte (confirmado em amostras de várias RAs e anos):

    - Cada arquivo pode ter 1 aba (ano mais recente) ou várias abas,
      uma por ano (ex: "PPV(mensal)2018", "PPV(mensal)2017", ...).
    - Em algum lugar das primeiras linhas existe uma célula com o texto
      exato "EIXOS INDICADORES" — é ela que ancora o cabeçalho real,
      já que a posição da linha varia de arquivo para arquivo.
    - Logo depois vem a linha "NATUREZA" / "TOTAL" / <ano>, e uma linha
      abaixo os meses JAN..DEZ.
    - O arquivo do Distrito Federal (agregado) tem uma coluna extra
      "OCORRÊNCIA" / "VÍTIMA" entre o eixo indicador e a natureza —
      os arquivos por RA não têm essa coluna.
    - A coluna de eixo indicador e a coluna de natureza só têm valor
      preenchido na primeira linha de cada grupo (célula mesclada no
      Excel original); as linhas seguintes vêm em branco.
    - Linhas de subtotal/total (ex: "1.TOTAL C.V.L.I.") aparecem
      misturadas com as linhas de detalhe, mas nem toda seção tem uma
      — não dá para contar com uma quantidade fixa de linhas totais.
    - O rodapé (linhas "Fonte:", "Obs:", "*") vem depois dos dados e
      não tem valor numérico na coluna TOTAL.

Se o portal mudar esse layout no futuro, este script deve ser revisado
(ver observação sobre isso no Documento de Visão do projeto).
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]

HEADER_ANCHOR = "EIXOS INDICADORES"
NATUREZA_LABEL = "NATUREZA"

# regex para "RA I - BRASÍLIA", "RA XX - ÁGUAS CLARAS", "RA IX - CEILÂNDIA" etc.
# usa \b antes de RA porque em anos mais antigos a frase vem embutida em
# texto maior, ex: "PRINCIPAIS OCORRÊNCIAS POLICIAIS NA RA IX - CEILÂNDIA"
RA_HEADER_RE = re.compile(r"\bRA\s+([IVXLCDM]+)\s*-\s*(.+)$", re.IGNORECASE)

# código da RA a partir do prefixo numérico do nome do arquivo
# (é como o portal da SSP-DF nomeia os downloads: "9_ceilandia...",
# "20_AGUAS_CLARAS...", "00_DISTRITO_FEDERAL...")
FILENAME_CODE_RE = re.compile(r"^(\d+)_")


class ParseWarning(Exception):
    """Erro não fatal: sinaliza que uma aba/arquivo foi pulado."""


def find_cell(df: pd.DataFrame, target: str, max_row: int = 15):
    """Procura a primeira célula (linha, coluna) cujo texto (stripped,
    case-insensitive) é igual a `target`, dentro das primeiras `max_row`
    linhas. Retorna (row_idx, col_idx) ou None."""
    limit = min(max_row, len(df))
    for r in range(limit):
        for c in range(df.shape[1]):
            val = df.iat[r, c]
            if isinstance(val, str) and val.strip().upper() == target.upper():
                return r, c
    return None


def extract_ra_from_header(df: pd.DataFrame, header_row: int):
    """Procura nas linhas antes do cabeçalho por 'RA <alg> - <nome>' ou
    'DISTRITO FEDERAL'. Retorna (codigo_romano_ou_None, nome) ou None."""
    for r in range(header_row):
        for c in range(df.shape[1]):
            val = df.iat[r, c]
            if not isinstance(val, str):
                continue
            text = val.strip()
            m = RA_HEADER_RE.search(text)
            if m:
                return m.group(1).upper(), m.group(2).strip().title()
            if text.upper() == "DISTRITO FEDERAL":
                return None, "Distrito Federal"
    return None


def extract_year(df: pd.DataFrame, header_row: int, year_col: int, sheet_name: str):
    """Tenta ler o ano da célula logo abaixo de TOTAL no cabeçalho; se
    não der, tenta extrair de 'COMPARATIVO MENSAL <ano>' em texto livre
    próximo, ou do nome da aba."""
    val = df.iat[header_row, year_col]
    try:
        return int(float(val))
    except (ValueError, TypeError):
        pass
    for r in range(max(0, header_row - 4), header_row):
        for c in range(df.shape[1]):
            v = df.iat[r, c]
            if isinstance(v, str):
                m = re.search(r"(19|20)\d{2}", v)
                if m:
                    return int(m.group(0))
    m = re.search(r"(19|20)\d{2}", sheet_name)
    if m:
        return int(m.group(0))
    raise ParseWarning(f"não foi possível determinar o ano (aba '{sheet_name}')")


def parse_sheet(df: pd.DataFrame, source_file: str, sheet_name: str) -> pd.DataFrame:
    anchor = find_cell(df, HEADER_ANCHOR)
    if anchor is None:
        raise ParseWarning(
            f"célula '{HEADER_ANCHOR}' não encontrada (aba '{sheet_name}')"
        )
    header_row, eixo_col = anchor

    natureza_col = None
    for c in range(eixo_col, df.shape[1]):
        v = df.iat[header_row, c]
        if isinstance(v, str) and v.strip().upper() == NATUREZA_LABEL:
            natureza_col = c
            break
    if natureza_col is None:
        raise ParseWarning(
            f"coluna '{NATUREZA_LABEL}' não encontrada (aba '{sheet_name}')"
        )

    total_col = natureza_col + 1
    year_col = total_col + 1
    months_start = year_col

    # coluna extra "OCORRÊNCIA"/"VÍTIMA" só existe em alguns arquivos
    # (ex: consolidado do Distrito Federal), fica entre eixo e natureza
    tipo_col = eixo_col + 1 if (natureza_col - eixo_col) == 2 else None

    if months_start + 11 >= df.shape[1]:
        raise ParseWarning(
            f"colunas de meses fora do esperado (aba '{sheet_name}')"
        )

    year = extract_year(df, header_row, year_col, sheet_name)
    ra_info = extract_ra_from_header(df, header_row)
    ra_nome = ra_info[1] if ra_info else None

    codigo_arquivo = None
    m = FILENAME_CODE_RE.match(Path(source_file).name)
    if m:
        codigo_arquivo = m.group(1).zfill(2)

    if ra_nome is None:
        # fallback: usa o nome do arquivo sem prefixo numérico/sufixos
        stem = Path(source_file).stem
        stem = re.sub(r"^\d+_", "", stem)
        stem = re.sub(r"[_\-].*$", "", stem)
        ra_nome = stem.replace("_", " ").title()

    data_start = header_row + 2
    data = df.iloc[data_start:, :].reset_index(drop=True).copy()

    # linhas de subtotal/total: o texto na coluna do eixo contém "TOTAL"
    eixo_raw = data[eixo_col].astype(str)
    is_total_row = eixo_raw.str.upper().str.contains("TOTAL", na=False)

    # preenche células mescladas "para baixo"
    data[eixo_col] = data[eixo_col].ffill()
    if tipo_col is not None:
        data[tipo_col] = data[tipo_col].ffill()
    data[natureza_col] = data[natureza_col].ffill()

    total_numeric = pd.to_numeric(data[total_col], errors="coerce")
    valid = total_numeric.notna() & ~is_total_row & data[natureza_col].notna()
    data = data[valid].copy()
    total_numeric = total_numeric[valid]

    if data.empty:
        raise ParseWarning(f"nenhuma linha de detalhe encontrada (aba '{sheet_name}')")

    out = pd.DataFrame({
        "regiao_administrativa": ra_nome,
        "codigo_ra_arquivo": codigo_arquivo,
        "ano": year,
        "eixo_indicador": data[eixo_col].astype(str).str.strip(),
        "tipo_registro": (
            data[tipo_col].astype(str).str.strip().str.upper()
            if tipo_col is not None else "OCORRENCIA"
        ),
        "natureza": data[natureza_col].astype(str).str.strip(),
        "total_ano": total_numeric.astype(int),
    })

    for i, mes in enumerate(MESES):
        col = months_start + i
        out[mes] = pd.to_numeric(data.iloc[:, col], errors="coerce").fillna(0).astype(int)

    out["arquivo_origem"] = Path(source_file).name
    out["aba_origem"] = sheet_name

    return out.reset_index(drop=True)


def process_file(path: Path, warnings: list) -> list:
    engine = "openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd"
    try:
        xls = pd.ExcelFile(path, engine=engine)
    except Exception as e:
        warnings.append(f"[{path.name}] não foi possível abrir o arquivo: {e}")
        return []

    frames = []
    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
            frames.append(parse_sheet(raw, str(path), sheet))
        except ParseWarning as w:
            warnings.append(f"[{path.name}] {w}")
        except Exception as e:
            warnings.append(f"[{path.name}] aba '{sheet}': erro inesperado: {e}")
    return frames


def consolidar(input_dir: Path, output_path: Path) -> dict:
    """Consolida todos os .xls/.xlsx de input_dir no CSV output_path.
    Retorna um resumo (linhas, regiões, anos, avisos) — reutilizável pela API."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(list(Path(input_dir).glob("*.xls")) + list(Path(input_dir).glob("*.xlsx")))
    if not files:
        return {"status": "nenhum_arquivo", "mensagem": f"Nenhum arquivo .xls/.xlsx em '{input_dir}'"}

    warnings = []
    all_frames = []
    for f in files:
        frames = process_file(f, warnings)
        all_frames.extend(frames)
        print(f"  {f.name}: {len(frames)} aba(s) processada(s)")

    if not all_frames:
        return {"status": "sem_dados", "avisos": warnings,
                "mensagem": "Nenhum dado extraído dos arquivos."}

    consolidado = pd.concat(all_frames, ignore_index=True)
    consolidado = consolidado.sort_values(
        ["regiao_administrativa", "ano", "eixo_indicador", "natureza", "tipo_registro"]
    ).reset_index(drop=True)

    consolidado.to_csv(output_path, index=False, encoding="utf-8-sig")

    resumo = {
        "status": "ok",
        "csv_gerado": str(output_path),
        "linhas": int(len(consolidado)),
        "regioes": int(consolidado["regiao_administrativa"].nunique()),
        "anos": sorted(int(a) for a in consolidado["ano"].unique()),
        "avisos": warnings,
    }
    print(f"\n✔ Consolidado salvo em: {output_path}")
    print(f"  Linhas: {resumo['linhas']} | Regiões: {resumo['regioes']} | Anos: {resumo['anos']}")
    if warnings:
        print(f"\n⚠ {len(warnings)} aviso(s) durante o processamento:")
        for w in warnings:
            print(f"  - {w}")
    return resumo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "-i", default="raw_data", help="Pasta com os .xls/.xlsx baixados manualmente")
    ap.add_argument("--output", "-o", default="output/crimemap_consolidado.csv", help="Caminho do CSV consolidado")
    args = ap.parse_args()

    consolidar(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
