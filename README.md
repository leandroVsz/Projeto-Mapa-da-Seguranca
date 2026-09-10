# 🛡️ Mapa da Segurança - Distrito Federal (DF)

Sistema web geoespacial para análise e visualização da violência e criminalidade no Distrito Federal através de **mapas de calor interativos**, indicadores estatísticos e central de consolidação de dados da Secretaria de Segurança Pública (SSP-DF).

Projeto desenvolvido para a disciplina de **Soluções Computacionais (8º Semestre) - Universidade Católica de Brasília (UCB)**.

---

## 🏛️ Arquitetura do Sistema (100% Python)

O sistema foi desenhado com foco em **separação de responsabilidades**, facilidade de execução e valorização acadêmica:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   FRONTEND WEB (Streamlit Dashboard)                   │
│  - Mapa de Calor Geoespacial 2D (PyDeck Heatmap) e 3D (Hexágonos)      │
│  - Filtros: Regiões Administrativas (RAs), Crimes, Períodos e Anos     │
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
│  - Cálculo de intensidades e matriz geoespacial de calor               │
│  - Agregações estatísticas e consultas filtradas                       │
│  - Pipeline ETL para consolidar anos e cidades da SSP-DF               │
│  - Fallback local transparente caso a API esteja desligada             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Leitura / Gravação
┌───────────────────────────────────▼────────────────────────────────────┐
│                     CAMADA DE DADOS UNIFICADA (data/)                  │
│  - Base de ocorrências simuladas (padrão SSP-DF)                       │
│  - Metadados geográficos das 14 principais RAs do DF                   │
│  - Diretório raw/ para novos CSVs anuais baixados                      │
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
| `GET` | `/api/health` | Status de integridade do servidor e total de registros |
| `GET` | `/api/regioes` | Lista de RAs e coordenadas centrais de cada região |
| `GET` | `/api/filtros` | Opções disponíveis de filtros (RAs, crimes, anos, períodos) |
| `GET` | `/api/heatmap` | Matriz de coordenadas e intensidade `[lat, lon, peso]` |
| `GET` | `/api/ocorrencias` | Listagem detalhada de ocorrências com busca textual |
| `GET` | `/api/stats` | Indicadores-chave (KPIs) e resumos estatísticos |
| `POST`| `/api/consolidar` | Executa a unificação de arquivos brutos anuais (ETL) |

Documentação interativa Swagger disponível em: **[http://localhost:8000/docs](http://localhost:8000/docs)**.
