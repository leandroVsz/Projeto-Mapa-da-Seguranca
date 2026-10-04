"""
API FastAPI embutida para deploys em nuvem que executam apenas o app
Streamlit (ex: Streamlit Community Cloud), onde não existe um segundo
serviço rodando na porta 8000.

Com EMBED_API=true no .env (ou nos secrets do deploy), o app sobe a API
como subprocesso `python -m uvicorn api.server:app` e redireciona o
ApiClient para a porta usada. Se a porta padrão já tiver uma API
respondendo (ex: `python run.py api` no mesmo PC), nada é feito.

Subprocesso (e não thread) para não conflitar o event loop do uvicorn
com o do próprio Streamlit.
"""

import atexit
import subprocess
import sys
import time

import streamlit as st

PORTA_PADRAO = 8000
PORTAS_FALLBACK = [8001, 8080]

porta_ativa: int | None = None
_processo = None


def _porta_respondendo(porta: int, caminho: str = "/api/health") -> bool:
    import requests

    try:
        r = requests.get(f"http://localhost:{porta}{caminho}", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def _aguardar_health(porta: int, segundos: float = 15.0) -> bool:
    """Espera o /api/health responder antes do primeiro render do app."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if _porta_respondendo(porta):
            return True
        time.sleep(0.3)
    return False


def _subir_subprocesso(porta: int) -> subprocess.Popen:
    """Sobe `python -m uvicorn api.server:app` na porta indicada."""
    cmd = [
        sys.executable, "-m", "uvicorn", "api.server:app",
        "--host", "0.0.0.0", "--port", str(porta), "--log-level", "warning",
    ]
    return subprocess.Popen(
        cmd, cwd=str(st.session_state.get("_projeto_raiz") or "."),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _encerrar() -> None:
    global _processo
    if _processo is not None and _processo.poll() is None:
        _processo.terminate()
        _processo = None


def iniciar_api_embutida() -> bool:
    """Sobe a API embutida (uma única vez por sessão do Streamlit).

    Retorna True se houver uma API respondendo (a que subiu aqui ou uma
    já existente na porta padrão)."""
    global porta_ativa, _processo

    if st.session_state.get("_api_embutida_iniciada"):
        return porta_ativa is not None or _porta_respondendo(PORTA_PADRAO)

    st.session_state["_api_embutida_iniciada"] = True

    # Já existe API respondendo na porta padrão? Nada a fazer.
    if _porta_respondendo(PORTA_PADRAO):
        porta_ativa = PORTA_PADRAO
        return True

    # Diretório raiz do projeto (para o uvicorn achar o pacote `api`)
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    st.session_state["_projeto_raiz"] = str(raiz)
    atexit.register(_encerrar)

    for porta in (PORTA_PADRAO, *PORTAS_FALLBACK):
        _processo = _subir_subprocesso(porta)
        if _aguardar_health(porta, 15.0):
            porta_ativa = porta
            # Redireciona o ApiClient para a porta que subiu
            import app.api_client as api_client_mod

            api_client_mod.DEFAULT_API_URL = f"http://localhost:{porta}"
            print(f"[api-embutida] API FastAPI embutida online na porta {porta}")
            return True
        # Não subiu (porta ocupada por algo que não responde, etc.)
        print(f"[api-embutida] porta {porta} indisponível; tentando a próxima...")
        _encerrar()

    porta_ativa = None
    print("[api-embutida] nenhuma porta disponível — seguindo em modo fallback")
    return False
