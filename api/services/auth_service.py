"""
Serviço de autenticação do Mapa da Segurança DF.

Responsável por todo o ciclo de vida de usuários e sessões no schema
`auth` do mesmo banco PostgreSQL do projeto:

  - Registro com validação de e-mail e política de senha forte
  - Hash de senha com bcrypt (cost 12) — senha nunca é armazenada/registrada
  - Bloqueio temporário anti-força-bruta (5 falhas => 15 min)
  - Sessões "remember me" com token opaco (guardamos apenas o SHA-256)
  - Reset de senha por token de uso único com expiração
  - Trilha de auditoria em auth.log_acesso

Todas as consultas usam a mesma engine/SessionLocal de api.db.session
(um único servidor de banco), porém isoladas no schema `auth`.
"""

import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.db.session import SessionLocal

# ---------------------------------------------------------------------------
# Parâmetros de segurança (ajustáveis)
# ---------------------------------------------------------------------------
BCRYPT_ROUNDS = 12                 # custo do hash (~250ms em hardware comum)
SESSAO_HORAS = 12                  # duração padrão da sessão
SESSAO_REMEMBER_DIAS = 30          # duração com "manter conectado"
MAX_FALHAS_LOGIN = 5               # tentativas antes do bloqueio
BLOQUEIO_MINUTOS = 15              # janela do bloqueio anti-força-bruta
RESET_EXPIRA_MINUTOS = 30          # validade do token de reset de senha
MAX_SESSOES_POR_USUARIO = 20       # podas sessões antigas ao criar nova

_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class AuthError(Exception):
    """Erro de regra de negócio de autenticação (mensagem segura p/ usuário)."""

    def __init__(self, mensagem: str, codigo: str = "erro"):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo  # email_em_uso | senha_fraca | credenciais |
        #                         bloqueado | inativo | token_invalido |
        #                         email_invalido | nao_encontrado | erro


# ---------------------------------------------------------------------------
# Helpers de hashing e validação
# ---------------------------------------------------------------------------
def _hash_senha(senha: str) -> str:
    """Gera hash bcrypt (sal aleatório embutido)."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def _verificar_senha(senha: str, senha_hash: str) -> bool:
    """Verificação em tempo constante contra o hash armazenado."""
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    """SHA-256 hex de tokens opacos (sessão e reset)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validar_forca_senha(senha: str) -> List[str]:
    """Retorna lista de problemas da senha (vazia = senha aceitável)."""
    problemas: List[str] = []
    if not senha or len(senha) < 8:
        problemas.append("ter no mínimo 8 caracteres")
    if len(senha.encode("utf-8")) > 72:
        problemas.append("ter no máximo 72 bytes (limite do bcrypt)")
    if not re.search(r"[A-Z]", senha):
        problemas.append("conter ao menos uma letra maiúscula")
    if not re.search(r"[a-z]", senha):
        problemas.append("conter ao menos uma letra minúscula")
    if not re.search(r"\d", senha):
        problemas.append("conter ao menos um número")
    return problemas


def _normalizar_email(email: str) -> str:
    email = unicodedata.normalize("NFKC", (email or "").strip().lower())
    if not email or not _RE_EMAIL.match(email) or len(email) > 255:
        raise AuthError("Informe um e-mail válido.", "email_invalido")
    return email


