-- =====================================================================
-- CrimeMap DF — Schema AUTH (usuários, sessões e auditoria)
-- Aplicado automaticamente na primeira inicialização do container
-- (montado em /docker-entrypoint-initdb.d) e idempotente, então pode
-- ser reaplicado manualmente a qualquer momento:
--     psql "$DATABASE_URL" -f db/auth_schema.sql
-- Ou pela API: POST /api/auth/setup-schema (admin)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS auth;

-- ---------------------------------------------------------------------
-- Tabela: auth.USUARIO
-- Credenciais de acesso ao painel. Senha NUNCA é armazenada em texto:
-- guarda apenas o hash bcrypt (cost 12). E-mail guardado em minúsculas.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auth.usuario (
    id               BIGSERIAL PRIMARY KEY,
    email            VARCHAR(255) NOT NULL,
    nome             VARCHAR(120) NOT NULL,
    senha_hash       VARCHAR(255) NOT NULL,
    papel            VARCHAR(20)  NOT NULL DEFAULT 'usuario'
                     CHECK (papel IN ('admin', 'usuario')),
    ativo            BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ultimo_login_em  TIMESTAMPTZ,
    falhas_login     SMALLINT     NOT NULL DEFAULT 0,
    bloqueado_ate    TIMESTAMPTZ,          -- anti força-bruta (lockout)
    token_reset      VARCHAR(64),          -- sha256 do token de reset
    token_reset_exp  TIMESTAMPTZ,
    CONSTRAINT uq_usuario_email UNIQUE (email),
    CONSTRAINT ck_usuario_papel CHECK (papel IN ('admin', 'usuario'))
);

CREATE INDEX IF NOT EXISTS ix_usuario_ativo ON auth.usuario (ativo);

-- ---------------------------------------------------------------------
-- Tabela: auth.SESSAO_USUARIO
-- Sessões "remember me": guarda apenas SHA-256 do token opaco.
-- O token em claro vive somente no cookie/localStorage do cliente.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auth.sessao_usuario (
    id           BIGSERIAL PRIMARY KEY,
    usuario_id   BIGINT      NOT NULL REFERENCES auth.usuario(id) ON DELETE CASCADE,
    token_hash   CHAR(64)    NOT NULL,          -- SHA-256 hex do token
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em    TIMESTAMPTZ NOT NULL,
    revogada     BOOLEAN     NOT NULL DEFAULT FALSE,
    ip_origem    VARCHAR(64),
    user_agent   VARCHAR(300),
    CONSTRAINT uq_sessao_token UNIQUE (token_hash),
    CONSTRAINT ck_sessao_exp CHECK (expira_em > criado_em)
);

CREATE INDEX IF NOT EXISTS ix_sessao_usuario ON auth.sessao_usuario (usuario_id);
CREATE INDEX IF NOT EXISTS ix_sessao_expira  ON auth.sessao_usuario (expira_em);

-- ---------------------------------------------------------------------
-- Tabela: auth.LOG_ACESSO
-- Trilha de auditoria (sem PII além do e-mail tentado e do IP).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auth.log_acesso (
    id         BIGSERIAL PRIMARY KEY,
    email      VARCHAR(255),
    acao       VARCHAR(40) NOT NULL
               CHECK (acao IN ('LOGIN_OK', 'LOGIN_FALHA', 'LOGOUT',
                               'REGISTRO', 'RESET_SENHA', 'BLOQUEIO')),
    sucesso    BOOLEAN     NOT NULL DEFAULT TRUE,
    ip_origem  VARCHAR(64),
    detalhe    VARCHAR(300),
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_log_acesso_email ON auth.log_acesso (email, criado_em DESC);
