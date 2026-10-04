"""
Pipeline de carga: CSV consolidado + GeoJSON de RAs → PostgreSQL/PostGIS.

Etapas:
  1. Cria as tabelas (idempotente — mesmo DDL de db/schema.sql).
  2. Garante o GeoJSON dos contornos das RAs (download com cache em
     data/geo/ra_df.geojson; se indisponível, usa centroides do
     regioes_administrativas.json).
  3. Lê o CSV consolidado (crimemap_consolidadov2.csv) e normaliza
     região administrativa, eixo indicador e natureza.
  4. Despivotagem jan..dez → linhas (regiao, crime, ano, mes, quantidade).
  5. Upsert idempotente em regiao_administrativa, tipo_crime e
     ocorrencia_mensal (pode rodar quantas vezes quiser sem duplicar).

Uso:
    python -m db.load_csv                          # CSV v2 padrão
    python -m db.load_csv --csv <caminho>          # outro CSV
    python -m db.load_csv --sem-contornos          # pula GeoJSON (só centroides)
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.db.models import Base, OcorrenciaMensal, RegiaoAdministrativa, TipoCrime
from api.db.session import SessionLocal, engine

CSV_PADRAO = ROOT_DIR / "api" / "services" / "output" / "crimemap_consolidadov2.csv"
GEO_DIR = ROOT_DIR / "data" / "geo"
GEOJSON_PATH = GEO_DIR / "ra_df.geojson"
JSON_RAS_PATH = ROOT_DIR / "data" / "regioes_administrativas.json"

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]

# ---------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------

def strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_nome_regiao(nome: str) -> str:
    """Normaliza grafias: tira espaços duplicados, coloca em Title Case
    mantendo partículas comuns minúsculas (de, da, do, das, dos)."""
    nome = re.sub(r"\s+", " ", str(nome)).strip()
    particulas = {"de", "da", "do", "das", "dos", "e"}
    palavras = []
    for i, p in enumerate(nome.split(" ")):
        pl = p.lower()
        if i > 0 and pl in particulas:
            palavras.append(pl)
        else:
            palavras.append(p[:1].upper() + p[1:].lower() if p else p)
    return " ".join(palavras)


ALIASES_REGIAO = {
    # unifica grafias divergentes vistas entre arquivos da SSP-DF
    "brasilia": "Brasília",
    "aguas claras": "Águas Claras",
    "arniqueira": "Arniqueira",
    "arniqueiras": "Arniqueira",
    "brazlandia": "Brazlândia",
    "ceilandia": "Ceilândia",
    "candangolandia": "Candangolândia",
    "cruzeiro": "Cruzeiro",
    "fercal": "Fercal",
    "guara": "Guará",
    "guara i": "Guará I",
    "guara ii": "Guará II",
    "itapoa": "Itapoã",
    "jardim botanico": "Jardim Botânico",
    "paranoa": "Paranoá",
    "riacho fundo": "Riacho Fundo",
    "riacho fundo ii": "Riacho Fundo II",
    "santa maria": "Santa Maria",
    "sao sebastiao": "São Sebastião",
    "sudoeste": "Sudoeste/Octogonal",
    "sudoeste octogonal": "Sudoeste/Octogonal",
    "varjao": "Varjão",
    "varjao do torto": "Varjão",  # RA 23 foi renomeada pela SSP-DF (~2024)
    "distrito": "Distrito Federal",  # fallback do ingest em agregados antigos
    "park way": "Park Way",
    "scia estrutural": "SCIA/Estrutural",
    "scia/estrutural": "SCIA/Estrutural",
    "estrutural": "SCIA/Estrutural",
    "sobradinho ii": "Sobradinho II",
    "lago sul": "Lago Sul",
    "lago norte": "Lago Norte",
    "nucleo bandeirante": "Núcleo Bandeirante",
    "recanto das emas": "Recanto das Emas",
    "vicente pires": "Vicente Pires",
    "distrito federal": "Distrito Federal",
    "plano piloto": "Plano Piloto",
    "planaltina": "Planaltina",
    "samambaia": "Samambaia",
    "gama": "Gama",
    "taguatinga": "Taguatinga",
    "sobradinho": "Sobradinho",
    "sia": "SIA",
    "s.i.a.": "SIA",
    "scia": "SCIA",
    "sol": "Sol Nascente/Pôr do Sol",
    "sol nascente": "Sol Nascente/Pôr do Sol",
    "sol nascente/por do sol": "Sol Nascente/Pôr do Sol",
    "sol nascente/por do sol (4)": "Sol Nascente/Pôr do Sol",
}


def resolver_regiao(nome_bruto: str) -> str:
    """Resolve apelidos/grafias para o nome oficial da RA.
    Remove sufixos de downloads duplicados ex: 'Arniqueira (4)' -> 'Arniqueira'."""
    bruto = re.sub(r"\s+", " ", str(nome_bruto)).strip()
    bruto = re.sub(r"\s*\(\d+\)\s*$", "", bruto)  # sufixo ' (N)' de re-download
    chave = re.sub(r"\s+", " ", strip_accents(bruto).strip().lower())
    chave = chave.replace("-", " ").replace("/", " ")
    if chave in ALIASES_REGIAO:
        return ALIASES_REGIAO[chave]
    # tenta também com separadores preservados (caso 'scia/estrutural')
    chave2 = re.sub(r"\s+", " ", strip_accents(bruto).strip().lower())
    if chave2 in ALIASES_REGIAO:
        return ALIASES_REGIAO[chave2]
    return normalizar_nome_regiao(bruto)


def limpar_eixo(eixo_bruto: str) -> str:
    """Remove prefixos numéricos e espaços duplicados do eixo indicador.
    Ex: '2. C.C.P. -      CRIMES CONTRA O PATRIMÔNIO' → 'C.C.P. - CRIMES CONTRA O PATRIMÔNIO'"""
    eixo = re.sub(r"^\s*\d+\.\s*", "", str(eixo_bruto))
    eixo = re.sub(r"\s+", " ", eixo).strip()
    if eixo.upper() == "TOTAL":
        return "TOTAL (resumo)"
    return eixo


def limpar_natureza(nat: str) -> str:
    """Remove asteriscos de nota de rodapé e espaços duplicados."""
    nat = re.sub(r"\s*\*+\s*$", "", str(nat))
    nat = re.sub(r"\s+", " ", nat).strip()
    return nat


# ---------------------------------------------------------------------
# Contornos (GeoJSON) e fallback de centroides
# ---------------------------------------------------------------------

GEOJSON_REPO = "https://raw.githubusercontent.com/caefleury/geodata-distrito-federal-brasil/main/geojson-data"

# Centro geográfico aproximado do DF (usado para o agregado 'Distrito Federal')
DF_CENTER_LAT, DF_CENTER_LON = -15.7942, -47.8822

# O GeoJSON disponível divide RAs grandes em sub-regiões; este mapa une
# as partes (nomes já normalizados por resolver_regiao) na RA oficial.
MERGE_POLIGONOS = {
    "Brasília": ["Asa Norte", "Asa Sul", "Vila Planalto", "Noroeste"],
    "Ceilândia": ["Ceilândia Norte", "Ceilândia Sul"],
    "Guará": ["Guará I", "Guará II"],
    "Taguatinga": ["Taguatinga Norte", "Taguatinga Sul"],
    "Arniqueira": ["Arniqueiras", "Água Quente"],
    "Riacho Fundo": ["Riacho Fundo I"],
    "SCIA/Estrutural": ["SCIA", "26 de Setembro", "Café Sem Troco", "Taquari"],
    "Sudoeste/Octogonal": ["Sudoeste", "Octogonal"],
}


def baixar_geojson_ras() -> dict | None:
    """Garante o GeoJSON das RAs do DF em data/geo/ra_df.geojson.
    Fonte: repositório 'geodata-distrito-federal-brasil' (GitHub), um
    arquivo por RA (ex: 01-gama.geo.json) com 'properties.name'.
    Usa cache local mesclado; retorna None se não conseguir."""
    if GEOJSON_PATH.exists():
        try:
            return json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠ Cache de GeoJSON corrompido ({e}); refazendo download...")

    try:
        import requests

        print("  ⬇ Baixando contornos das RAs (geodata-distrito-federal-brasil)...")
        resp = requests.get(
            "https://api.github.com/repos/caefleury/geodata-distrito-federal-brasil/contents/geojson-data",
            timeout=30,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        arquivos = [a["name"] for a in resp.json() if a["name"].endswith(".geo.json")]
        # ignora o arquivo do DF inteiro (agregado, não é uma RA)
        arquivos = [a for a in arquivos if a != "01-distrito-federal.geo.json"]
        print(f"    {len(arquivos)} arquivos de RA encontrados")

        features = []
        for nome_arq in arquivos:
            r = requests.get(f"{GEOJSON_REPO}/{nome_arq}", timeout=30)
            r.raise_for_status()
            features.extend(r.json().get("features", []))

        data = {"type": "FeatureCollection", "features": features}
        GEO_DIR.mkdir(parents=True, exist_ok=True)
        GEOJSON_PATH.write_text(json.dumps(data), encoding="utf-8")
        print(f"  ✔ {len(features)} feições salvas em {GEOJSON_PATH}")
        return data
    except Exception as e:
        print(f"  ⚠ Não foi possível baixar o GeoJSON das RAs: {e}")
        print(f"    Dica: coloque um GeoJSON manualmente em {GEOJSON_PATH}")
        return None


def carregar_centroides_fallback() -> dict[str, tuple[float, float]]:
    """Centroides aproximados das principais RAs (regioes_administrativas.json)."""
    if not JSON_RAS_PATH.exists():
        return {}
    data = json.loads(JSON_RAS_PATH.read_text(encoding="utf-8"))
    return {
        r["nome"]: (r["latitude"], r["longitude"])
        for r in data.get("regioes", [])
    }


def extrair_poligonos_por_nome(geojson: dict) -> dict[str, dict]:
    """Mapeia nome (normalizado) → {polygon: shapely, ra_codigo: int|None}.
    O GeoJSON disponível usa sub-regiões (ex: Ceilândia Norte/Sul, Asa
    Norte/Sul); MERGE_POLIGONOS une essas partes na RA oficial."""
    from shapely.geometry import MultiPolygon, shape
    from shapely.ops import unary_union

    brutos: dict[str, dict] = {}
    for feat in geojson.get("features", []):
        props = feat.get("properties", {}) or {}
        nome_bruto = (
            props.get("NOME") or props.get("nome") or props.get("NOME_RA")
            or props.get("RA_NOME") or props.get("name")
        )
        if not nome_bruto:
            continue
        geom = shape(feat["geometry"])
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        codigo = props.get("CD_RA") or props.get("codigo") or props.get("CODIGO")
        try:
            codigo = int(codigo) if codigo is not None else None
        except (ValueError, TypeError):
            codigo = None
        nome_final = resolver_regiao(nome_bruto)
        # Se um arquivo do GeoJSON resolver para o nome de uma RA mesclada
        # (ex: 'Arniqueiras' → 'Arniqueira' pelo alias do CSV), ele é uma
        # PARTE dessa RA — mantém o nome normalizado p/ a união funcionar.
        if nome_final in MERGE_POLIGONOS:
            nome_final = normalizar_nome_regiao(nome_bruto)
        brutos[nome_final] = {"polygon": geom, "codigo": codigo}

    def _reparar(geom):
        """Corrige topologia inválida (auto-interseções do fonte)."""
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom

    out = {}
    for alvo, partes in MERGE_POLIGONOS.items():
        pecas = [_reparar(brutos[p]["polygon"]) for p in partes if p in brutos]
        if pecas:
            unido = unary_union(pecas) if len(pecas) > 1 else pecas[0]
            if unido.geom_type == "Polygon":
                unido = MultiPolygon([unido])
            out[alvo] = {"polygon": unido, "codigo": None}
    # RAs que já vêm direto no GeoJSON — exceto as partes já absorvidas por
    # uma RA mesclada acima (ex: 'Asa Sul' dentro de 'Brasília'), que ficariam
    # como polígonos sobrepostos "duplicados" no mapa coropleto.
    partes_consumidas = {p for partes in MERGE_POLIGONOS.values() for p in partes}
    for nome, dados in brutos.items():
        if nome in partes_consumidas:
            continue
        out.setdefault(nome, dados)
    return out


# ---------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------

def preparar_dataframe(caminho_csv: Path) -> pd.DataFrame:
    """Lê o CSV consolidado e aplica toda a normalização + deduplicação.
    Compartilhado entre a carga (carregar_base) e o smoke test, para que
    ambos comparem exatamente os mesmos dados."""
    df = pd.read_csv(caminho_csv, encoding="utf-8-sig")
    df["regiao_normalizada"] = df["regiao_administrativa"].apply(resolver_regiao)
    df["eixo_limpo"] = df["eixo_indicador"].apply(limpar_eixo)
    df["natureza_limpa"] = df["natureza"].apply(limpar_natureza)
    # tipo_registro canônico sem acento (OCORRENCIA | VITIMA)
    df["tipo_registro_normalizado"] = (
        df["tipo_registro"].astype(str).apply(strip_accents).str.upper().str.strip()
    )
    df.loc[~df["tipo_registro_normalizado"].isin(["OCORRENCIA", "VITIMA"]),
           "tipo_registro_normalizado"] = "OCORRENCIA"

    # Remapeia eixo 'TOTAL (resumo)' pelo conteúdo da natureza
    # (ex: 'VÍTIMAS C.V.L.I.' pertence ao eixo C.V.L.I.)
    mask_total = df["eixo_limpo"] == "TOTAL (resumo)"
    df.loc[mask_total & df["natureza_limpa"].str.contains("C.V.L.I.", na=False), "eixo_limpo"] = (
        "C.V.L.I. - CRIMES VIOLENTOS LETAIS INTENCIONAIS"
    )

    # Remove duplicatas do CSV: re-downloads do portal colocam o mesmo
    # (RA, natureza, ano, tipo_registro) em mais de um arquivo. Agrega
    # tomando o valor MÁXIMO por mês de cada grupo (arquivos idênticos
    # ficam inalterados; entre divergentes, preserva o maior).
    meses_todos = MESES + ["total_ano"]
    agregacoes = {col: "max" for col in meses_todos}
    if "codigo_ra_arquivo" in df.columns:
        agregacoes["codigo_ra_arquivo"] = "first"
    if "eixo_limpo" in df.columns:
        agregacoes["eixo_limpo"] = "first"
    df = df.groupby(
        ["regiao_normalizada", "natureza_limpa", "ano", "tipo_registro_normalizado"],
        as_index=False,
    ).agg(agregacoes)
    return df


def criar_extensao_postgis():
    """Garante a extensão PostGIS no banco. Necessário quando o schema.sql
    não foi aplicado por entrypoint (ex: Postgres na nuvem, tipo Neon)."""
    with SessionLocal() as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        session.commit()
        print("  ✔ Extensão PostGIS disponível")


def carregar_base() -> dict:
    """Executa a carga completa. Retorna resumo para logs/endpoint."""
    resumo: dict = {"regioes": 0, "crimes": 0, "registros_inseridos": 0,
                    "avisos": []}

    print("🔧 Criando tabelas (idempotente)...")
    criar_extensao_postgis()
    Base.metadata.create_all(engine)

    # --- 1. CSV consolidado -------------------------------------------
    if not CSV_PADRAO.exists():
        raise FileNotFoundError(f"CSV consolidado não encontrado: {CSV_PADRAO}")

    print(f"📄 Lendo {CSV_PADRAO.name}...")
    df = preparar_dataframe(CSV_PADRAO)

    regioes_unicas = sorted(df["regiao_normalizada"].unique())
    crimes_unicos = df[["natureza_limpa", "eixo_limpo"]].drop_duplicates()
    print(f"  → {len(regioes_unicas)} RAs | {len(crimes_unicos)} naturezas | {len(df)} linhas")

    # --- 2. Contornos das RAs ------------------------------------------
    poligonos: dict[str, dict] = {}
    if not getattr(carregar_base, "_sem_contornos", False):
        geojson = baixar_geojson_ras()
        if geojson:
            poligonos = extrair_poligonos_por_nome(geojson)
    centroides_fallback = carregar_centroides_fallback()

    # Garante que TODAS as RAs com contorno conhecido existam na dimensão,
    # mesmo sem nenhuma ocorrência no CSV — assim o mapa coropleto exibe o
    # DF completo (RAs sem dados aparecem em cinza no frontend).
    if poligonos:
        faltantes = [r for r in poligonos
                     if r not in regioes_unicas and r != "Distrito Federal"]
        if faltantes:
            print(f"  ➕ {len(faltantes)} RAs sem dados no CSV adicionadas ao mapa: "
                  f"{faltantes[:6]}{'...' if len(faltantes) > 6 else ''}")
            regioes_unicas = sorted(set(regioes_unicas) | set(faltantes))

    print("💾 Carregando dimensões no banco (upsert idempotente)...")
    with SessionLocal() as session:
        # --- 3. Upsert de regiões ----------------------------------------
        map_regiao_id: dict[str, int] = {}
        for nome in regioes_unicas:
            poly_data = poligonos.get(nome)
            centroide_wkt = None
            contorno_wkt = None
            codigo = None

            if poly_data:
                geom = poly_data["polygon"]
                c = geom.centroid
                contorno_wkt = f"SRID=4326;{geom.wkt}"
                centroide_wkt = f"SRID=4326;POINT({c.x} {c.y})"
                codigo = poly_data["codigo"]

            if codigo is None:
                # fallback: código pelo JSON local (ra_numero) ou pelo CSV
                mask = df["regiao_normalizada"] == nome
                codigos_csv = df.loc[mask, "codigo_ra_arquivo"].dropna().unique()
                if len(codigos_csv) > 0:
                    codigo = int(codigos_csv[0])
                else:
                    for ra_json, (lat, lon) in centroides_fallback.items():
                        if resolver_regiao(ra_json) == nome:
                            centroide_wkt = f"SRID=4326;POINT({lon} {lat})"
                            break

            if codigo == -1:
                resumo["avisos"].append(f"RA '{nome}' sem código — usando placeholder -1")
            codigo_final = codigo if codigo is not None else -1

            if centroide_wkt is None and nome in centroides_fallback:
                lat, lon = centroides_fallback[nome]
                centroide_wkt = f"SRID=4326;POINT({lon} {lat})"

            # 'Distrito Federal' é o agregado estadual (não é RA mapeável);
            # recebe o centro geográfico do DF para servir ao heatmap.
            if centroide_wkt is None and nome == "Distrito Federal":
                centroide_wkt = f"SRID=4326;POINT({DF_CENTER_LON} {DF_CENTER_LAT})"

            stmt = pg_insert(RegiaoAdministrativa).values(
                nome=nome, codigo=codigo_final,
                contorno=contorno_wkt, centroide=centroide_wkt,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["nome"],
                set_={
                    "codigo": codigo_final,
                    "contorno": stmt.excluded.contorno,
                    "centroide": stmt.excluded.centroide,
                },
            )
            session.execute(stmt)

        session.flush()
        regs = session.query(RegiaoAdministrativa.id, RegiaoAdministrativa.nome).all()
        map_regiao_id = {nome: rid for rid, nome in regs}
        resumo["regioes"] = len(regs)

        # --- 4. Upsert de tipos de crime ---------------------------------
        map_crime_id: dict[tuple, int] = {}
        for _, row in crimes_unicos.iterrows():
            nat = row["natureza_limpa"]
            eixo = row["eixo_limpo"]
            stmt = pg_insert(TipoCrime).values(
                nome=nat, eixo_indicador=eixo,
                descricao=f"Natureza '{nat}' do eixo {eixo} (padrão SSP-DF).",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["nome"], set_={"eixo_indicador": eixo},
            )
            session.execute(stmt)

        session.flush()
        crimes_db = session.query(TipoCrime.id, TipoCrime.nome).all()
        map_crime_id = {nome: cid for cid, nome in crimes_db}
        resumo["crimes"] = len(crimes_db)

        # --- 5. Despivotagem + upsert do fato ----------------------------
        print("📊 Despivotando meses e carregando ocorrência_mensal...")
        registros = []
        for _, row in df.iterrows():
            rid = map_regiao_id.get(row["regiao_normalizada"])
            cid = map_crime_id.get(row["natureza_limpa"])
            if rid is None or cid is None:
                resumo["avisos"].append(
                    f"Linha ignorada (RA/crime não mapeado): {row['regiao_administrativa']} / {row['natureza']}"
                )
                continue
            ano = int(row["ano"])
            treg = str(row["tipo_registro_normalizado"])
            for mes, coluna in enumerate(MESES, start=1):
                qtd = int(row.get(coluna, 0) or 0)
                registros.append({
                    "regiao_id": rid, "tipo_crime_id": cid,
                    "ano": ano, "mes": mes, "tipo_registro": treg,
                    "quantidade": qtd,
                })

        if registros:
            # insert em blocos para não estourar memória
            BLOCO = 5000
            total = 0
            for i in range(0, len(registros), BLOCO):
                bloco = registros[i:i + BLOCO]
                stmt = pg_insert(OcorrenciaMensal).values(bloco)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_ocorrencia_mensal",
                    set_={"quantidade": stmt.excluded.quantidade},
                )
                session.execute(stmt)
                total += len(bloco)
                if (i // BLOCO) % 4 == 0:
                    print(f"    {total}/{len(registros)} linhas...")
            resumo["registros_inseridos"] = total

        session.commit()

    print(f"\n✔ Carga concluída: {resumo['regioes']} RAs, "
          f"{resumo['crimes']} naturezas, {resumo['registros_inseridos']} registros mensais.")
    if resumo["avisos"]:
        print(f"⚠ {len(resumo['avisos'])} aviso(s):")
        for a in resumo["avisos"][:10]:
            print(f"  - {a}")
    return resumo


def main():
    global CSV_PADRAO

    parser = argparse.ArgumentParser(description="Carga do CSV consolidado no Postgres")
    parser.add_argument("--csv", default=str(CSV_PADRAO), help="CSV consolidado de entrada")
    parser.add_argument("--sem-contornos", action="store_true",
                        help="Não baixar/inserir poligonos (só centroides)")
    args = parser.parse_args()

    if args.csv:
        CSV_PADRAO = Path(args.csv)
    if args.sem_contornos:
        carregar_base._sem_contornos = True

    carregar_base()


if __name__ == "__main__":
    main()
