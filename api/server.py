"""
Servidor FastAPI principal para o backend do Mapa da Segurança DF.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys

# Garante inclusão do diretório raiz no sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from api.routes.regioes import router as regioes_router
from api.routes.ocorrencias import router as ocorrencias_router
from api.services.data_service import DataService

app = FastAPI(
    title="API - Mapa da Segurança do Distrito Federal",
    description="""
    Serviço backend de dados de criminalidade e mapas de calor geoespaciais para o DF.
    
    Projeto acadêmico UCB (8º Semestre) - Soluções Computacionais.
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra rotas
app.include_router(regioes_router)
app.include_router(ocorrencias_router)

data_service = DataService()


@app.get("/", tags=["Status"])
def root():
    return {
        "sistema": "Mapa da Segurança do Distrito Federal",
        "modulo": "Backend API REST",
        "versao": "2.0.0",
        "documentacao_swagger": "/docs",
        "status": "online",
    }


@app.get("/api/health", tags=["Status"])
def health():
    df = data_service.carregar_dados()
    return {
        "status": "healthy",
        "total_registros_ativos": len(df),
        "total_regioes_mapeadas": len(data_service.get_regioes()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)

