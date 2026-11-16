"""
Smoke test de relatórios salvos (schema auth.relatorio_salvo, HU08).

Valida o ciclo completo contra o PostgreSQL real:

  1. Criação de dois usuários de teste (A e B)
  2. Usuário A salva um relatório
  3. Isolamento na listagem: B não vê o relatório de A
  4. Isolamento na exclusão: B não consegue excluir relatório de A
  5. Título duplicado (mesmo usuário) é rejeitado
  6. Validações de entrada (título, dimensão, tipo de gráfico, top_n)
  7. Usuário A exclui o próprio relatório
  8. Excluir relatório já excluído/inexistente é rejeitado
  9. Sessão ausente/inválida é rejeitada (base do 401 nas rotas HTTP)
  10. Limpeza dos dados de teste (deixa o banco como estava)

Uso:
    python -m db.relatorio_smoke_test
"""

import sys
import uuid
from pathlib import Path

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.db.session import SessionLocal
from api.services.auth_service import AuthService
from api.services.relatorio_service import RelatorioError, RelatorioService

_PASSO = [0]


def _passo(titulo: str) -> None:
    _PASSO[0] += 1
    print(f"\n{_PASSO[0]}. {titulo}")
    print("-" * 60)


def main() -> int:
    erros = []
    marcador = f"smoketestrel-{uuid.uuid4().hex[:8]}"
    senha = "Senha@Forte123"

    def _limpar():
        with SessionLocal() as s:
            s.execute(text("""
                DELETE FROM auth.relatorio_salvo
                WHERE usuario_id IN (
                    SELECT id FROM auth.usuario WHERE email LIKE :padrao
                )
            """), {"padrao": f"{marcador}%"})
            s.execute(
                text("DELETE FROM auth.usuario WHERE email LIKE :padrao"),
                {"padrao": f"{marcador}%"},
            )
            s.commit()

    try:
        # 1. Usuários ----------------------------------------------------
        _passo("Criando dois usuários de teste (A e B)")
        _limpar()
        user_a = AuthService.registrar("Smoke A", f"{marcador}-a@exemplo.com", senha)
        user_b = AuthService.registrar("Smoke B", f"{marcador}-b@exemplo.com", senha)
        print(f"  ✔ Usuário A #{user_a['id']}, Usuário B #{user_b['id']}.")

        # 2. Salvar --------------------------------------------------------
        _passo("Usuário A salva um relatório")
        relatorio = RelatorioService.salvar(
            usuario_id=user_a["id"],
            titulo="Smoke · Gama · Barras",
            dimensao="por_regiao",
            tipo_grafico="Barras",
            top_n=10,
            filtros={"regioes": ["Gama"]},
        )
        assert relatorio["titulo"] == "Smoke · Gama · Barras"
        print(f"  ✔ Relatório #{relatorio['id']} salvo para o usuário A.")

        # 3. Isolamento na listagem -----------------------------------------
        _passo("Isolamento: usuário B não vê o relatório de A")
        lista_a = RelatorioService.listar(user_a["id"])
        lista_b = RelatorioService.listar(user_b["id"])
        assert len(lista_a) == 1 and lista_a[0]["id"] == relatorio["id"]
        assert lista_b == []
        print("  ✔ Usuário A vê 1 relatório; usuário B vê 0.")

        # 4. Isolamento na exclusão ------------------------------------------
        _passo("Isolamento: usuário B não consegue excluir relatório de A")
        try:
            RelatorioService.excluir(usuario_id=user_b["id"], relatorio_id=relatorio["id"])
            erros.append("Usuário B conseguiu excluir relatório de A")
        except RelatorioError as e:
            assert e.codigo == "nao_encontrado"
            print("  ✔ Exclusão cross-user rejeitada (mensagem genérica 'não encontrado').")
        assert len(RelatorioService.listar(user_a["id"])) == 1, (
            "relatório de A sumiu após tentativa de exclusão por B"
        )

        # 5. Título duplicado -------------------------------------------------
        _passo("Título duplicado (mesmo usuário) é rejeitado")
        try:
            RelatorioService.salvar(
                usuario_id=user_a["id"], titulo="Smoke · Gama · Barras",
                dimensao="por_ano", tipo_grafico="Linha", top_n=5,
            )
            erros.append("Título duplicado foi aceito")
        except RelatorioError as e:
            assert e.codigo == "titulo_duplicado"
            print("  ✔ Título duplicado rejeitado.")

        # 6. Validações de entrada ---------------------------------------------
        _passo("Validações de entrada")
        casos_invalidos = [
            dict(titulo="", dimensao="por_regiao", tipo_grafico="Barras", top_n=10),
            dict(titulo="Válido", dimensao="por_bairro", tipo_grafico="Barras", top_n=10),
            dict(titulo="Válido", dimensao="por_regiao", tipo_grafico="Radar", top_n=10),
            dict(titulo="Válido", dimensao="por_regiao", tipo_grafico="Barras", top_n=1),
            dict(titulo="Válido", dimensao="por_regiao", tipo_grafico="Barras", top_n=99),
        ]
        for caso in casos_invalidos:
            try:
                RelatorioService.salvar(usuario_id=user_a["id"], **caso)
                erros.append(f"Caso inválido foi aceito: {caso}")
            except RelatorioError as e:
                if e.codigo != "validacao":
                    erros.append(f"Código de erro inesperado para {caso}: {e.codigo}")
        print(f"  ✔ {len(casos_invalidos)} combinações inválidas rejeitadas.")

        # 7. Exclusão normal ----------------------------------------------------
        _passo("Usuário A exclui o próprio relatório")
        RelatorioService.excluir(usuario_id=user_a["id"], relatorio_id=relatorio["id"])
        assert RelatorioService.listar(user_a["id"]) == []
        print("  ✔ Relatório excluído; lista de A fica vazia.")

        # 8. Exclusão de relatório inexistente -----------------------------------
        _passo("Excluir relatório já excluído/inexistente é rejeitado")
        try:
            RelatorioService.excluir(usuario_id=user_a["id"], relatorio_id=relatorio["id"])
            erros.append("Exclusão de relatório já excluído deveria falhar")
        except RelatorioError as e:
            assert e.codigo == "nao_encontrado"
            print("  ✔ Exclusão de relatório inexistente rejeitada.")

        # 9. Base do 401 (sessão ausente/inválida) --------------------------------
        _passo("Sessão ausente/inválida é rejeitada (base do 401 nas rotas)")
        assert AuthService.validar_sessao("") is None
        assert AuthService.validar_sessao("token-que-nao-existe") is None
        print(
            "  ✔ Sem token válido, nenhum usuário é retornado "
            "(rotas de /api/relatorios devolvem 401 via usuario_atual)."
        )

    finally:
        # 10. Limpeza -----------------------------------------------------------
        _passo("Limpeza dos dados de teste")
        _limpar()
        with SessionLocal() as s:
            restantes = int(
                s.execute(
                    text("SELECT COUNT(*) FROM auth.usuario WHERE email LIKE :padrao"),
                    {"padrao": f"{marcador}%"},
                ).scalar()
                or 0
            )
        print("  ✔ Banco limpo." if restantes == 0 else f"  ⚠ {restantes} linhas restantes.")

        print("\n" + "=" * 60)
        if erros:
            print(f"✖ RELATÓRIOS SMOKE TEST FALHOU — {len(erros)} problema(s):")
            for e in erros:
                print(f"  - {e}")
            return 1
        print("✔ RELATÓRIOS SMOKE TEST OK — todos os passos passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
