"""
CLI de administração de usuários — Mapa da Segurança DF.

Uso (a partir da raiz do projeto):

    # Listar usuários
    python -m db.auth_admin listar

    # Criar usuário (senha pedida interativamente, sem eco)
    python -m db.auth_admin criar --nome "Ana Silva" --email ana@ucb.br [--admin]

    # Promover / rebaixar para admin
    python -m db.auth_admin promover --email ana@ucb.br
    python -m db.auth_admin rebaixar --email ana@ucb.br

    # Ativar / desativar conta
    python -m db.auth_admin ativar --email ana@ucb.br
    python -m db.auth_admin desativar --email ana@ucb.br

    # Resetar senha de um usuário (gera token de 30 min e redefine)
    python -m db.auth_admin reset-senha --email ana@ucb.br [--nova "Senha@123"]

    # Aplicar/verificar o schema auth no banco
    python -m db.auth_admin schema

Requer que o PostgreSQL esteja no ar (docker compose up -d) e que as
dependências estejam instaladas. A primeira criação aplica o schema
automaticamente se ele não existir.
"""

import argparse
import getpass
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.db.session import SessionLocal
from api.services.auth_service import AuthService, AuthError, validar_forca_senha
from sqlalchemy import text


def _email_existe(email: str):
    with SessionLocal() as s:
        return s.execute(text(
            "SELECT id FROM auth.usuario WHERE email = :e"
        ), {"e": email.strip().lower()}).first()


def cmd_listar(_):
    usuarios = AuthService.listar_usuarios()
    if not usuarios:
        print("Nenhum usuário cadastrado.")
        return 0
    print(f"{'ID':>4}  {'PAPEL':<8} {'ATIVO':<5} {'EMAIL':<30} NOME")
    print("-" * 80)
    for u in usuarios:
        print(f"{u['id']:>4}  {u['papel']:<8} {'sim' if u['ativo'] else 'não':<5} "
              f"{u['email']:<30} {u['nome']}")
    return 0


def cmd_criar(args):
    senha = getpass.getpass("Senha para o novo usuário: ")
    confirm = getpass.getpass("Confirme a senha: ")
    if senha != confirm:
        print("✖ Senhas não coincidem.")
        return 1
    problemas = validar_forca_senha(senha)
    if problemas:
        print("✖ Senha fraca — precisa " + "; ".join(problemas) + ".")
        return 1
    try:
        user = AuthService.registrar(args.nome, args.email, senha,
                                     papel="admin" if args.admin else "usuario")
    except AuthError as e:
        print(f"✖ {e.mensagem}")
        return 1
    print(f"✔ Usuário criado: #{user['id']} — {user['nome']} <{user['email']}> "
          f"[{user['papel']}]")
    return 0


def _localizar_por_email(args) -> int:
    row = _email_existe(args.email)
    if not row:
        print(f"✖ Usuário não encontrado: {args.email}")
        return 1
    return row[0]


def cmd_promover(args):
    uid = _localizar_por_email(args)
    if isinstance(uid, int) and uid > 0:
        AuthService.promover_admin(uid, True)
        print(f"✔ Usuário #{uid} agora é admin.")
        return 0
    return uid


def cmd_rebaixar(args):
    uid = _localizar_por_email(args)
    if isinstance(uid, int) and uid > 0:
        AuthService.promover_admin(uid, False)
        print(f"✔ Usuário #{uid} rebaixado para 'usuario'.")
        return 0
    return uid


def cmd_ativar(args):
    uid = _localizar_por_email(args)
    if isinstance(uid, int) and uid > 0:
        AuthService.alterar_status(uid, True)
        print(f"✔ Usuário #{uid} ativado.")
        return 0
    return uid


def cmd_desativar(args):
    uid = _localizar_por_email(args)
    if isinstance(uid, int) and uid > 0:
        AuthService.alterar_status(uid, False)
        print(f"✔ Usuário #{uid} desativado (sessões revogadas).")
        return 0
    return uid


def cmd_reset_senha(args):
    uid = _localizar_por_email(args)
    if not (isinstance(uid, int) and uid > 0):
        return uid

    if args.nova:
        nova = args.nova
    else:
        nova = getpass.getpass("Nova senha: ")
        confirm = getpass.getpass("Confirme: ")
        if nova != confirm:
            print("✖ Senhas não coincidem.")
            return 1

    problemas = validar_forca_senha(nova)
    if problemas:
        print("✖ Senha fraca — precisa " + "; ".join(problemas) + ".")
        return 1

    try:
        AuthService.redefinir_senha(AuthService.solicitar_reset(args.email) or "", nova)
    except AuthError as e:
        print(f"✖ {e.mensagem}")
        return 1
    print(f"✔ Senha redefinida para {args.email}. Sessões revogadas.")
    return 0


def cmd_schema(_):
    try:
        AuthService.criar_schema()
        print("✔ Schema 'auth' criado/verificado (db/auth_schema.sql).")
        print(f"  Usuários cadastrados: {AuthService.health().get('usuarios', 0)}")
        return 0
    except Exception as e:
        print(f"✖ Falha ao aplicar schema: {str(e)[:300]}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Administração de usuários (Mapa da Segurança DF)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("listar", help="Lista todos os usuários")
    p.set_defaults(fn=cmd_listar)
    p = sub.add_parser("criar", help="Cria um usuário (senha via prompt)")
    p.add_argument("--nome", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--admin", action="store_true", help="Cria como admin")
    p.set_defaults(fn=cmd_criar)

    for nome, ajuda in [("promover", "Torna admin"), ("rebaixar", "Remove admin"),
                        ("ativar", "Ativa conta"), ("desativar", "Desativa conta")]:
        p = sub.add_parser(nome, help=ajuda)
        p.add_argument("--email", required=True)
        p.set_defaults(fn=globals()[f"cmd_{nome}"])

    p = sub.add_parser("reset-senha", help="Redefine a senha de um usuário")
    p.add_argument("--email", required=True)
    p.add_argument("--nova", help="Nova senha (opcional; senão pergunta)")
    p.set_defaults(fn=cmd_reset_senha)

    p = sub.add_parser("schema", help="Aplica/verifica o schema auth no banco")
    p.set_defaults(fn=cmd_schema)

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
