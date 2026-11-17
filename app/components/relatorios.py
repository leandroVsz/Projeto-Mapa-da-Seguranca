"""
Aba "Meus relatórios" (HU08 / Tela 3): lista os relatórios salvos do
usuário logado, permite reabrir (regenera o gráfico com dados atuais
usando a dimensão/tipo/Top N/filtros salvos), exportar CSV/PDF e excluir
(com confirmação). Reaproveita montar_dataframe/criar_figura de charts.py
e gerar_csv/gerar_pdf de chart_export.py, como pede o Passo 6.
"""

import streamlit as st

from app.auth_ui import is_logado
from app.components.chart_export import gerar_csv, gerar_pdf, nome_arquivo
from app.components.charts import DIMENSOES, criar_figura, montar_dataframe

_DIMENSAO_LABEL = {v: k for k, v in DIMENSOES.items()}


def render_meus_relatorios(client):
    """client: instância de ApiClient (necessária para listar/excluir)."""
    st.subheader("📁 Meus relatórios")

    if client is None or not client.is_online():
        st.info(
            "Esta tela exige o backend conectado (API + banco). "
            "No momento o app está no **Modo Direto Local**."
        )
        return

    if not is_logado():
        st.info("Entre na aba **👤 Conta & Acesso** para ver seus relatórios salvos.")
        return

    token = st.session_state.get("auth_token")
    resultado = client.listar_relatorios(token)
    if not resultado.get("ok"):
        st.error(resultado.get("erro", "Não foi possível carregar seus relatórios."))
        return

    relatorios = resultado.get("relatorios", [])
    if not relatorios:
        st.info("Você ainda não salvou nenhum relatório. Salve um na aba 📊 Gráficos & Tendências.")
        return

    confirmando = st.session_state.get("excluir_confirmando")

    for rel in relatorios:
        rid = rel["id"]
        dimensao_label = _DIMENSAO_LABEL.get(rel["dimensao"], rel["dimensao"])
        with st.expander(f"📄 {rel['titulo']}  ·  {dimensao_label}  ·  {rel['tipo_grafico']}"):
            filtros = rel.get("filtros") or {}
            st.caption(
                f"Top {rel['top_n']} · Salvo em {str(rel.get('criado_em', ''))[:10]} · "
                f"Filtros — regiões: {filtros.get('regioes') or 'todas'}; "
                f"eixos: {filtros.get('eixos') or 'todos'}; "
                f"naturezas: {filtros.get('naturezas') or 'todas'}; "
                f"anos: {filtros.get('anos') or 'todos'}"
            )

            stats_regen = client.get_stats(
                regioes=filtros.get("regioes") or None,
                naturezas=filtros.get("naturezas") or None,
                eixos=filtros.get("eixos") or None,
                anos=filtros.get("anos") or None,
            )
            df = montar_dataframe(stats_regen, dimensao_label, int(rel["top_n"]))

            if df.empty:
                st.warning(
                    "Sem dados para os filtros salvos neste relatório "
                    "(podem ter mudado desde o momento em que foi salvo)."
                )
            else:
                st.plotly_chart(
                    criar_figura(df, rel["tipo_grafico"], rel["titulo"]),
                    width="stretch",
                    key=f"chart_{rid}",
                )
                b1, b2 = st.columns(2)
                b1.download_button(
                    "⬇️ CSV",
                    data=gerar_csv(df),
                    file_name=nome_arquivo(rel["titulo"], rel["tipo_grafico"], "csv"),
                    mime="text/csv",
                    key=f"csv_{rid}",
                    width="stretch",
                )
                b2.download_button(
                    "⬇️ PDF",
                    data=gerar_pdf(df, rel["tipo_grafico"], rel["titulo"]),
                    file_name=nome_arquivo(rel["titulo"], rel["tipo_grafico"], "pdf"),
                    mime="application/pdf",
                    key=f"pdf_{rid}",
                    width="stretch",
                )

            st.markdown("")
            if confirmando == rid:
                st.warning(f'Excluir o relatório "{rel["titulo"]}" definitivamente?')
                c1, c2 = st.columns(2)
                if c1.button("✅ Sim, excluir", key=f"confirma_del_{rid}", width="stretch"):
                    r = client.excluir_relatorio(token, rid)
                    if r.get("ok"):
                        st.session_state.pop("excluir_confirmando", None)
                        st.success("Relatório excluído.")
                        st.rerun()
                    else:
                        st.error(r.get("erro", "Não foi possível excluir."))
                if c2.button("Cancelar", key=f"cancela_del_{rid}", width="stretch"):
                    st.session_state.pop("excluir_confirmando", None)
                    st.rerun()
            else:
                if st.button("🗑️ Excluir relatório", key=f"del_{rid}"):
                    st.session_state["excluir_confirmando"] = rid
                    st.rerun()
