"""
Serviço de relatórios salvos do Mapa da Segurança DF (HU08).

Responsável pelo CRUD de `auth.relatorio_salvo`: salvar a configuração
de um gráfico (dimensão, tipo, Top N e filtros) na conta do usuário
logado, listar os relatórios salvos e excluir um relatório.

A tabela guarda apenas a CONFIGURAÇÃO do gráfico, nunca a imagem: ao
reabrir, o gráfico é regenerado com os dados atuais (reaproveitando
montar_dataframe/criar_figura de app/components/charts.py).

Um usuário nunca acessa ou exclui relatório de outro: toda consulta é
filtrada por usuario_id, e os métodos exigem o id do usuário logado
(injetado pela dependência usuario_atual das rotas).

Segue o mesmo padrão de api/services/auth_service.py: SQLAlchemy via
texto (text()), SessionLocal por operação, exceções de domínio em
RelatorioError (mensagem segura para o usuário + código para a rota
decidir o status HTTP).
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.db.session import SessionLocal

# ---------------------------------------------------------------------------
# Valores aceitos (espelham o CHECK de db/auth_schema.sql e as constantes
# de app/components/charts.py — DIMENSOES e TIPOS_GRAFICO)
# ---------------------------------------------------------------------------
DIMENSOES_VALIDAS = ("por_regiao", "por_natureza", "por_mes", "por_ano")
TIPOS_GRAFICO_VALIDOS = (
    "Barras", "Barras horizontais", "Linha", "Área", "Pizza", "Rosca",
)
TOP_N_MIN = 3
TOP_N_MAX = 30
TITULO_MAX = 120


class RelatorioError(Exception):
    """Erro de regra de negócio de relatórios (mensagem segura p/ usuário)."""

    def __init__(self, mensagem: str, codigo: str = "erro"):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo  # titulo_duplicado | validacao | nao_encontrado | erro


def _to_dict(row) -> Dict[str, Any]:
    """Serializa uma linha de auth.relatorio_salvo."""
    filtros = row.filtros
    if isinstance(filtros, str):
        filtros = json.loads(filtros)
    return {
        "id": int(row.id),
        "titulo": row.titulo,
        "dimensao": row.dimensao,
        "tipo_grafico": row.tipo_grafico,
        "top_n": int(row.top_n),
        "filtros": filtros or {},
        "criado_em": row.criado_em.isoformat() if isinstance(row.criado_em, datetime) else row.criado_em,
    }


class RelatorioService:
    """Operações sobre auth.relatorio_salvo, sempre escopadas ao usuário."""

    # ------------------------------------------------------------------
    # Validação (mesmas regras do CHECK no banco, verificadas antes para
    # devolver uma mensagem clara em vez de um erro genérico de SQL)
    # ------------------------------------------------------------------
    @staticmethod
    def _validar(titulo: str, dimensao: str, tipo_grafico: str, top_n: int) -> str:
        titulo = (titulo or "").strip()
        if not (1 <= len(titulo) <= TITULO_MAX):
            raise RelatorioError(
                f"O título precisa ter entre 1 e {TITULO_MAX} caracteres.", "validacao"
            )
        if dimensao not in DIMENSOES_VALIDAS:
            raise RelatorioError("Dimensão inválida.", "validacao")
        if tipo_grafico not in TIPOS_GRAFICO_VALIDOS:
            raise RelatorioError("Tipo de gráfico inválido.", "validacao")
        if not (TOP_N_MIN <= top_n <= TOP_N_MAX):
            raise RelatorioError(
                f"Top N precisa estar entre {TOP_N_MIN} e {TOP_N_MAX}.", "validacao"
            )
        return titulo

    # ------------------------------------------------------------------
    # Salvar
    # ------------------------------------------------------------------
    @staticmethod
    def salvar(
        usuario_id: int,
        titulo: str,
        dimensao: str,
        tipo_grafico: str,
        top_n: int = 10,
        filtros: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        titulo = RelatorioService._validar(titulo, dimensao, tipo_grafico, top_n)
        filtros_json = json.dumps(filtros or {}, ensure_ascii=False)

        try:
            with SessionLocal() as s:
                row = s.execute(text("""
                    INSERT INTO auth.relatorio_salvo
                        (usuario_id, titulo, dimensao, tipo_grafico, top_n, filtros)
                    VALUES
                        (:usuario_id, :titulo, :dimensao, :tipo_grafico, :top_n, CAST(:filtros AS JSONB))
                    RETURNING id, titulo, dimensao, tipo_grafico, top_n, filtros, criado_em
                """), {
                    "usuario_id": usuario_id,
                    "titulo": titulo,
                    "dimensao": dimensao,
                    "tipo_grafico": tipo_grafico,
                    "top_n": int(top_n),
                    "filtros": filtros_json,
                }).first()
                s.commit()
        except IntegrityError as e:
            # uq_relatorio_usuario_titulo: mesmo usuário + mesmo título
            if "uq_relatorio_usuario_titulo" in str(e.orig):
                raise RelatorioError(
                    "Você já tem um relatório salvo com esse título.", "titulo_duplicado"
                )
            raise RelatorioError("Não foi possível salvar o relatório.", "erro")

        return _to_dict(row)

    # ------------------------------------------------------------------
    # Listar (só do próprio usuário)
    # ------------------------------------------------------------------
    @staticmethod
    def listar(usuario_id: int) -> List[Dict[str, Any]]:
        with SessionLocal() as s:
            rows = s.execute(text("""
                SELECT id, titulo, dimensao, tipo_grafico, top_n, filtros, criado_em
                FROM auth.relatorio_salvo
                WHERE usuario_id = :usuario_id
                ORDER BY criado_em DESC
            """), {"usuario_id": usuario_id}).fetchall()
        return [_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Excluir (só o próprio; nunca de outro usuário)
    # ------------------------------------------------------------------
    @staticmethod
    def excluir(usuario_id: int, relatorio_id: int) -> None:
        with SessionLocal() as s:
            res = s.execute(text("""
                DELETE FROM auth.relatorio_salvo
                WHERE id = :id AND usuario_id = :usuario_id
            """), {"id": relatorio_id, "usuario_id": usuario_id})
            s.commit()
        if not res.rowcount:
            # Mesma mensagem tanto se o relatório não existe quanto se é
            # de outro usuário: nunca revelamos que o id pertence a outra conta.
            raise RelatorioError("Relatório não encontrado.", "nao_encontrado")
