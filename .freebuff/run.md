# Run doc — Mapa da Segurança DF

## Como reproduzir os artefatos (checkout novo)

1. Ambiente Python:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Banco PostgreSQL + PostGIS via Docker:
   ```bash
   docker compose up -d
   ```
   > ⚠ Nesta máquina o Docker é o **Snap** e o projeto está em `/media/...`:
   > é preciso `snap connect docker:removable-media` (já conectado) e o
   > socket só aceita root nesta instalação — rode `docker compose` via
   > elevação (sudo) ou cadastre o usuário no grupo do docker.
3. Carga dos dados reais (idempotente — baixa os contornos das RAs em
   `data/geo/ra_df.geojson` na primeira vez):
   ```bash
   python -m db.load_csv
   python -m db.smoke_test
   ```
4. Não há arquivo `.env` obrigatório; a conexão padrão é
   `postgresql+psycopg2://crimemap:crimemap@localhost:5432/crimemap`
   (ver `.env.example`).

## Como rodar os servidores

Dois processos, em terminais separados (a partir da raiz do projeto):

```bash
# Terminal 1 — API FastAPI (porta 8000)
source venv/bin/activate
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000

# Terminal 2 — Streamlit (porta 8501)
source venv/bin/activate
python -m streamlit run app/main.py --server.port 8501 --server.headless true
```

Ou ambos de uma vez: `python run.py`.

- **Preview (Streamlit)**: http://localhost:8501
- **Swagger (API)**: http://localhost:8000/docs
