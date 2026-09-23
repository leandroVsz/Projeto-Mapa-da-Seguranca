# 🛡️ Mapa da Segurança - Distrito Federal (DF)

Sistema web geoespacial para análise e visualização da violência e criminalidade no Distrito Federal através de **mapas de calor interativos**, indicadores estatísticos e central de consolidação de dados da Secretaria de Segurança Pública (SSP-DF).

Projeto desenvolvido para a disciplina de **Soluções Computacionais (8º Semestre) - Universidade Católica de Brasília (UCB)**.

---

## 🏛️ Arquitetura do Sistema (100% Python)

O sistema foi desenhado com foco em **separação de responsabilidades** e facilidade de execução:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   FRONTEND WEB (Streamlit Dashboard)                   │
│  - Mapa Coropleto por RA (polígonos GeoJSON) + Heatmap 2D e 3D         │
│  - Filtros: RAs, Eixos Indicadores, Crimes, Períodos e Anos            │
│  - Cards de KPIs e Indicadores de Segurança Pública                    │
│  - Gráficos estatísticos e tendências temporais                        │
│  - Tabela detalhada de ocorrências com busca e exportação CSV          │
│  - Interface visual para ingestão e consolidação de dados (ETL)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Requisições HTTP / JSON
┌───────────────────────────────────▼────────────────────────────────────┐
│                        BACKEND (API REST FastAPI)                      │
│                                                                        │
│  - Endpoints REST documentados automaticamente no Swagger (/docs)      │
│  - Agregações estatísticas via SQL (GROUP BY no PostgreSQL)            │
│  - Coropleto, heatmap ponderado e séries mensais reais                 │
│  - Pipeline ETL: CSV consolidado → PostgreSQL/PostGIS                  │
│  - Fallback transparente para CSV/simulado se o banco estiver offline  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ SQL (SQLAlchemy + PostGIS)
┌───────────────────────────────────▼────────────────────────────────────┐
│              BANCO DE DADOS (PostgreSQL + PostGIS via Docker)          │
│  - regiao_administrativa: RAs com contorno (polígono) e centroide      │
│  - tipo_crime: naturezas + eixo indicador (padrão SSP-DF)              │
│  - ocorrencia_mensal: fato com contagens por RA/crime/ano/mês          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Carga (db/load_csv.py)
┌───────────────────────────────────▼────────────────────────────────────┐
│                     CAMADA DE DADOS UNIFICADA (data/)                  │
│  - CSV consolidado da SSP-DF (api/services/output/)                    │
│  - GeoJSON dos contornos das RAs (data/geo/)                           │
│  - Base de ocorrências simuladas (fallback offline)                    │
│  - Diretório raw/ para planilhas anuais baixadas                       │
│  - Diretório processed/ para arquivos consolidados                     │
└────────────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> **Zero Dependências de Node.js**: O ambiente é **100% Python**. Nenhum colega precisa instalar Node.js ou lidar com npm. Um simples `pip install -r requirements.txt` configura todo o projeto tanto no Windows quanto no Linux.

---

## 🚀 Como Executar o Projeto

### 🪟 No Windows (1 Clique)
1. Dê um duplo clique no arquivo:
   ```cmd
   run.bat
   ```
