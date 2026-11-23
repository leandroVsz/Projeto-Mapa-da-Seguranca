"""
Cache em memória com TTL para respostas de leitura.

O dashboard faz as mesmas consultas em praticamente todo rerun do Streamlit
(filtros e contornos das RAs são praticamente estáticos). Guardar a resposta
por alguns minutos elimina idas repetidas ao banco sem alterar contratos.

TTL configurável por `API_CACHE_TTL_SEGUNDOS` (padrão: 300s; 0 desliga).
"""

import os
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

_CACHE: Dict[str, Tuple[float, Any]] = {}
_LOCK = threading.Lock()


def _ttl_padrao() -> float:
    try:
        return max(0.0, float(os.getenv("API_CACHE_TTL_SEGUNDOS", "300")))
    except ValueError:
        return 300.0


def get_or_set(chave: str, produtor: Callable[[], Any],
               ttl: Optional[float] = None) -> Any:
    """Devolve o valor em cache (se ainda válido) ou executa `produtor`."""
    validade = _ttl_padrao() if ttl is None else ttl
    if validade <= 0:
        return produtor()

    agora = time.monotonic()
    with _LOCK:
        item = _CACHE.get(chave)
        if item is not None and item[0] > agora:
            return item[1]

    valor = produtor()
    with _LOCK:
        _CACHE[chave] = (agora + validade, valor)
    return valor


def invalidar(chave: Optional[str] = None) -> None:
    """Invalida uma entrada (ou todo o cache) — usado após carga/ETL."""
    with _LOCK:
        if chave is None:
            _CACHE.clear()
        else:
            _CACHE.pop(chave, None)
