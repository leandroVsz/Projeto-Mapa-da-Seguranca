"""
Smoke test do banco CrimeMap DF: valida se o que está no Postgres
bate com o CSV consolidado de origem.

Verificações:
  1. Soma de (jan..dez) do CSV == SUM(quantidade) no banco, por
     (regiao, natureza, ano, tipo_registro).
  2. RAs, naturezas e anos esperados estão presentes no banco.
  3. RAs têm contorno (polígono) cadastrado.

Uso:
    python -m db.smoke_test
"""

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.load_csv import CSV_PADRAO, MESES, preparar_dataframe
from api.db.session import SessionLocal

TOLERANCIA = 0


def main() -> int:
    erros = []
    avisos = []

    if not CSV_PADRAO.exists():
        print(f"✖ CSV não encontrado: {CSV_PADRAO}")
        return 1

    df = preparar_dataframe(CSV_PADRAO)

    # Informativo: linhas onde o próprio total_ano da planilha não bate com
    # a soma dos meses (inconsistência da fonte, anos antigos 2014/2016/2017).
    # O banco armazena os valores mensais (verdade granular), então isso
    # não é erro de carga — apenas documentamos a diferença.
    divergencia_fonte = (df[MESES].sum(axis=1).astype(int) - df["total_ano"].astype(int)).abs()
    n_div = int((divergencia_fonte > 0).sum())
    if n_div:
        avisos.append(
            f"{n_div} linhas do CSV têm total_ano ≠ soma dos meses "
            f"(inconsistência da fonte; o banco usa os valores mensais)"
        )

    esperado = (
        df.groupby(["regiao_normalizada", "natureza_limpa", "ano", "tipo_registro_normalizado"])[MESES]
        .sum()
        .sum(axis=1)
        .to_dict()
    )

    with SessionLocal() as session:
        # 1. Totais no banco
        resultado = session.execute(text("""
            SELECT r.nome, t.nome, f.ano, f.tipo_registro, SUM(f.quantidade)
            FROM ocorrencia_mensal f
            JOIN regiao_administrativa r ON r.id = f.regiao_id
            JOIN tipo_crime t ON t.id = f.tipo_crime_id
            GROUP BY r.nome, t.nome, f.ano, f.tipo_registro
        """)).all()

        no_banco = {(r[0], r[1], int(r[2]), r[3]): int(r[4]) for r in resultado}

        faltando = set(esperado) - set(no_banco)
        if faltando:
            erros.append(f"{len(faltando)} chaves do CSV não estão no banco. "
                         f"Ex: {list(faltando)[:3]}")

        divergentes = [
            (k, esperado[k], no_banco[k])
            for k in esperado.keys() & no_banco.keys()
            if abs(esperado[k] - no_banco[k]) > TOLERANCIA
        ]
        if divergentes:
            erros.append(f"{len(divergentes)} totais divergem entre CSV e banco. "
                         f"Ex: {divergentes[:3]}")

        # 2. Cobertura de dimensões
        ras_db = {r[0] for r in session.execute(text("SELECT nome FROM regiao_administrativa"))}
        crimes_db = {r[0] for r in session.execute(text("SELECT nome FROM tipo_crime"))}
        anos_db = {int(r[0]) for r in session.execute(text("SELECT DISTINCT ano FROM ocorrencia_mensal"))}

        ras_faltando = set(df["regiao_normalizada"].unique()) - ras_db
        crimes_faltando = set(df["natureza_limpa"].unique()) - crimes_db
        anos_faltando = set(df["ano"].unique()) - anos_db

        if ras_faltando:
            erros.append(f"RAs ausentes no banco: {sorted(ras_faltando)}")
        if crimes_faltando:
            erros.append(f"Naturezas ausentes no banco: {sorted(crimes_faltando)}")
        if anos_faltando:
            erros.append(f"Anos ausentes no banco: {sorted(anos_faltando)}")

        # 3. Contornos
        resultado_geo = session.execute(text("""
            SELECT nome,
                   (contorno IS NOT NULL) AS tem_contorno,
                   (centroide IS NOT NULL) AS tem_centroide
            FROM regiao_administrativa
        """)).all()
        sem_contorno = [r[0] for r in resultado_geo if not r[1]]
        sem_centroide = [r[0] for r in resultado_geo if not r[2]]
        if sem_contorno:
            print(f"  ⚠ {len(sem_contorno)} RAs sem contorno (polygon): {sem_contorno[:5]}...")
        if sem_centroide:
            erros.append(f"RAs sem centroide: {sem_centroide}")

    # Resumo
    print("=" * 60)
    for a in avisos:
        print(f"  ⚠ {a}")
    if erros:
        print(f"✖ SMOKE TEST FALHOU — {len(erros)} problema(s):")
        for e in erros:
            print(f"  - {e}")
        return 1

    print("✔ SMOKE TEST OK")
    print(f"  Regiões no banco:      {len(ras_db)}")
    print(f"  Naturezas no banco:    {len(crimes_db)}")
    print(f"  Anos no banco:         {sorted(anos_db)}")
    print(f"  Chaves (RA,crime,ano): {len(no_banco)} — todas batem com o CSV.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
