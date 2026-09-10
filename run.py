"""
Inicializador Unificado do Projeto - Mapa da Segurança DF.

Permite rodar:
- Ambos os serviços (API FastAPI + Web Streamlit) simultaneamente
- Apenas a API REST: python run.py api
- Apenas a aplicação Streamlit: python run.py app
"""

import sys
import argparse
import subprocess
import multiprocessing
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def iniciar_api(porta: int = 8000):
    """Inicia a API FastAPI."""
    import uvicorn
    print(f"\n🚀 [API REST] Iniciando em http://localhost:{porta}")
    print(f"📖 [SWAGGER] Documentação interativa em http://localhost:{porta}/docs\n")
    uvicorn.run("api.server:app", host="0.0.0.0", port=porta, reload=True)


def iniciar_app(porta: int = 8501):
    """Inicia o Streamlit."""
    app_path = ROOT_DIR / "app" / "main.py"
    print(f"\n🛡️ [STREAMLIT] Iniciando Web App em http://localhost:{porta}\n")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(porta),
        "--server.headless",
        "true",
    ]
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="Launcher do Mapa da Segurança DF")
    parser.add_argument(
        "modo",
        choices=["todos", "api", "app"],
        default="todos",
        nargs="?",
        help="Serviço para iniciar: 'todos' (padrão), 'api' ou 'app'",
    )
    parser.add_argument("--porta-api", type=int, default=8000, help="Porta para a API FastAPI")
    parser.add_argument("--porta-app", type=int, default=8501, help="Porta para o Streamlit")

    args = parser.parse_args()

    if args.modo == "api":
        iniciar_api(args.porta_api)
    elif args.modo == "app":
        iniciar_app(args.porta_app)
    elif args.modo == "todos":
        print("=" * 65)
        print("🛡️  MAPA DA SEGURANÇA DO DISTRITO FEDERAL - INICIANDO SISTEMA")
        print(f"   ► API REST FastAPI:     http://localhost:{args.porta_api}")
        print(f"   ► Documentação Swagger: http://localhost:{args.porta_api}/docs")
        print(f"   ► Web App Streamlit:    http://localhost:{args.porta_app}")
        print("=" * 65)

        p_api = multiprocessing.Process(target=iniciar_api, args=(args.porta_api,))
        p_app = multiprocessing.Process(target=iniciar_app, args=(args.porta_app,))

        p_api.start()
        p_app.start()

        try:
            p_api.join()
            p_app.join()
        except KeyboardInterrupt:
            print("\nEncerrando serviços...")
            p_api.terminate()
            p_app.terminate()


if __name__ == "__main__":
    main()

