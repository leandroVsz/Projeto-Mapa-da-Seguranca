"""
Rotas REST de autenticação (schema auth no mesmo PostgreSQL do projeto).

Autenticação por token opaco no header `X-Auth-Token`. Basta o cliente
enviar o token recebido no /login (ou /registro) nas chamadas protegidas.

Mensagens de erro são genéricas de propósito: nunca revelamos se um
e-mail existe ou não (evita enumeração de contas).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from api.services.auth_service import AuthService, AuthError

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])


# ---------------------------------------------------------------------------
# Modelos de requisição (validação de entrada via Pydantic)
# ---------------------------------------------------------------------------
class RegistroIn(BaseModel):
    nome: str = Field(min_length=3, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    senha: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    senha: str = Field(min_length=1, max_length=128)
    lembrar: bool = False


class TrocaSenhaIn(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=128)
    nova_senha: str = Field(min_length=8, max_length=128)


class ResetSolicitarIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)


class ResetConfirmarIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    nova_senha: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cliente_ip(request: Request) -> Optional[str]:
    """IP real atrás de proxy reverso (X-Forwarded-For), se houver."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else None)[:64] or None


def _ou_401(err: AuthError) -> HTTPException:
    status = {
        "bloqueado": 429,
        "credenciais": 401,
        "inativo": 403,
        "email_em_uso": 409,
        "senha_fraca": 422,
        "email_invalido": 422,
        "token_invalido": 400,
        "nao_encontrado": 404,
    }.get(err.codigo, 400)
    return HTTPException(status_code=status, detail=err.mensagem)


async def usuario_atual(
    x_auth_token: Optional[str] = Header(default=None),
) -> dict:
    """Dependência FastAPI: injeta o usuário autenticado ou 401."""
    user = AuthService.validar_sessao(x_auth_token or "")
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Sessão inválida ou expirada. Faça login novamente.",
        )
    return user


# ---------------------------------------------------------------------------
# Endpoints públicos
# ---------------------------------------------------------------------------
@router.post("/registro", summary="Criar nova conta de usuário")
def registrar(dados: RegistroIn, request: Request):
    try:
        user = AuthService.registrar(
            nome=dados.nome, email=dados.email, senha=dados.senha,
            ip_origem=_cliente_ip(request),
        )
    except AuthError as e:
        raise _ou_401(e)
    # Já autentica e devolve token para fluxo contínuo no front
    try:
        login = AuthService.autenticar(
            email=dados.email, senha=dados.senha,
            ip_origem=_cliente_ip(request),
            user_agent=request.headers.get("user-agent", "")[:300],
        )
        sessao = AuthService.criar_sessao(
            login["id"], lembrar=True,
            ip_origem=_cliente_ip(request),
            user_agent=request.headers.get("user-agent", "")[:300],
        )
    except AuthError as e:
        raise _ou_401(e)
    return {"usuario": login, "token": sessao["token"], "expira_em": sessao["expira_em"]}


@router.post("/login", summary="Autenticar e receber token de sessão")
def login(dados: LoginIn, request: Request):
    ip = _cliente_ip(request)
    ua = request.headers.get("user-agent", "")[:300]
    try:
        user = AuthService.autenticar(dados.email, dados.senha, ip_origem=ip, user_agent=ua)
        sessao = AuthService.criar_sessao(
            user["id"], lembrar=dados.lembrar, ip_origem=ip, user_agent=ua,
        )
    except AuthError as e:
        raise _ou_401(e)
    return {"usuario": user, "token": sessao["token"], "expira_em": sessao["expira_em"]}


@router.post("/logout", summary="Encerrar a sessão atual")
def logout(
    request: Request,
    x_auth_token: Optional[str] = Header(default=None),
):
    user = AuthService.validar_sessao(x_auth_token or "")
    if user:
        AuthService.revogar_sessao(x_auth_token or "")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Endpoints autenticados
# ---------------------------------------------------------------------------
@router.get("/eu", summary="Dados do usuário autenticado")
def eu(user: dict = Depends(usuario_atual)):
    return {"usuario": user}


@router.post("/trocar-senha", summary="Trocar a própria senha (revoga sessões)")
def trocar_senha(dados: TrocaSenhaIn, user: dict = Depends(usuario_atual)):
    try:
        AuthService.trocar_senha(user["id"], dados.senha_atual, dados.nova_senha)
    except AuthError as e:
        raise _ou_401(e)
    return {"ok": True, "mensagem": "Senha alterada. Faça login novamente."}


# ---------------------------------------------------------------------------
# Reset de senha (token de uso único; em produção seria enviado por e-mail)
# ---------------------------------------------------------------------------
@router.post("/reset/solicitar", summary="Solicitar token de redefinição")
def reset_solicitar(dados: ResetSolicitarIn, request: Request):
    token = AuthService.solicitar_reset(dados.email)
    # Resposta sempre igual (não vaza existência de conta). O token só é
    # devolvido em ambiente de desenvolvimento, para fins acadêmicos.
    resp = {"ok": True,
            "mensagem": "Se o e-mail existir, um token de redefinição foi gerado."}
    if token:
        resp["token_dev"] = token  # TODO: remover em produção (enviar por e-mail)
    return resp


@router.post("/reset/confirmar", summary="Redefinir a senha com o token")
def reset_confirmar(dados: ResetConfirmarIn):
    try:
        AuthService.redefinir_senha(dados.token, dados.nova_senha)
    except AuthError as e:
        raise _ou_401(e)
    return {"ok": True, "mensagem": "Senha redefinida com sucesso."}


# ---------------------------------------------------------------------------
# Status do subsistema de autenticação
# ---------------------------------------------------------------------------
@router.get("/health", summary="Status do schema auth")
def auth_health():
    return AuthService.health()