def _to_dict(row) -> Dict[str, Any]:
    """Serializa linha de auth.usuario sem expor o hash da senha."""
    return {
        "id": int(row.id),
        "email": row.email,
        "nome": row.nome,
        "papel": row.papel,
        "ativo": bool(row.ativo),
        "criado_em": row.criado_em.isoformat() if row.criado_em else None,
        "ultimo_login_em": row.ultimo_login_em.isoformat() if row.ultimo_login_em else None,
        "bloqueado_ate": row.bloqueado_ate.isoformat() if row.bloqueado_ate else None,
    }


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
def _log_acesso(
    email: Optional[str],
    acao: str,
    sucesso: bool = True,
    ip_origem: Optional[str] = None,
    detalhe: Optional[str] = None,
) -> None:
    """Grava evento de auditoria; falha de log nunca deve derrubar o fluxo."""
    try:
        with SessionLocal() as s:
            s.execute(text("""
                INSERT INTO auth.log_acesso (email, acao, sucesso, ip_origem, detalhe)
                VALUES (:email, :acao, :sucesso, :ip, :detalhe)
            """), {
                "email": (email or "")[:255] or None,
                "acao": acao,
                "sucesso": sucesso,
                "ip": (ip_origem or "")[:64] or None,
                "detalhe": (detalhe or "")[:300] or None,
            })
            s.commit()
    except SQLAlchemyError:
        pass  # auditoria é best-effort


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------
class AuthService:
    """Operações de usuário/sessão no schema auth do PostgreSQL."""

    # ------------------------------------------------------------------
    # Infra
    # ------------------------------------------------------------------
    @staticmethod
    def criar_schema() -> Dict[str, Any]:
        """Aplica o DDL do schema auth de forma idempotente (sem psql/Docker)."""
        from pathlib import Path

        ddl = (Path(__file__).resolve().parent.parent.parent / "db" / "auth_schema.sql").read_text(
            encoding="utf-8"
        )
        with SessionLocal() as s:
            s.execute(text(ddl))
            s.commit()
        return {"schema": "auth", "status": "criado/verificado"}

    @staticmethod
    def health() -> Dict[str, Any]:
        """Status do schema auth + total de usuários."""
        try:
            with SessionLocal() as s:
                total = s.execute(text("SELECT COUNT(*) FROM auth.usuario")).scalar() or 0
                ativos = s.execute(
                    text("SELECT COUNT(*) FROM auth.usuario WHERE ativo")
                ).scalar() or 0
            return {"auth_online": True, "usuarios": int(total), "usuarios_ativos": int(ativos)}
        except SQLAlchemyError:
            return {"auth_online": False}

    # ------------------------------------------------------------------
    # Registro / consulta de usuários
    # ------------------------------------------------------------------
    @staticmethod
    def registrar(nome: str, email: str, senha: str,
                  papel: str = "usuario", ip_origem: Optional[str] = None) -> Dict[str, Any]:
        """Cria um novo usuário (papel 'admin' apenas via CLI/admin)."""
        nome = (nome or "").strip()
        if len(nome) < 3 or len(nome) > 120:
            raise AuthError("Informe seu nome completo (3 a 120 caracteres).")
        if papel not in ("admin", "usuario"):
            raise AuthError("Papel inválido.")

        email = _normalizar_email(email)

        problemas = validar_forca_senha(senha)
        if problemas:
            raise AuthError("A senha precisa " + "; ".join(problemas) + ".", "senha_fraca")

        senha_hash = _hash_senha(senha)
        try:
            with SessionLocal() as s:
                row = s.execute(text("""
                    INSERT INTO auth.usuario (email, nome, senha_hash, papel)
                    VALUES (:email, :nome, :senha_hash, :papel)
                    RETURNING id, email, nome, senha_hash, papel, ativo,
                              criado_em, ultimo_login_em, bloqueado_ate
                """), {
                    "email": email, "nome": nome,
                    "senha_hash": senha_hash, "papel": papel,
                }).first()
                s.commit()
        except SQLAlchemyError as e:
            msg = str(e).lower()
            if "uq_usuario_email" in msg or "duplicate key" in msg:
                raise AuthError("Este e-mail já está cadastrado.", "email_em_uso") from e
            raise AuthError("Banco indisponível no momento. Tente novamente.", "erro") from e

        _log_acesso(email, "REGISTRO", True, ip_origem, f"papel={papel}")
        return _to_dict(row)

    @staticmethod
    def obter_por_id(usuario_id: int) -> Optional[Dict[str, Any]]:
        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT id, email, nome, senha_hash, papel, ativo,
                       criado_em, ultimo_login_em, bloqueado_ate
                FROM auth.usuario WHERE id = :id
            """), {"id": usuario_id}).first()
        return _to_dict(row) if row else None

    @staticmethod
    def listar_usuarios(apenas_ativos: bool = False) -> List[Dict[str, Any]]:
        with SessionLocal() as s:
            sql = """
                SELECT id, email, nome, senha_hash, papel, ativo,
                       criado_em, ultimo_login_em, bloqueado_ate
                FROM auth.usuario
            """
            if apenas_ativos:
                sql += " WHERE ativo"
            sql += " ORDER BY criado_em"
            rows = s.execute(text(sql)).all()
        return [_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Login / logout
    # ------------------------------------------------------------------
    @staticmethod
    def autenticar(email: str, senha: str, ip_origem: Optional[str] = None,
                   user_agent: Optional[str] = None) -> Dict[str, Any]:
        """Valida credenciais. Em caso de falha, lança AuthError (mensagem
        genérica 'credenciais' para não revelar quais e-mails existem)."""
        try:
            email_norm = _normalizar_email(email)
        except AuthError:
            raise AuthError("E-mail ou senha incorretos.", "credenciais")

        agora = datetime.now(timezone.utc)

        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT id, email, nome, senha_hash, papel, ativo,
                       criado_em, ultimo_login_em, bloqueado_ate, falhas_login
                FROM auth.usuario WHERE email = :email
            """), {"email": email_norm}).first()

            if row is None:
                # custo aproximado ao de um hash real (evita timing oracle)
                bcrypt.checkpw(b"senha-fantasma", bcrypt.gensalt(rounds=4))
                _log_acesso(email_norm, "LOGIN_FALHA", False, ip_origem, "e-mail inexistente")
                raise AuthError("E-mail ou senha incorretos.", "credenciais")

            if row.bloqueado_ate:
                bloqueado_ate = row.bloqueado_ate
                if bloqueado_ate.tzinfo is None:
                    bloqueado_ate = bloqueado_ate.replace(tzinfo=timezone.utc)
                if bloqueado_ate > agora:
                    minutos = max(1, int((bloqueado_ate - agora).total_seconds() // 60) + 1)
                    _log_acesso(email_norm, "BLOQUEIO", False, ip_origem,
                                "tentativa durante lockout")
                    raise AuthError(
                        f"Conta temporariamente bloqueada por tentativas inválidas. "
                        f"Tente novamente em ~{minutos} min.",
                        "bloqueado",
                    )

            if not row.ativo:
                _log_acesso(email_norm, "LOGIN_FALHA", False, ip_origem, "conta inativa")
                raise AuthError("Esta conta está desativada. Procure um administrador.",
                                "inativo")

            if not _verificar_senha(senha or "", row.senha_hash):
                falhas = int(row.falhas_login or 0) + 1
                if falhas >= MAX_FALHAS_LOGIN:
                    s.execute(text("""
                        UPDATE auth.usuario
                        SET falhas_login = 0, bloqueado_ate = NOW() + (:min || ' minutes')::interval
                        WHERE id = :id
                    """), {"min": str(BLOQUEIO_MINUTOS), "id": row.id})
                    _log_acesso(email_norm, "BLOQUEIO", False, ip_origem,
                                f"{falhas} falhas => lockout {BLOQUEIO_MINUTOS}min")
                else:
                    s.execute(text("""
                        UPDATE auth.usuario SET falhas_login = :f WHERE id = :id
                    """), {"f": falhas, "id": row.id})
                s.commit()
                _log_acesso(email_norm, "LOGIN_FALHA", False, ip_origem,
                            f"senha incorreta ({falhas}/{MAX_FALHAS_LOGIN})")
                raise AuthError("E-mail ou senha incorretos.", "credenciais")

            # Sucesso: zera contador, registra último login, poda sessões antigas
            s.execute(text("""
                UPDATE auth.usuario SET falhas_login = 0, bloqueado_ate = NULL,
                       ultimo_login_em = NOW()
                WHERE id = :id
            """), {"id": row.id})
            s.execute(text("""
                DELETE FROM auth.sessao_usuario
                WHERE usuario_id = :id AND id NOT IN (
                    SELECT id FROM auth.sessao_usuario
                    WHERE usuario_id = :id AND revogada = FALSE AND expira_em > NOW()
                    ORDER BY expira_em DESC LIMIT :max_sessoes
                )
            """), {"id": row.id, "max_sessoes": MAX_SESSOES_POR_USUARIO})
            s.commit()

        _log_acesso(email_norm, "LOGIN_OK", True, ip_origem)
        return _to_dict(row)

    # ------------------------------------------------------------------
    # Sessões ("remember me") — token opaco, guardamos apenas SHA-256
    # ------------------------------------------------------------------
    @staticmethod
    def criar_sessao(usuario_id: int, lembrar: bool = False,
                     ip_origem: Optional[str] = None,
                     user_agent: Optional[str] = None) -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        duracao = timedelta(days=SESSAO_REMEMBER_DIAS if lembrar else 0,
                            hours=SESSAO_HORAS if not lembrar else 0)
        with SessionLocal() as s:
            s.execute(text("""
                INSERT INTO auth.sessao_usuario
                    (usuario_id, token_hash, expira_em, ip_origem, user_agent)
                VALUES (:uid, :thash, NOW() + (:secs || ' seconds')::interval, :ip, :ua)
            """), {
                "uid": usuario_id,
                "thash": _hash_token(token),
                "secs": str(int(duracao.total_seconds())),
                "ip": (ip_origem or "")[:64] or None,
                "ua": (user_agent or "")[:300] or None,
            })
            s.commit()
        return {"token": token,
                "expira_em": (datetime.now(timezone.utc) + duracao).isoformat()}

    @staticmethod
    def validar_sessao(token: str) -> Optional[Dict[str, Any]]:
        """Retorna o usuário da sessão válida ou None (token expirado/revogado)."""
        if not token:
            return None
        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT u.id, u.email, u.nome, u.papel, u.ativo,
                       u.criado_em, u.ultimo_login_em, u.bloqueado_ate
                FROM auth.sessao_usuario se
                JOIN auth.usuario u ON u.id = se.usuario_id
                WHERE se.token_hash = :thash
                  AND se.revogada = FALSE
                  AND se.expira_em > NOW()
            """), {"thash": _hash_token(token)}).first()
        if row is None or not row.ativo:
            return None
        return _to_dict(row)

    @staticmethod
    def revogar_sessao(token: str) -> None:
        if not token:
            return
        with SessionLocal() as s:
            s.execute(text("""
                UPDATE auth.sessao_usuario SET revogada = TRUE
                WHERE token_hash = :thash
            """), {"thash": _hash_token(token)})
            s.commit()

    @staticmethod
    def revogar_todas_sessoes(usuario_id: int) -> int:
        """Revoga todas as sessões ativas do usuário (ex.: após trocar senha)."""
        with SessionLocal() as s:
            res = s.execute(text("""
                UPDATE auth.sessao_usuario SET revogada = TRUE
                WHERE usuario_id = :uid AND revogada = FALSE
            """), {"uid": usuario_id})
            s.commit()
        return int(res.rowcount or 0)

    # ------------------------------------------------------------------
    # Troca e reset de senha
    # ------------------------------------------------------------------
    @staticmethod
    def trocar_senha(usuario_id: int, senha_atual: str, nova_senha: str) -> Dict[str, Any]:
        problemas = validar_forca_senha(nova_senha)
        if problemas:
            raise AuthError("A nova senha precisa " + "; ".join(problemas) + ".", "senha_fraca")

        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT id, email, senha_hash FROM auth.usuario WHERE id = :id
            """), {"id": usuario_id}).first()
            if row is None:
                raise AuthError("Usuário não encontrado.", "nao_encontrado")
            if not _verificar_senha(senha_atual or "", row.senha_hash):
                _log_acesso(row.email, "LOGIN_FALHA", False, None, "senha atual errada (troca)")
                raise AuthError("A senha atual está incorreta.", "credenciais")

            s.execute(text("""
                UPDATE auth.usuario
                SET senha_hash = :hash, atualizado_em = NOW(),
                    falhas_login = 0, bloqueado_ate = NULL,
                    token_reset = NULL, token_reset_exp = NULL
                WHERE id = :id
            """), {"hash": _hash_senha(nova_senha), "id": usuario_id})
            s.commit()

        # Boa prática: invalida todas as sessões existentes após trocar a senha
        AuthService.revogar_todas_sessoes(usuario_id)
        _log_acesso(row.email, "RESET_SENHA", True, None, "troca de senha autenticada")
        return {"ok": True, "sessoes_revogadas": True}

    @staticmethod
    def solicitar_reset(email: str) -> Optional[str]:
        """Gera token de reset de uso único (30 min). Retorna o token em claro
        apenas se o e-mail existir; em sistema real ele seria enviado por
        e-mail — aqui fica disponível para o administrador/devolver na CLI.
        Sempre responde 'silenciosamente' para não vazar existência de conta."""
        try:
            email = _normalizar_email(email)
        except AuthError:
            return None

        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT id, email FROM auth.usuario WHERE email = :email AND ativo
            """), {"email": email}).first()
            if row is None:
                return None

            token = secrets.token_urlsafe(32)
            s.execute(text("""
                UPDATE auth.usuario
                SET token_reset = :thash,
                    token_reset_exp = NOW() + (:min || ' minutes')::interval
                WHERE id = :id
            """), {"thash": _hash_token(token), "min": str(RESET_EXPIRA_MINUTOS), "id": row.id})
            s.commit()

        _log_acesso(email, "RESET_SENHA", True, None, "token gerado")
        return token

    @staticmethod
    def redefinir_senha(token: str, nova_senha: str) -> Dict[str, Any]:
        problemas = validar_forca_senha(nova_senha)
        if problemas:
            raise AuthError("A nova senha precisa " + "; ".join(problemas) + ".", "senha_fraca")

        thash = _hash_token(token or "")
        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT id, email FROM auth.usuario
                WHERE token_reset = :thash AND token_reset_exp > NOW() AND ativo
            """), {"thash": thash}).first()
            if row is None:
                raise AuthError("Link de redefinição inválido ou expirado.", "token_invalido")

            s.execute(text("""
                UPDATE auth.usuario
                SET senha_hash = :hash, atualizado_em = NOW(),
                    falhas_login = 0, bloqueado_ate = NULL,
                    token_reset = NULL, token_reset_exp = NULL
                WHERE id = :id
            """), {"hash": _hash_senha(nova_senha), "id": row.id})
            s.commit()

        AuthService.revogar_todas_sessoes(row.id)
        _log_acesso(row.email, "RESET_SENHA", True, None, "senha redefinida via token")
        return {"ok": True}

    # ------------------------------------------------------------------
    # Administração
    # ------------------------------------------------------------------
    @staticmethod
    def alterar_status(usuario_id: int, ativo: bool) -> Dict[str, Any]:
        with SessionLocal() as s:
            row = s.execute(text("""
                SELECT email FROM auth.usuario WHERE id = :id
            """), {"id": usuario_id}).first()
            if row is None:
                raise AuthError("Usuário não encontrado.", "nao_encontrado")
            s.execute(text("""
                UPDATE auth.usuario SET ativo = :ativo, atualizado_em = NOW()
                WHERE id = :id
            """), {"ativo": ativo, "id": usuario_id})
            s.commit()
        if not ativo:
            AuthService.revogar_todas_sessoes(usuario_id)
        return {"id": usuario_id, "ativo": ativo}

    @staticmethod
    def promover_admin(usuario_id: int, admin: bool = True) -> Dict[str, Any]:
        with SessionLocal() as s:
            s.execute(text("""
                UPDATE auth.usuario SET papel = :papel, atualizado_em = NOW()
                WHERE id = :id
            """), {"papel": "admin" if admin else "usuario", "id": usuario_id})
            s.commit()
        return {"id": usuario_id, "papel": "admin" if admin else "usuario"}

    @staticmethod
    def contar_admins_ativos() -> int:
        with SessionLocal() as s:
            return int(s.execute(text(
                "SELECT COUNT(*) FROM auth.usuario WHERE papel = 'admin' AND ativo"
            )).scalar() or 0)

    # ------------------------------------------------------------------
    # Manutenção
    # ------------------------------------------------------------------
    @staticmethod
    def limpar_dados_expirados() -> Dict[str, Any]:
        """Remove sessões expiradas há mais de 7 dias e logs com mais de
        180 dias. Pode ser chamado por cron/job de manutenção."""
        with SessionLocal() as s:
            r1 = s.execute(text("""
                DELETE FROM auth.sessao_usuario
                WHERE expira_em < NOW() - INTERVAL '7 days'
            """))
            r2 = s.execute(text("""
                DELETE FROM auth.log_acesso
                WHERE criado_em < NOW() - INTERVAL '180 days'
            """))
            s.commit()
        return {"sessoes_removidas": int(r1.rowcount or 0),
                "logs_removidos": int(r2.rowcount or 0)}
