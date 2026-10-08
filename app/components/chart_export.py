"""
Exportação de gráficos para CSV e PDF.

Recebe o DataFrame (colunas "Categoria" e "Ocorrências") gerado em charts.py
e devolve os bytes do arquivo, prontos para o st.download_button.
"""

import io
import re
import unicodedata

import matplotlib

matplotlib.use("Agg")  # backend sem janela, necessário para rodar em servidor
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402


def nome_arquivo(titulo: str, tipo: str, extensao: str) -> str:
    """Gera um nome de arquivo seguro: sem acentos, espaços ou símbolos."""
    base = f"{titulo}_{tipo}"
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return f"{base}.{extensao}"


def gerar_csv(df: pd.DataFrame) -> bytes:
    """CSV com ';' e UTF-8 com BOM, para abrir certo no Excel em português."""
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def _milhar(valor) -> str:
    """1234567 -> '1.234.567' (padrão brasileiro)."""
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def _desenhar_grafico(ax, df: pd.DataFrame, tipo: str, titulo: str):
    x = df["Categoria"].astype(str).tolist()
    y = df["Ocorrências"].tolist()

    if tipo == "Barras":
        ax.bar(x, y, color="#38bdf8")
        ax.tick_params(axis="x", rotation=45)
        plt.setp(ax.get_xticklabels(), ha="right")
    elif tipo == "Barras horizontais":
        ax.barh(x[::-1], y[::-1], color="#38bdf8")
    elif tipo == "Linha":
        ax.plot(x, y, marker="o", color="#10b981")
        ax.tick_params(axis="x", rotation=45)
        plt.setp(ax.get_xticklabels(), ha="right")
    elif tipo == "Área":
        posicoes = range(len(x))
        ax.fill_between(posicoes, y, alpha=0.4, color="#f59e0b")
        ax.plot(posicoes, y, color="#f59e0b")
        ax.set_xticks(list(posicoes))
        ax.set_xticklabels(x, rotation=45, ha="right")
    else:  # Pizza ou Rosca
        ax.pie(
            y,
            labels=x,
            autopct="%1.1f%%",
            startangle=90,
            wedgeprops={"width": 0.45} if tipo == "Rosca" else None,
        )
        ax.axis("equal")

    ax.set_title(titulo, fontsize=14, fontweight="bold")
    if tipo not in ("Pizza", "Rosca"):
        ax.grid(alpha=0.3)
        formatador = FuncFormatter(lambda valor, _: _milhar(valor))
        if tipo == "Barras horizontais":
            ax.set_xlabel("Ocorrências")
            ax.xaxis.set_major_formatter(formatador)
        else:
            ax.set_ylabel("Ocorrências")
            ax.yaxis.set_major_formatter(formatador)


def gerar_pdf(df: pd.DataFrame, tipo: str, titulo: str) -> bytes:
    """PDF de 2 páginas: (1) o gráfico, (2) a tabela com os dados."""
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        # Página 1: gráfico (A4 paisagem)
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        _desenhar_grafico(ax, df, tipo, titulo)
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Página 2: tabela de dados
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.axis("off")
        ax.set_title(f"Dados: {titulo}", fontsize=14, fontweight="bold")
        linhas = [[str(c), _milhar(v)] for c, v in zip(df["Categoria"], df["Ocorrências"])]
        tabela = ax.table(
            cellText=linhas,
            colLabels=["Categoria", "Ocorrências"],
            loc="upper center",
            cellLoc="left",
        )
        tabela.auto_set_font_size(False)
        tabela.set_fontsize(10)
        tabela.scale(1, 1.4)
        pdf.savefig(fig)
        plt.close(fig)

        info = pdf.infodict()
        info["Title"] = titulo
        info["Creator"] = "Mapa da Segurança DF"
    return buffer.getvalue()
