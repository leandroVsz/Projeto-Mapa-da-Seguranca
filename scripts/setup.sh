#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================================"
echo "  CONFIGURAÇÃO AUTOMÁTICA - MAPA DA SEGURANÇA DF"
echo "  Ambiente 100% Python (Linux / macOS)"
echo "========================================================"
echo ""

# 1. Verificar Python
if ! command -v python3 &>/dev/null; then
    echo "[ERRO] python3 não foi encontrado. Instale o Python 3.10+."
    exit 1
fi

echo "[OK] Python detectado: $(python3 --version)"

# 2. Criar e configurar venv
cd "$ROOT_DIR"
if [ ! -d "venv" ] || [ ! -f "venv/bin/pip" ]; then
    echo "[*] Criando ambiente virtual Python (venv)..."
    rm -rf venv
    if python3 -m venv venv 2>/dev/null; then
        echo "[OK] Ambiente virtual criado com sucesso."
    else
        echo "[*] Criando venv com --without-pip e obtendo pip..."
        python3 -m venv --without-pip venv
        curl -sS https://bootstrap.pypa.io/get-pip.py | ./venv/bin/python3
        echo "[OK] Pip configurado com sucesso no venv."
    fi
else
    echo "[INFO] Ambiente virtual 'venv' já existe."
fi

echo "[*] Ativando venv e instalando dependências..."
source venv/bin/activate
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
echo "[OK] Dependências instaladas com sucesso."

# 3. Gerar dataset se necessário
if [ ! -f "data/ocorrencias_df.csv" ]; then
    echo "[*] Gerando dados de demonstração..."
    python3 -c "from api.services.data_ingestion import gerar_dados_amostra; gerar_dados_amostra()"
fi

echo ""
echo "========================================================"
echo "  CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!"
echo "========================================================"
echo "Para iniciar:"
echo "  ./run.sh (ou python3 run.py)"
echo "========================================================"
