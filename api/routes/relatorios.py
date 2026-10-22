"""
Rotas REST de relatórios salvos (HU08 / Tela "Meus relatórios").

Todas as rotas exigem usuário autenticado (header X-Auth-Token), via a
mesma dependência usuario_atual usada em api/routes/auth.py. Um usuário
nunca enxerga nem apaga relatório de outro: tudo é filtrado pelo id do
usuário da sessão, nunca por um id vindo do cliente.
"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.routes.auth import usuario_atual
from api.services.relatorio_service import (
    RelatorioService, RelatorioError, TOP_N_MIN, TOP_N_MAX, TITULO_MAX,
)

router = APIRouter(prefix="/api/relatorios", tags=["Relatórios salvos"])


# ---------------------------------------------------------------------------
# Modelos de requisição/resposta
# ---------------------------------------------------------------------------
class RelatorioIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=TITULO_MAX)
    dimensao: Literal["por_regiao", "por_natureza", "por_mes", "por_ano"]
    tipo_grafico: Literal[
        "Barras", "Barras horizontais", "Linha", "Área", "Pizza", "Rosca"
    ]
    top_n: int = Field(default=10, ge=TOP_N_MIN, le=TOP_N_MAX)
    filtros: Dict[str, Any] = Field(default_factory=dict)


class RelatorioOut(BaseModel):
    id: int
    titulo: str
    dimensao: str
    tipo_grafico: str
    top_n: int
    filtros: Dict[str, Any]
    criado_em: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _erro_http(err: RelatorioError) -> HTTPException:
    status = {
        "titulo_duplicado": 409,
        "validacao": 422,
        "nao_encontrado": 404,
    }.get(err.codigo, 400)
    return HTTPException(status_code=status, detail=err.mensagem)


# ---------------------------------------------------------------------------
# Endpoints (todos autenticados)
# ---------------------------------------------------------------------------
@router.post("", summary="Salvar um relatório (gráfico) na conta do usuário",
             response_model=RelatorioOut)
def salvar(dados: RelatorioIn, user: dict = Depends(usuario_atual)):
    try:
        return RelatorioService.salvar(
            usuario_id=user["id"],
            titulo=dados.titulo,
            dimensao=dados.dimensao,
            tipo_grafico=dados.tipo_grafico,
            top_n=dados.top_n,
            filtros=dados.filtros,
        )
    except RelatorioError as e:
        raise _erro_http(e)


@router.get("", summary="Listar os relatórios salvos do usuário logado",
            response_model=List[RelatorioOut])
def listar(user: dict = Depends(usuario_atual)):
    return RelatorioService.listar(usuario_id=user["id"])


@router.delete("/{relatorio_id}", summary="Excluir um relatório salvo (só o próprio)")
def excluir(relatorio_id: int, user: dict = Depends(usuario_atual)):
    try:
        RelatorioService.excluir(usuario_id=user["id"], relatorio_id=relatorio_id)
    except RelatorioError as e:
        raise _erro_http(e)
    return {"ok": True}