2. O script detectará o ambiente, ativará o `venv` e iniciará automaticamente a **API REST** e o **Web App Streamlit**.
   - **Streamlit**: [http://localhost:8501](http://localhost:8501)
   - **API REST (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

> 📖 Para um guia passo a passo detalhado, consulte [SETUP_WINDOWS.md](SETUP_WINDOWS.md).

---

### 🐧 No Linux / macOS
```bash
# Executa API e Streamlit simultaneamente:
./run.sh

# Ou diretamente pelo Python:
python3 run.py
```

### ⚡ Execução Individual dos Serviços
Caso queira rodar apenas um dos serviços:
```bash
# Apenas a aplicação Web Streamlit:
python run.py app

# Apenas o servidor Backend API FastAPI:
python run.py api
```

---

## 🗄️ Banco de Dados (PostgreSQL + PostGIS)

O backend consulta um banco PostgreSQL com extensão PostGIS, subido via Docker:

```bash
# 1. Subir o banco (na primeira vez cria as tabelas automaticamente):
docker compose up -d

# 2. Configurar conexão (opcional — o padrão já funciona):
cp .env.example .env

# 3. Carregar os dados reais (CSV consolidado + contornos das RAs):
python -m db.load_csv

# 4. Validar a carga (totais do banco × CSV):
python -m db.smoke_test
```

---

## 🔐 Autenticação e Usuários

O sistema conta com login/registro de usuários armazenados **no mesmo banco PostgreSQL, em um schema separado chamado `auth`** (isolamento lógico sem precisar de segunda instância):

| Tabela | Papel |
|---|---|
| `auth.usuario` | E-mail (único), nome, hash bcrypt da senha, papel (admin/usuario), status, lockout anti-força-bruta, token de reset |
| `auth.sessao_usuario` | Sessões "manter conectado" — guarda apenas o SHA-256 do token opaco |
| `auth.log_acesso` | Auditoria: logins, falhas, bloqueios, registros e resets |

### Segurança implementada

- **bcrypt (cost 12)** com sal aleatório por usuário — senha nunca é armazenada nem logada
- **Mensagens de erro genéricas** (não revela se um e-mail existe)
- **Lockout progressivo**: 5 falhas ⇒ conta bloqueada por 15 minutos
- **Tokens de sessão opacos** (`secrets.token_urlsafe`), guardados apenas como SHA-256 no banco, com revogação
- **Reset de senha por token de uso único** (30 min), revogando todas as sessões
- **Auditoria completa** de acessos em `auth.log_acesso`

### Como usar

**No Streamlit** — aba **"👤 Conta & Acesso"**: login, registro, troca de senha e (para admins) gestão de usuários. Por padrão o painel é aberto a visitantes; para exigir login, defina no `.env`:

```env
AUTH_REQUIRED=true
```

**Pela API** — endpoints documentados no Swagger (`/docs`), autenticando com o header `X-Auth-Token`:

```
POST /api/auth/registro          -> cria conta e já devolve token
POST /api/auth/login             -> autentica (e-mail, senha, lembrar)
POST /api/auth/logout            -> encerra a sessão
GET  /api/auth/eu                -> dados do usuário autenticado
POST /api/auth/trocar-senha      -> troca a própria senha
POST /api/auth/reset/solicitar   -> gera token de redefinição (30 min)
POST /api/auth/reset/confirmar   -> redefine a senha com o token
GET  /api/auth/health            -> status do subsistema de autenticação
```

**Pela linha de comando** (requer banco no ar):

```bash
# Aplicar/verificar o schema auth (idempotente)
python -m db.auth_admin schema

# Criar o primeiro administrador (senha pedida sem eco)
python -m db.auth_admin criar --nome "Admin UCB" --email admin@ucb.br --admin

# Outros comandos: listar | promover | rebaixar | ativar | desativar | reset-senha
python -m db.auth_admin listar

# Validar todo o ciclo de autenticação (registro, lockout, sessões, reset...)
python -m db.auth_smoke_test
```

> Requer **Docker Desktop** (Windows/Mac) ou Docker Engine (Linux). Sem o banco no ar, o sistema continua funcionando no modo fallback (dados simulados), apenas sem o mapa coropleto e o filtro de eixos.

### Modelo de dados

| Tabela | Papel | Colunas principais |
|---|---|---|
| `regiao_administrativa` | Dimensão geográfica | `id`, `nome` (único), `codigo` (único), `contorno` (GEOMETRY MultiPolygon), `centroide` (GEOMETRY Point) |
| `tipo_crime` | Dimensão de crimes | `id`, `nome` (único), `eixo_indicador`, `descricao` |
| `ocorrencia_mensal` | Fato (contagens) | `regiao_id` (FK), `tipo_crime_id` (FK), `ano`, `mes`, `tipo_registro`, `quantidade` — único por (RA, crime, ano, mês, tipo) |

A carga (`db/load_csv.py`) é **idempotente** (upsert): pode ser rodada sempre que um novo CSV consolidado for gerado, sem duplicar registros.

---

## 🗺️ Regiões Administrativas e Dados do DF

O sistema conta com dados e coordenadas representativas das principais Regiões Administrativas do DF:
- **Ceilândia**, **Taguatinga**, **Samambaia**, **Plano Piloto**, **Gama**, **Guará**, **Águas Claras**, **Santa Maria**, **Planaltina**, **Sobradinho**, **Recanto das Emas**, **São Sebastião**, **Paranoá** e **Vicente Pires**.

### Naturezas de Crimes Mapeadas (Padrão SSP-DF):
- Homicídio Doloso
- Latrocínio (Roubo seguido de morte)
- Roubo a Transeunte (Pedestres)
- Roubo de Veículo
- Roubo em Coletivo (Ônibus)
- Roubo a Comércio
- Furto a Transeunte / Veículo
- Violência Doméstica
- Tráfico de Drogas

---

## ⚙️ Estratégia de Consolidação de Dados (ETL)

Quando o grupo começar a utilizar os **dados reais baixados da SSP-DF** (onde cada arquivo representa um ano de uma cidade específica):

1. Salve os arquivos brutos baixados dentro da pasta:
   ```
   data/raw/
   ```
   *Exemplo:* `ceilandia_2021.csv`, `ceilandia_2022.csv`, `taguatinga_2022.csv`.

2. Execute a consolidação:
   - Pelo Streamlit: Abra a aba **⚙️ Central de Consolidação (ETL)** e clique em **Executar Consolidação**.
   - Pela API: Faça um `POST` em `/api/consolidar` (pelo Swagger).
   - Pelo terminal:
     ```bash
     python -c "from api.services.data_ingestion import consolidar_arquivos_por_cidade; consolidar_arquivos_por_cidade()"
     ```

3. **Resultado**: O pipeline gerará os arquivos unificados por cidade em `data/processed/cidades/` e a base mestre consolidada de todo o Distrito Federal em `data/processed/ocorrencias_df_master.csv`.

---

## 🔌 Endpoints da API REST (FastAPI)

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Status do servidor + do banco PostgreSQL (com fallback) |
| `GET` | `/api/regioes` | RAs com contorno GeoJSON, código e centroide |
| `GET` | `/api/filtros` | Opções de filtros: RAs, crimes, **eixos indicadores**, anos |
| `GET` | `/api/heatmap` | Matriz `[lat, lon, peso]` (centroides ponderados) |
| `GET` | `/api/coropleto` | Intensidade por RA `{nome, total}` para o mapa coropleto |
| `GET` | `/api/ocorrencias` | Listagem agregada RA/crime/ano/mês com busca textual |
| `GET` | `/api/stats` | Indicadores-chave (KPIs) e séries por ano/mês |
| `POST`| `/api/consolidar` | Executa a unificação de arquivos brutos anuais (ETL) |
| `POST`| `/api/carga-db` | Carrega o CSV consolidado + contornos no PostgreSQL |

Documentação interativa Swagger disponível em: **[http://localhost:8000/docs](http://localhost:8000/docs)**.
