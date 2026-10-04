"""
UI de autenticação do Streamlit — Mapa da Segurança DF.

Fornece:
  - render_auth_tab(): aba "👤 Conta" com login, registro, perfil,
    troca de senha e administração (se papel=admin);
  - render_login_gate(): tela cheia que bloqueia o dashboard quando
    AUTH_REQUIRED=true e ninguém está autenticado.

O token de sessão fica em st.session_state (volátil, não persistido em
disco). Sem AUTH_REQUIRED o painel continua acessível a convidados.
"""

from typing import Any, Dict, Optional

import streamlit as st
import requests

from api.services.auth_service import (
    AuthService,
    AuthError,
    validar_forca_senha,
)

_API_URL = "http://localhost:8000"
_TIMEOUT = 3.0

PAPEIS = {"admin": "Administrador", "usuario": "Usuário"}


# ---------------------------------------------------------------------------
# Estado de sessão
# ---------------------------------------------------------------------------
def init_auth_state() -> None:
    ss = st.session_state
    ss.setdefault("auth_usuario", None)   # dict {id, email, nome, papel, ...}
    ss.setdefault("auth_token", None)     # token opaco da sessão (API)
    ss.setdefault("auth_modo", "login")   # login | registro | reset
    ss.setdefault("auth_aviso", None)


def is_logado() -> bool:
    return bool(st.session_state.get("auth_usuario"))


def usuario_logado() -> Optional[Dict[str, Any]]:
    return st.session_state.get("auth_usuario")


def logout() -> None:
    token = st.session_state.get("auth_token")
    if token:
        try:
            requests.post(f"{_API_URL}/api/auth/logout",
                          headers={"X-Auth-Token": token}, timeout=_TIMEOUT)
        except requests.RequestException:
            pass  # revoga localmente mesmo se a API estiver offline
    AuthService.revogar_sessao(token or "")
    for k in ("auth_usuario", "auth_token"):
        st.session_state[k] = None
    st.session_state["auth_modo"] = "login"


# ---------------------------------------------------------------------------
# Chamadas: API REST primeiro; fallback direto no banco se API offline
# ---------------------------------------------------------------------------
def _api_post(path: str, payload: dict, token: Optional[str] = None):
    headers = {"X-Auth-Token": token} if token else {}
    return requests.post(f"{_API_URL}{path}", json=payload,
                         headers=headers, timeout=_TIMEOUT)


def _chamar(path: str, payload: dict, token: Optional[str] = None):
    """Tenta API; retorna (ok, data) com data sendo dict de sucesso ou
    {'detail': msg} de erro. Se a API estiver offline, cai no banco direto."""
    try:
        r = _api_post(path, payload, token)
        if r.status_code < 400:
            return True, r.json()
        try:
            return False, r.json()
        except ValueError:
            return False, {"detail": f"HTTP {r.status_code}"}
    except requests.RequestException:
        return None, None  # sinaliza "API offline"


def _via_banco(path: str, payload: dict):
    """Fallback direto (mesma lógica dos endpoints, sem HTTP)."""
    try:
        if path == "/api/auth/login":
            user = AuthService.autenticar(payload["email"], payload["senha"])
            sessao = AuthService.criar_sessao(user["id"], lembrar=payload.get("lembrar", False))
            return {"usuario": user, "token": sessao["token"]}
        if path == "/api/auth/registro":
            user = AuthService.registrar(payload["nome"], payload["email"], payload["senha"])
            sessao = AuthService.criar_sessao(user["id"], lembrar=True)
            return {"usuario": user, "token": sessao["token"]}
        if path == "/api/auth/trocar-senha":
            AuthService.trocar_senha(
                st.session_state["auth_usuario"]["id"],
                payload["senha_atual"], payload["nova_senha"])
            return {"ok": True}
        if path == "/api/auth/reset/solicitar":
            tok = AuthService.solicitar_reset(payload["email"])
            return {"ok": True, "token_dev": tok}
        if path == "/api/auth/reset/confirmar":
            AuthService.redefinir_senha(payload["token"], payload["nova_senha"])
            return {"ok": True}
    except AuthError as e:
        return {"detail": e.mensagem}
    return {"detail": "Operação não suportada offline."}


