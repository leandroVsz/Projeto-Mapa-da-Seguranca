#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ] || [ ! -f "venv/bin/pip" ]; then
    echo "[*] Ambiente virtual não encontrado ou incompleto. Executando setup inicial..."
    ./scripts/setup.sh
fi

source venv/bin/activate

MODO="${1:-todos}"
./venv/bin/python3 run.py "$MODO"
