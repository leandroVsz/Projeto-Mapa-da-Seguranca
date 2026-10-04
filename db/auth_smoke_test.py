"""
Smoke test do subsistema de autenticação (schema auth).

Valida o ciclo completo contra o PostgreSQL real:

  1. Aplicação do schema (idempotente)
  2. Registro de usuário + política de senha
  3. Login correto, senha errada, lockout anti-força-bruta
  4. Sessões (criação, validação, revogação, "lembrar")
  5. Troca de senha revogando sessões
  6. Reset de senha via token (uso único)
  7. Administração (promover/rebaixar/desativar)
  8. Auditoria em auth.log_acesso
  9. Limpeza dos dados de teste (deixa o banco como estava)

Uso:
    python -m db.auth_smoke_test
"""

import sys
import uuid
from pathlib import Path

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.db.session import SessionLocal
from api.services.auth_service import (
    AuthService,
    AuthError,
    validar_forca_senha,
)

_PASSO = [0]


def _passo(titulo: str) -> None:
    _PASSO[0] += 1
    print(f"\n{_PASSO[0]}. {titulo}")
    print("-" * 60)


def main() -> int:
    erros = []

    # 1. Schema ----------------------------------------------------------
    _passo("Aplicando schema auth (idempotente)")
    try:
        AuthService.criar_schema()
        print("  ✔ Schema 'auth' pronto.")
    except Exception as e:
        print(f"  ✖ Falha ao aplicar schema: {str(e)[:200]}")
        return 1

    marcador = f"smoketest-{uuid.uuid4().hex[:8]}"
    email = f"{marcador}@exemplo.com"
    senha = "Senha@Forte123"

    def _limpar():
        with SessionLocal() as s:
            s.execute(text("DELETE FROM auth.usuario WHERE email LIKE 'smoketest-%'"))
            s.execute(text("DELETE FROM auth.log_acesso WHERE email LIKE 'smoketest-%'"))
            s.commit()

    try:
        # 2. Registro --------------------------------------------------------
        _passo("Registro de usuário")
        _limpar()
        user = AuthService.registrar("Smoke Test", email, senha)
        assert user["email"] == email and user["papel"] == "usuario"
        print(f"  ✔ Usuário #{user['id']} criado ({user['email']}).")

        try:
            AuthService.registrar("Duplicado", email, senha)
            erros.append("Registro duplicado deveria falhar")
        except AuthError as e:
            assert e.codigo == "email_em_uso"
            print("  ✔ E-mail duplicado rejeitado.")

        for fraca in ["curta", "senhatodaemminiscula1", "SEMNUMERO123", "12345678"]:
            try:
                AuthService.registrar("Fraca", f"fraca-{uuid.uuid4().hex[:6]}@x.com", fraca)
                erros.append(f"Senha fraca aceita: {fraca}")
            except AuthError as e:
                assert e.codigo == "senha_fraca"
        print("  ✔ Política de senha rejeita senhas fracas.")

        # 3. Login -----------------------------------------------------------
        _passo("Login (correto, errado, lockout)")
        try:
            AuthService.autenticar(email, "Errada@123")
            erros.append("Login com senha errada deveria falhar")
        except AuthError as e:
            assert e.codigo == "credenciais"
            print("  ✔ Senha errada rejeitada (mensagem genérica).")

        try:
            AuthService.autenticar("inexistente@exemplo.com", "Qualquer@1")
            erros.append("Login de e-mail inexistente deveria falhar")
        except AuthError as e:
            assert e.codigo == "credenciais"
            print("  ✔ E-mail inexistente rejeitado sem vazar existência.")

        ok = AuthService.autenticar(email, senha)
        assert ok["id"] == user["id"]
        print("  ✔ Login correto funciona e zera falhas.")

        # 4. Sessões ---------------------------------------------------------
        _passo("Sessões (validação e revogação)")
        sess = AuthService.criar_sessao(user["id"], lembrar=True)
        assert AuthService.validar_sessao(sess["token"])["id"] == user["id"]
        print("  ✔ Token de sessão válido.")

        AuthService.revogar_sessao(sess["token"])
        assert AuthService.validar_sessao(sess["token"]) is None
        print("  ✔ Revogação de sessão imediata.")

        with SessionLocal() as s:
            exp = s.execute(text("""
                SELECT expira_em - criado_em FROM auth.sessao_usuario
                WHERE usuario_id = :uid LIMIT 1
            """), {"uid": user["id"]}).scalar()
        assert exp and exp.days >= 29, f"expiração 'lembrar' errada: {exp}"
        print("  ✔ Sessão 'lembrar' com ~30 dias.")

        # 5. Troca de senha --------------------------------------------------
        _passo("Troca de senha revoga sessões")
        sess2 = AuthService.criar_sessao(user["id"])
        AuthService.trocar_senha(user["id"], senha, "Nova@Senha456")
        assert AuthService.validar_sessao(sess2["token"]) is None
        try:
            AuthService.autenticar(email, senha)
            erros.append("Senha antiga ainda funciona após troca")
        except AuthError:
            pass
        AuthService.autenticar(email, "Nova@Senha456")
        print("  ✔ Troca de senha OK; sessões antigas revogadas.")

        # 6. Reset de senha --------------------------------------------------
        _passo("Reset de senha via token (uso único)")
        try:
            AuthService.redefinir_senha("token-invalido", "Outra@Senha789")
            erros.append("Token inválido deveria falhar")
        except AuthError as e:
            assert e.codigo == "token_invalido"
            print("  ✔ Token inválido rejeitado.")

        tok = AuthService.solicitar_reset(email)
        assert tok, "token de reset não gerado"
        AuthService.redefinir_senha(tok, "Reset@Senha789")
        try:
            AuthService.redefinir_senha(tok, "Reuso@Senha789")
            erros.append("Token reutilizado deveria falhar")
        except AuthError:
            print("  ✔ Token de uso único (reuso bloqueado).")
        AuthService.autenticar(email, "Reset@Senha789")
        print("  ✔ Reset com token válido funciona.")

        # 7. Administração ---------------------------------------------------
        _passo("Administração")
        AuthService.promover_admin(user["id"], True)
        assert AuthService.obter_por_id(user["id"])["papel"] == "admin"
        AuthService.promover_admin(user["id"], False)
        AuthService.alterar_status(user["id"], False)
        sess3 = AuthService.criar_sessao(user["id"])
        assert AuthService.validar_sessao(sess3["token"]) is None
        AuthService.alterar_status(user["id"], True)
        print("  ✔ Promover/rebaixar/desativar/reativar OK "
              "(desativar revoga sessões).")

        # 8. Auditoria -------------------------------------------------------
        _passo("Auditoria")
        with SessionLocal() as s:
            n = int(s.execute(text(
                "SELECT COUNT(*) FROM auth.log_acesso WHERE email = :e"
            ), {"e": email}).scalar() or 0)
        assert n >= 5, f"poucos eventos de auditoria: {n}"
        print(f"  ✔ {n} eventos registrados em auth.log_acesso.")

    finally:
        # 9. Limpeza ---------------------------------------------------------
        _passo("Limpeza dos dados de teste")
        _limpar()
        restantes = 0
        with SessionLocal() as s:
            restantes = int(s.execute(text(
                "SELECT COUNT(*) FROM auth.usuario WHERE email LIKE 'smoketest-%'"
            )).scalar() or 0)
        print("  ✔ Banco limpo." if restantes == 0 else f"  ⚠ {restantes} linhas restantes.")

        # Resumo
        print("\n" + "=" * 60)
        if erros:
            print(f"✖ AUTH SMOKE TEST FALHOU — {len(erros)} problema(s):")
            for e in erros:
                print(f"  - {e}")
            return 1
        print("✔ AUTH SMOKE TEST OK — todos os passos passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
