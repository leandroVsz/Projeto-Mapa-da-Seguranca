# 🪟 Guia de Configuração de Ambiente no Windows

Este guia foi elaborado para que os colegas de equipe configurem e executem o **Mapa da Segurança DF** no Windows com rapidez e sem problemas de ambiente.

> [!NOTE]
> O projeto é **100% Python**. Não é necessário instalar Node.js, npm ou compiladores extras — todas as bibliotecas abaixo possuem *wheels* pré-compilados para Windows.

---

## 1. Pré-requisitos

### 1.1 Python 3.10 ou superior (**obrigatório**)

1. Baixe o instalador oficial do Python em: [python.org/downloads](https://www.python.org/downloads/)
2. ⚠️ **ATENÇÃO (Passo Crucial)**: Na primeira tela da instalação, marque a caixa:
   - ☑️ **"Add python.exe to PATH"** (Adicionar Python às variáveis de ambiente).
3. Conclua a instalação padrão.
4. Verifique no CMD:

```cmd
python --version
:: Deve exibir Python 3.10.x ou superior (testado até 3.14)
```

### 1.2 Docker Desktop (**opcional** — apenas para os dados reais)

Necessário somente se você quiser o banco **PostgreSQL + PostGIS** com os dados reais da SSP-DF (mapa coropleto completo, filtro por Eixo Indicador). Sem ele, o sistema roda em modo fallback com dados de demonstração.

Download: [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)

---

## 2. Bibliotecas Python Utilizadas (`requirements.txt`)

Todas são instaladas automaticamente pelo `pip install -r requirements.txt`. Resumo do papel de cada uma:

### 🖥️ Interface Web (Dashboard Streamlit)

| Biblioteca | Versão mín. | Para que serve |
|---|---|---|
| `streamlit` | 1.36 | Framework do painel web (abas, filtros, gráficos). A partir da 1.36 renderiza o mapa PyDeck com **MapLibre**, sem necessidade de token Mapbox |
| `pydeck` | 0.8 | Camadas do mapa geoespacial: coropleto (GeoJSON), heatmap 2D e hexágonos 3D |
| `pandas` | 2.0 | Leitura/manipulação de CSVs (fallback, ETL e carga no banco) |
| `numpy` | 1.24 | Base numérica do pandas; geração da base de dados de demonstração |

### ⚙️ Backend (API REST)

| Biblioteca | Versão mín. | Para que serve |
|---|---|---|
| `fastapi` | 0.110 | Framework da API REST (`/api/regioes`, `/api/heatmap`, `/api/stats`...) |
| `uvicorn` | 0.29 | Servidor ASGI que executa a API na porta 8000 |
| `pydantic` | 2.6 | Validação dos modelos de requisição/resposta (dependência do FastAPI) |
| `requests` | 2.31 | Cliente HTTP: o Streamlit consome a API; pipeline baixa os contornos GeoJSON das RAs |
| `python-dotenv` | 1.0 | Carrega o `.env` (DATABASE_URL, AUTH_REQUIRED) |

### 🗄️ Banco de Dados (PostgreSQL + PostGIS)

| Biblioteca | Versão mín. | Para que serve |
|---|---|---|
| `sqlalchemy` | 2.0 | ORM, engine de conexão e upserts idempotentes da carga |
| `psycopg2-binary` | 2.9 | Driver PostgreSQL (versão binária — não exige compilação) |
| `geoalchemy2` | 0.14 | Tipos geométricos PostGIS (`GEOMETRY(MultiPolygon, 4326)`) nos modelos |
| `shapely` | 2.0 | Operações com geometrias: união de polígonos das RAs, centroides, WKB/WKT ↔ GeoJSON |

### 🔐 Autenticação

| Biblioteca | Versão mín. | Para que serve |
|---|---|---|
| `bcrypt` | 4.0 | Hash seguro de senhas (cost 12) do subsistema de login/registro |

### 📊 Ingestão de Planilhas SSP-DF

| Biblioteca | Versão mín. | Para que serve |
|---|---|---|
| `openpyxl` | 3.1 | Leitura das planilhas `.xlsx` baixadas do portal da SSP-DF (`data/raw/`) |
| `xlrd` | 2.0 | Leitura dos arquivos `.xls` agregados antigos |

### Instalação manual das bibliotecas (se preferir)

```cmd
pip install streamlit pydeck pandas numpy fastapi uvicorn pydantic requests python-dotenv sqlalchemy psycopg2-binary geoalchemy2 shapely bcrypt openpyxl xlrd
```

---

## 3. Inicialização em Um Clique (Recomendado)

1. Abra a pasta do projeto no Windows Explorer.
2. Dê um duplo clique no arquivo:
   ```cmd
   run.bat
   ```
3. O script fará tudo de forma automática:
   - Criará o ambiente virtual `venv` caso ainda não exista.
   - Instalará todas as bibliotecas da tabela acima (`requirements.txt`).
   - Inicializará a base de dados de demonstração do DF.
   - Abrirá tanto o **Web App Streamlit** quanto a **API REST (FastAPI)**.

---

## 4. URLs do Sistema

Após a inicialização:
- **Painel Web (Streamlit)**: [http://localhost:8501](http://localhost:8501)
- **Documentação Swagger da API**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 5. Execução Manual pelo Prompt de Comando (CMD)

Se preferir rodar manualmente comando por comando:

```cmd
:: 1. Criar o ambiente virtual (apenas na primeira vez)
python -m venv venv

:: 2. Ativar o ambiente virtual
venv\Scripts\activate.bat

:: 3. Instalar as dependências
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 4. Iniciar todo o sistema (API + Streamlit)
python run.py

:: (Opcional) Se quiser rodar apenas o Streamlit:
:: python run.py app

:: (Opcional) Se quiser rodar apenas a API:
:: python run.py api
```

---

## 6. Verificando a Instalação

Para confirmar que tudo foi instalado corretamente, com o venv ativado rode:

```cmd
python -c "import streamlit, pydeck, pandas, numpy, fastapi, uvicorn, pydantic, requests, dotenv, sqlalchemy, psycopg2, geoalchemy2, shapely, bcrypt, openpyxl, xlrd; print('OK - todas as bibliotecas importadas com sucesso!')"
```

Se aparecer `OK - todas as bibliotecas importadas com sucesso!`, o ambiente está pronto. Se algum módulo falhar, rode `pip install -r requirements.txt` novamente.

---

## 7. Banco de Dados

Você tem **duas opções** — escolha uma:

### Opção A: Banco na nuvem, sem Docker (mais fácil — recomendado)

Não exige virtualização nem Docker Desktop — funciona em qualquer PC.

1. Crie um banco PostgreSQL gratuito com PostGIS em [neon.tech](https://neon.tech):
   - Cadastro (pode usar conta Google/GitHub) → **Create project**
   - Copie a **Connection string** (formato `postgresql://usuario:senha@ep-xxx.../neondb`)
2. Configure o projeto:
   ```cmd
   copy .env.example .env
   ```
   Abra o `.env` no bloco de notas e ajuste a linha `DATABASE_URL` para a connection string do Neon, **mantendo a parte `+psycopg2`** e **adicionando `?sslmode=require`** ao final:
   ```env
   DATABASE_URL=postgresql+psycopg2://usuario:senha@ep-xxx.neon.tech/neondb?sslmode=require
   ```
3. Ative o venv e rode a carga (cria tabelas, extensão PostGIS, baixa os contornos GeoJSON e popula tudo):
   ```cmd
   venv\Scripts\activate.bat
   python -m db.load_csv
   python -m db.smoke_test
   ```
4. Inicie o sistema (`run.bat`) — o painel exibirá o mapa coropleto completo com as RAs do DF.

> [!TIP]
> Esse mesmo banco serve depois para o **deploy no Streamlit Cloud**: lá, a connection string é configurada como *secret* (`DATABASE_URL`) e a variável `EMBED_API=true` faz o app subir a API no mesmo processo. Sem servidor separado.

### Opção B: PostgreSQL local via Docker

> [!WARNING]
> O Docker Desktop exige **virtualização** ativa (BIOS/UEFI + WSL2). Se aparecer o erro
> "Virtualization support not detected", use a **Opção A** — ou solicite ao suporte/da
> instituição a liberação da virtualização.

Por padrão, o sistema roda com dados de demonstração. Para usar os **dados reais da SSP-DF** com o mapa coropleto de todas as Regiões Administrativas, é preciso subir o banco:

1. **Instale o Docker Desktop** e abra-o uma vez após instalar (reinicie o computador se pedido).

2. **Suba o banco** (na pasta do projeto):
   ```cmd
   docker compose up -d
   ```
   Na primeira execução as tabelas são criadas automaticamente.

3. **Carregue os dados reais** (CSV consolidado + contornos GeoJSON de todas as RAs):
   ```cmd
   venv\Scripts\activate.bat
   python -m db.load_csv
   python -m db.smoke_test
   ```
   > A carga baixa automaticamente os contornos oficiais das RAs do DF e garante que **todas as regiões apareçam no mapa**, mesmo as sem ocorrências (exibidas em cinza).

4. **Reinicie a API** (`python run.py api`) — o painel passará a exibir o mapa coropleto por RA e o filtro de Eixo Indicador.

> [!TIP]
> Sem o banco no ar, tudo continua funcionando no modo fallback (dados simulados). O banco é necessário apenas para os dados reais.

Por padrão, o sistema roda com dados de demonstração. Para usar os **dados reais da SSP-DF** com o mapa coropleto de todas as Regiões Administrativas, é preciso subir o banco:

1. **Instale o Docker Desktop** e abra-o uma vez após instalar (reinicie o computador se pedido).

2. **Suba o banco** (na pasta do projeto):
   ```cmd
   docker compose up -d
   ```
   Na primeira execução as tabelas são criadas automaticamente.

3. **Carregue os dados reais** (CSV consolidado + contornos GeoJSON de todas as RAs):
   ```cmd
   venv\Scripts\activate.bat
   python -m db.load_csv
   python -m db.smoke_test
   ```
   > A carga baixa automaticamente os contornos oficiais das RAs do DF e garante que **todas as regiões apareçam no mapa**, mesmo as sem ocorrências (exibidas em cinza).

4. **Reinicie a API** (`python run.py api`) — o painel passará a exibir o mapa coropleto por RA e o filtro de Eixo Indicador.

> [!TIP]
> Sem o Docker/banco no ar, tudo continua funcionando no modo fallback (dados simulados). O banco é necessário apenas para os dados reais.

---

## 8. Resolução de Problemas Comuns

### Erro: "A execução de scripts foi desabilitada neste sistema" (PowerShell)
Se estiver utilizando o PowerShell e o comando de ativação do venv for bloqueado:
1. Abra o PowerShell como Administrador e execute:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```
2. Digite `S` (Sim) e confirme.
   > Alternativa: use o **CMD** (run.bat e os comandos deste guia funcionam sem essa alteração).

### Erro: "python não é reconhecido como um comando interno ou externo"
O Python não foi marcado com a opção "Add to PATH" durante a instalação.
- Reabra o instalador do Python, selecione **Modify** e marque a caixa **Add Python to PATH**.

### Porta já em uso (8000 ou 8501)
Se outra aplicação no computador já estiver usando essas portas, você pode especificar portas alternativas:
```cmd
python run.py --porta-api 8080 --porta-app 8502
```

### Erro do Docker: "Virtualization support not detected"
A virtualização está desativada ou o WSL2 não está instalado. Caminhos possíveis:
1. Confira no BIOS/UEFI se **Intel VT-x / AMD-V (SVM)** está habilitado (o `systeminfo` mostra "Virtualização Habilitada no Firmware").
2. Instale o WSL2 (pede elevação admin e reinício):
   ```powershell
   wsl --install --no-distribution
   ```
3. Se não puder alterar essas configurações, **use a Opção A (banco na nuvem)** — não exige nada disso.

### Mapa aparece em branco / não carrega
- Confira se sua versão do Streamlit é **1.36 ou superior**: `pip show streamlit`. Versões antigas tentavam usar o estilo Mapbox (que exige token) e ficavam em branco.
- O mapa base (ruas/bairros) é carregado dos servidores da CARTO — verifique sua conexão com a internet.
- Se os **polígonos das RAs** não aparecem (só o fundo do mapa), o banco está sem contornos: rode `docker compose up -d` e depois `python -m db.load_csv`.

### Falha ao instalar `psycopg2-binary` ou `shapely`
- Atualize o pip primeiro: `python -m pip install --upgrade pip`.
- Confirme que está usando Python 64 bits (`python -c "import platform; print(platform.architecture())"`) — wheels para Windows existem para 64 bits.

### `pip install` muito lento ou travando
- Use um mirror próximo: `pip install -r requirements.txt --index-url https://pypi.org/simple --timeout 60`.
