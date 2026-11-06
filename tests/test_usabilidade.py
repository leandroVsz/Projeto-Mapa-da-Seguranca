"""Testes de usabilidade — seção 4.3 do relatório (heurísticas de Nielsen).

A interface Streamlit é executada de verdade com `streamlit.testing.v1.AppTest`,
sem navegador: o teste observa os mesmos widgets e mensagens que o usuário vê
(abas, filtros, cartões, botões, avisos e textos de ajuda).

Cada classe cobre uma heurística. Os testes não dependem de API no ar: o app
roda no "Modo Direto Local" (fallback CSV), que é o modo documentado para
quem não subiu o backend.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str((Path(__file__).resolve().parent.parent / "app" / "main.py").resolve())


def _novo_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=180)
    at.run()
    return at


def _botao(at: AppTest, rotulo: str):
    return next(b for b in at.button if b.label == rotulo)


def _numero_br(valor: str) -> int:
    return int(str(valor).replace(".", "").replace(",", "."))


@pytest.fixture(scope="module")
def app() -> AppTest:
    """Instância somente-leitura reaproveitada pelas verificações estáticas."""
    at = _novo_app()
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.fixture
def app_interativo() -> AppTest:
    """Instância nova para os testes que clicam/preenchem widgets."""
    at = _novo_app()
    assert not at.exception, [e.value for e in at.exception]
    return at


# ---------------------------------------------------------------------------
# 1. Visibilidade do status do sistema
# ---------------------------------------------------------------------------
class TestH1VisibilidadeStatus:
    def test_estado_do_backend_esta_visivel_na_barra_lateral(self, app):
        mensagens = [i.value for i in app.sidebar.info] + [
            s.value for s in app.sidebar.success
        ]
        assert any(
            "Backend API Conectado" in msg or "Modo Direto Local" in msg
            for msg in mensagens
        )

    def test_kpis_principais_sao_exibidos(self, app):
        rotulos = [m.label for m in app.metric]
        assert rotulos == [
            "Total de Ocorrências",
            "RA com Maior Incidência",
            "Crime Mais Frequente",
            "Mês Mais Crítico",
        ]
        assert all(str(m.value).strip() for m in app.metric)
        assert _numero_br(app.metric[0].value) > 0

    def test_quantidade_de_registros_visiveis_na_tabela(self, app):
        assert any("Mostrando" in c.value for c in app.caption)


# ---------------------------------------------------------------------------
# 2. Correspondência entre sistema e mundo real
# ---------------------------------------------------------------------------
class TestH2LinguagemDoDominio:
    def test_rotulos_usam_termos_do_dominio_e_pt_br(self, app):
        rotulos = {m.label for m in app.multiselect}
        assert "Região Administrativa (RA)" in rotulos
        assert "Eixo Indicador" in rotulos
        assert "Natureza da Ocorrência" in rotulos
        assert "Ano da Ocorrência" in rotulos
        assert [m.label for m in app.metric][1] == "RA com Maior Incidência"

    def test_dados_reais_da_ssp_df_aparecem_nas_opcoes(self, app):
        naturezas = next(
            m.options for m in app.multiselect if m.label == "Natureza da Ocorrência"
        )
        regioes = next(
            m.options for m in app.multiselect if m.label == "Região Administrativa (RA)"
        )
        anos = next(m.options for m in app.multiselect if m.label == "Ano da Ocorrência")

        assert "ROUBO A TRANSEUNTE" in naturezas
        assert any("Ceilândia" == r for r in regioes)
        # o widget devolve os anos como texto (ex.: "2024")
        assert "2024" in [str(ano) for ano in anos]
        assert [int(ano) for ano in anos] == sorted(
            (int(ano) for ano in anos), reverse=True
        )

    def test_fonte_e_periodo_dos_dados_sao_declarados(self, app):
        rodape = " ".join(c.value for c in app.sidebar.caption)
        assert "SSP-DF" in rodape
        assert "Dados mais recentes" in rodape


# ---------------------------------------------------------------------------
# 3. Controle e liberdade do usuário
# ---------------------------------------------------------------------------
class TestH3ControleELiberdade:
    def test_navegacao_por_abas_permite_alternar_contextos(self, app):
        assert [t.label for t in app.tabs] == [
            "📍 Mapa Geoespacial",
            "📊 Gráficos & Tendências",
            "📋 Tabela de Ocorrências",
            "🔌 Backend API REST",
            "👤 Conta & Acesso",
        ]

    def test_usuario_pode_ir_para_registro_e_voltar_ao_login(self, app_interativo):
        _botao(app_interativo, "Criar uma conta").click()
        app_interativo.run()
        assert any(b.label == "Registrar" for b in app_interativo.button)

        _botao(app_interativo, "← Voltar para o login").click()
        app_interativo.run()
        assert any(b.label == "Entrar" for b in app_interativo.button)

    def test_filtros_sao_opcionais_e_podem_ficar_vazios(self, app):
        assert all(m.value == [] for m in app.multiselect if m.label != "Ano da Ocorrência")
        assert app.select_slider[0].value == "Claro"  # configuração padrão do mapa


# ---------------------------------------------------------------------------
# 4. Consistência e padrões
# ---------------------------------------------------------------------------
class TestH4Consistencia:
    def test_cartoes_de_kpi_seguem_o_mesmo_padrao(self, app):
        assert len(app.metric) == 4
        assert all(" " in m.label for m in app.metric)
        # milhar no padrão brasileiro (ponto), sem decimais nos totais
        assert "." in app.metric[0].value or _numero_br(app.metric[0].value) < 1000

    def test_opcoes_de_grafico_sao_consistentes_com_a_exportacao(self, app):
        dimensoes = next(
            s.options for s in app.selectbox if s.label == "Dados a analisar"
        )
        tipos = next(s.options for s in app.selectbox if s.label == "Tipo de gráfico")
        assert dimensoes == ["Região Administrativa", "Natureza do crime", "Mês", "Ano"]
        assert tipos == [
            "Barras", "Barras horizontais", "Linha", "Área", "Pizza", "Rosca",
        ]
        assert [d.label for d in app.get("download_button")] == [
            "⬇️ Exportar CSV",
            "⬇️ Exportar PDF",
            "📥 Baixar Ocorrências Filtradas (CSV)",
        ]

    def test_nao_ha_erros_de_renderizacao(self, app):
        assert len(app.error) == 0
        assert len(app.exception) == 0


# ---------------------------------------------------------------------------
# 5. Prevenção de erros
# ---------------------------------------------------------------------------
class TestH5PrevencaoDeErros:
    def test_login_vazio_avisa_antes_de_enviar(self, app_interativo):
        _botao(app_interativo, "Entrar").click()
        app_interativo.run()
        assert any("Informe e-mail e senha" in w.value for w in app_interativo.warning)

    def test_registro_exige_confirmacao_de_senha(self, app_interativo):
        _botao(app_interativo, "Criar uma conta").click()
        app_interativo.run()

        app_interativo.text_input(key="reg_nome").set_value("Fulano de Teste")
        app_interativo.text_input(key="reg_email").set_value("fulano@teste.local")
        app_interativo.text_input(key="reg_senha").set_value("SenhaForte123")
        app_interativo.text_input(key="reg_senha2").set_value("OutraSenha123")
        _botao(app_interativo, "Registrar").click()
        app_interativo.run()

        assert any("senhas não coincidem" in e.value for e in app_interativo.error)

    def test_politica_de_senha_e_explicada_antes_do_envio(self, app_interativo):
        _botao(app_interativo, "Criar uma conta").click()
        app_interativo.run()

        app_interativo.text_input(key="reg_nome").set_value("Fulano de Teste")
        app_interativo.text_input(key="reg_email").set_value("fulano@teste.local")
        app_interativo.text_input(key="reg_senha").set_value("senhafraca")
        app_interativo.text_input(key="reg_senha2").set_value("senhafraca")
        _botao(app_interativo, "Registrar").click()
        app_interativo.run()

        erros = " ".join(e.value for e in app_interativo.error)
        assert "8 caracteres" in erros or "maiúscula" in erros

    def test_top_n_e_desabilitado_quando_nao_se_aplica(self, app_interativo):
        app_interativo.selectbox(key="grafico_dimensao").set_value("Mês")
        app_interativo.run()
        assert app_interativo.number_input(key="grafico_topn").disabled is True


# ---------------------------------------------------------------------------
# 6. Reconhecimento em vez de memorização
# ---------------------------------------------------------------------------
class TestH6Reconhecimento:
    def test_filtros_mostram_opcoes_e_placeholders(self, app):
        for multiselect in app.multiselect:
            assert len(multiselect.options) > 0
        regiões = next(
            m for m in app.multiselect if m.label == "Região Administrativa (RA)"
        )
        assert "Todas as regiões do DF" in regiões.placeholder

    def test_graficos_tem_rotulos_e_opcoes_visiveis(self, app):
        assert any(s.label == "Dados a analisar" for s in app.selectbox)
        assert any(s.label == "Tipo de gráfico" for s in app.selectbox)
        assert app.number_input[0].label == "Top N"
        assert app.select_slider[0].options == ["Claro", "Colorido", "Escuro"]

    def test_tabela_e_busca_ficam_na_mesma_aba(self, app):
        assert any("Buscar por crime ou RA" in t.label for t in app.text_input)
        assert any("Registros Detalhados" in s.value for s in app.subheader)


# ---------------------------------------------------------------------------
# 7. Flexibilidade e eficiência de uso
# ---------------------------------------------------------------------------
class TestH7Flexibilidade:
    def test_filtro_por_ra_recalcula_os_indicadores(self, app_interativo):
        total_geral = _numero_br(app_interativo.metric[0].value)

        app_interativo.multiselect[0].set_value(["Ceilândia"])
        app_interativo.run()

        total_filtrado = _numero_br(app_interativo.metric[0].value)
        assert 0 < total_filtrado < total_geral

    def test_usuario_pode_escolher_entre_varios_formatos(self, app):
        assert len(next(s for s in app.selectbox if s.label == "Tipo de gráfico").options) == 6
        assert len(next(s for s in app.selectbox if s.label == "Dados a analisar").options) == 4
        assert app.number_input[0].min == 3
        assert app.number_input[0].max == 30
        assert len(app.get("download_button")) == 3

    def test_camada_e_estilo_do_mapa_sao_configuraveis(self, app):
        assert app.radio[0].label == "Tipo de Camada"
        assert "Mapa de Calor (Heatmap 2D)" in app.radio[0].options


# ---------------------------------------------------------------------------
# 8. Design estético e minimalista
# ---------------------------------------------------------------------------
class TestH8Design:
    def test_interface_organizada_em_cinco_abas_e_quatro_kpis(self, app):
        assert len(app.tabs) == 5
        assert len(app.metric) == 4

    def test_graficos_secundarios_ficam_recolhidos(self, app):
        assert len(app.expander) == 1
        assert "Visão geral" in app.expander[0].label

    def test_conteudo_principal_comeca_pelos_indicadores(self, app):
        assert "Mapa da Segurança Pública - Distrito Federal" in app.title[0].value
        assert app.markdown[0].value.startswith("Visualização geoespacial")


# ---------------------------------------------------------------------------
# 9. Reconhecimento, diagnóstico e recuperação de erros
# ---------------------------------------------------------------------------
class TestH9RecuperacaoDeErros:
    def test_busca_sem_resultado_explica_o_que_aconteceu(self, app_interativo):
        busca = next(t for t in app_interativo.text_input if "Buscar" in t.label)
        busca.set_value("zzzzzzzz")
        app_interativo.run()

        assert any(
            "Nenhuma ocorrência encontrada" in i.value for i in app_interativo.info
        )
        assert not app_interativo.exception

    def test_modo_offline_orienta_como_subir_o_backend(self, app):
        textos = " ".join(i.value for i in app.sidebar.info) + " ".join(
            c.value for c in app.sidebar.caption
        )
        assert "Modo Direto Local" in textos
        assert "run.py api" in textos

    def test_salvar_relatorio_sem_backend_nao_quebra(self, app):
        assert any(
            "Salvar relatórios exige o backend" in c.value
            for c in app.caption
        )


# ---------------------------------------------------------------------------
# 10. Ajuda e documentação
# ---------------------------------------------------------------------------
class TestH10AjudaEDocumentacao:
    def test_aba_da_api_lista_endpoints_e_swagger(self, app):
        codigo = " ".join(c.value for c in app.code)
        assert "/api/heatmap" in codigo
        assert "/api/stats" in codigo
        assert "/api/auth/health" in codigo
        assert any(
            "Swagger" in m.value or "/docs" in m.value for m in app.markdown
        )

    def test_orientacoes_de_uso_do_mapa(self, app):
        textos = " ".join(c.value for c in app.caption)
        assert "Arraste para mover" in textos

    def test_documentacao_do_projeto_esta_no_repositorio(self):
        raiz = Path(__file__).resolve().parent.parent
        for arquivo in ("README.md", "SETUP_WINDOWS.md"):
            assert (raiz / arquivo).exists()
        readme = (raiz / "README.md").read_text(encoding="utf-8")
        assert "Swagger" in readme or "/docs" in readme
        assert "autenticação" in readme.lower() or "login" in readme.lower()
