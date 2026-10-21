#!/usr/bin/env bash
# ==============================================================================
# Script de Inicialização Manual do CHDevFlow Control Center (CC-01)
# Decisão D05: Execução manual pelo Product Owner sob demanda.
# RNF-01: Vinculado estritamente à interface loopback (127.0.0.1:8000).
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${WORKTREE_DIR}"

# Localiza ambiente virtual Python
if [[ -f "${WORKTREE_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${WORKTREE_DIR}/.venv/bin/python"
elif [[ -f "${WORKTREE_DIR}/../.venv/bin/python" ]]; then
    PYTHON_BIN="${WORKTREE_DIR}/../.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "❌ Erro: Interpretador Python não encontrado." >&2
    exit 1
fi

# Configura PYTHONPATH para resolução limpa dos pacotes locais
export PYTHONPATH="${WORKTREE_DIR}/apps/control-center/src:${WORKTREE_DIR}/apps/bootstrap/sentinela/src:${PYTHONPATH:-}"

echo "=================================================================="
echo " 🚀 Iniciando CHDevFlow Control Center (MVP v0.2 / Fatia CC-01)"
echo " • Interpretador: ${PYTHON_BIN}"
echo " • Diretório:     ${WORKTREE_DIR}"
echo " • Modo Inicial:  DEMO_OFFLINE (Seguro / R$ 0,00)"
echo " • URL de Acesso: http://127.0.0.1:8000"
echo "=================================================================="

exec "${PYTHON_BIN}" -m ch_control_center