def chamar_auth(path: str, payload: dict, token: Optional[str] = None):
    """Executa via API REST; se offline, executa direto no banco."""
    ok, data = _chamar(path, payload, token)
    if ok is None:                       # API offline -> fallback local
        return False, _via_banco(path, payload)
    return ok, data


# ---------------------------------------------------------------------------
# Widgets reutilizáveis
# ---------------------------------------------------------------------------
def _form_login():
    st.markdown("Entre com sua conta para acessar o painel.")
    with st.form("form_login", clear_on_submit=False):
        email = st.text_input("E-mail", key="login_email")
        senha = st.text_input("Senha", type="password", key="login_senha")
        lembrar = st.checkbox("Manter conectado (30 dias)", value=True, key="login_lembrar")
        enviar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    c1, c2 = st.columns(2)
    if c1.button("Criar uma conta", use_container_width=True):
        st.session_state["auth_modo"] = "registro"; st.rerun()
    if c2.button("Esqueci minha senha", use_container_width=True):
        st.session_state["auth_modo"] = "reset"; st.rerun()

    if enviar:
        if not email or not senha:
            st.warning("Informe e-mail e senha.")
            return
        ok, data = chamar_auth("/api/auth/login", {
            "email": email, "senha": senha, "lembrar": lembrar,
        })
        if ok and data.get("usuario"):
            st.session_state["auth_usuario"] = data["usuario"]
            st.session_state["auth_token"] = data["token"]
            st.session_state["auth_aviso"] = None
            st.rerun()
        else:
            st.error(data.get("detail", "Falha no login."))


def _form_registro():
    st.markdown("Crie sua conta para salvar preferências e acessar recursos exclusivos.")
    with st.form("form_registro", clear_on_submit=False):
        nome = st.text_input("Nome completo", key="reg_nome")
        email = st.text_input("E-mail", key="reg_email")
        c1, c2 = st.columns(2)
        senha = c1.text_input("Senha", type="password", key="reg_senha")
        confirmar = c2.text_input("Confirmar senha", type="password", key="reg_senha2")
        enviar = st.form_submit_button("Registrar", type="primary", use_container_width=True)

    if st.button("← Voltar para o login", use_container_width=True):
        st.session_state["auth_modo"] = "login"; st.rerun()

    if enviar:
        if senha != confirmar:
            st.error("As senhas não coincidem.")
            return
        problemas = validar_forca_senha(senha)
        if problemas:
            st.error("A senha precisa " + "; ".join(problemas) + ".")
            return
        ok, data = chamar_auth("/api/auth/registro", {
            "nome": nome, "email": email, "senha": senha,
        })
        if ok and data.get("usuario"):
            st.session_state["auth_usuario"] = data["usuario"]
            st.session_state["auth_token"] = data["token"]
            st.success("Conta criada com sucesso! Você já está autenticado.")
            st.rerun()
        else:
            st.error(data.get("detail", "Falha no registro."))


def _form_reset():
    st.markdown("Informe seu e-mail para gerar um token de redefinição de senha.")
    with st.form("form_reset"):
        email = st.text_input("E-mail", key="reset_email")
        enviar = st.form_submit_button("Gerar token", type="primary", use_container_width=True)
    if enviar:
        ok, data = chamar_auth("/api/auth/reset/solicitar", {"email": email})
        if ok:
            tok = data.get("token_dev")
            st.info("Se o e-mail existir, um token foi gerado (válido por 30 minutos).")
            if tok:
                st.code(tok, language="text")
                st.caption("Token exibido apenas neste ambiente de desenvolvimento "
                           "(em produção seria enviado por e-mail).")
        else:
            st.error(data.get("detail", "Falha ao solicitar token."))

    st.divider()
    st.markdown("**Já tem o token?** Redefina sua senha:")
    with st.form("form_reset_confirmar"):
        token = st.text_input("Token recebido", key="reset_token")
        nova = st.text_input("Nova senha", type="password", key="reset_nova")
        enviar2 = st.form_submit_button("Redefinir senha", use_container_width=True)
    if enviar2:
        if not token or not nova:
            st.warning("Informe o token e a nova senha.")
            return
        ok, data = chamar_auth("/api/auth/reset/confirmar",
                               {"token": token, "nova_senha": nova})
        if ok:
            st.success("Senha redefinida! Faça login com a nova senha.")
            st.session_state["auth_modo"] = "login"
        else:
            st.error(data.get("detail", "Falha ao redefinir senha."))

    if st.button("← Voltar para o login", use_container_width=True):
        st.session_state["auth_modo"] = "login"; st.rerun()


