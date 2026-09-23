-- =====================================================================
-- CrimeMap DF — Schema do banco (PostgreSQL + PostGIS)
-- Aplicado automaticamente na primeira inicialização do container.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------
-- Tabela: REGIAO_ADMINISTRATIVA
-- Dimensão geográfica: RAs do Distrito Federal.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regiao_administrativa (
    id        SERIAL PRIMARY KEY,
    nome      VARCHAR(120) UNIQUE NOT NULL,
    codigo    INTEGER UNIQUE NOT NULL,
    contorno  GEOMETRY(MultiPolygon, 4326),
    centroide GEOMETRY(Point, 4326)
);

CREATE INDEX IF NOT EXISTS ix_ra_contorno ON regiao_administrativa USING GIST (contorno);
CREATE INDEX IF NOT EXISTS ix_ra_centroide ON regiao_administrativa USING GIST (centroide);

-- ---------------------------------------------------------------------
-- Tabela: TIPO_CRIME
-- Dimensão: naturezas de crime consolidadas do padrão SSP-DF.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tipo_crime (
    id             SERIAL PRIMARY KEY,
    nome           VARCHAR(160) UNIQUE NOT NULL,
    eixo_indicador VARCHAR(160) NOT NULL,
    descricao      TEXT
);

-- ---------------------------------------------------------------------
-- Tabela: OCORRENCIA_MENSAL
-- Tabela-fato: contagens agregadas por RA / crime / ano / mês.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ocorrencia_mensal (
    id            BIGSERIAL PRIMARY KEY,
    regiao_id     INTEGER NOT NULL REFERENCES regiao_administrativa(id) ON DELETE CASCADE,
    tipo_crime_id INTEGER NOT NULL REFERENCES tipo_crime(id) ON DELETE CASCADE,
    ano           INTEGER NOT NULL,
    mes           INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    tipo_registro VARCHAR(20) NOT NULL DEFAULT 'OCORRENCIA'
                  CHECK (tipo_registro IN ('OCORRENCIA', 'VITIMA')),
    quantidade    INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_ocorrencia_mensal UNIQUE (regiao_id, tipo_crime_id, ano, mes, tipo_registro)
);

CREATE INDEX IF NOT EXISTS ix_ocorrencia_filtros
    ON ocorrencia_mensal (ano, mes, regiao_id, tipo_crime_id);