def _form_trocar_senha(user: dict):
    with st.form("form_trocar_senha"):
        atual = st.text_input("Senha atual", type="password", key="ts_atual")
        nova = st.text_input("Nova senha", type="password", key="ts_nova")
        conf = st.text_input("Confirmar nova senha", type="password", key="ts_conf")
        enviar = st.form_submit_button("Trocar senha", use_container_width=True)
    if enviar:
        if nova != conf:
            st.error("As novas senhas não coincidem.")
            return
        problemas = validar_forca_senha(nova)
        if problemas:
            st.error("A nova senha precisa " + "; ".join(problemas) + ".")
            return
        ok, data = chamar_auth("/api/auth/trocar-senha", {
            "senha_atual": atual, "nova_senha": nova,
        }, token=st.session_state.get("auth_token"))
        if ok:
            st.success("Senha alterada! Todas as sessões foram encerradas.")
            logout()
        else:
            st.error(data.get("detail", "Falha ao trocar senha."))


def _painel_admin():
    st.markdown("### 👥 Administração de Usuários")
    try:
        usuarios = AuthService.listar_usuarios()
    except Exception:
        st.warning("Banco indisponível para administração.")
        return
    if not usuarios:
        st.info("Nenhum usuário cadastrado.")
        return
    for u in usuarios:
        with st.expander(f"{'👑' if u['papel'] == 'admin' else '👤'} "
                         f"{u['nome']} — {u['email']} ({PAPEIS[u['papel']]})"):
            c1, c2 = st.columns(2)
            if u["ativo"]:
                if c1.button("Desativar", key=f"des_{u['id']}"):
                    AuthService.alterar_status(u["id"], False)
                    st.rerun()
            else:
                if c1.button("Reativar", key=f"rea_{u['id']}"):
                    AuthService.alterar_status(u["id"], True)
                    st.rerun()
            if u["papel"] == "usuario":
                if c2.button("Promover a admin", key=f"adm_{u['id']}"):
                    AuthService.promover_admin(u["id"], True)
                    st.rerun()
            else:
                if c2.button("Rebaixar a usuário", key=f"reb_{u['id']}"):
                    AuthService.promover_admin(u["id"], False)
                    st.rerun()
            st.caption(f"Cadastrado em: {u['criado_em'][:10]} | Último login: "
                       f"{(u['ultimo_login_em'] or '—')[:10]}")


def _perfil_logado(user: dict):
    st.success(f"Autenticado como **{user['nome']}** ({user['email']})")
    st.caption(f"Papel: {PAPEIS[user['papel']]} | "
               f"Último login: {(user['ultimo_login_em'] or '—')[:10]}")

    c1, c2 = st.columns(2)
    if c1.button("🚪 Sair", use_container_width=True):
        logout(); st.rerun()
    if c2.button("🔑 Trocar senha", use_container_width=True):
        st.session_state["auth_trocar"] = not st.session_state.get("auth_trocar", False)

    if st.session_state.get("auth_trocar"):
        _form_trocar_senha(user)

    st.divider()
    if user["papel"] == "admin":
        _painel_admin()


# ---------------------------------------------------------------------------
# Renderização principal
# ---------------------------------------------------------------------------
def render_auth_tab() -> None:
    """Conteúdo da aba 'Conta' dentro das tabs do dashboard."""
    init_auth_state()
    user = st.session_state.get("auth_usuario")

    if user:
        _perfil_logado(user)
        return

    modo = st.session_state.get("auth_modo", "login")
    if modo == "registro":
        _form_registro()
    elif modo == "reset":
        _form_reset()
    else:
        _form_login()


def render_login_gate(auth_required: bool) -> bool:
    """Se AUTH_REQUIRED e não logado: mostra tela de bloqueio e retorna False."""
    init_auth_state()
    if not auth_required or is_logado():
        return True

    st.title("🛡️ Mapa da Segurança DF")
    st.markdown("### Acesso restrito")
    st.warning("Faça login para visualizar o painel de criminalidade.")
    modo = st.session_state.get("auth_modo", "login")
    if modo == "registro":
        _form_registro()
    elif modo == "reset":
        _form_reset()
    else:
        _form_login()
    return False
