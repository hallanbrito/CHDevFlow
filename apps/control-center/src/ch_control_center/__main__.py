"""Ponto de entrada de execução do servidor local (CLI entrypoint).

Executa via:
    python -m ch_control_center

Respeita rigorosamente a Decisão D05 (inicialização manual pelo PO, sem daemons,
sem polling contínuo de rede) e a restrição RNF-01 (somente 127.0.0.1).
"""
from __future__ import annotations

import sys
import uvicorn

from ch_control_center.config import (
    HOST_PADRAO,
    PORTA_PADRAO,
    obter_host_configurado,
    obter_modo_operacao,
    obter_porta_configurada,
)


def main() -> None:
    """Inicia o servidor web local FastAPI na interface de loopback."""
    host = obter_host_configurado()
    porta = obter_porta_configurada()
    modo = obter_modo_operacao()

    # Salvaguarda Fail-Closed AUD-01: somente 127.0.0.1 é permitido
    if host != HOST_PADRAO:
        print(f"⚠️ ALERTA DE SEGURANÇA: Host '{host}' não permitido. Forçando {HOST_PADRAO}.", file=sys.stderr)
        host = HOST_PADRAO

    print("=" * 68)
    print(" 🚀 CHDevFlow Control Center — MVP v0.2 (Fatia CC-01)")
    print("=" * 68)
    print(f" • Endereço Local:      http://{host}:{porta}")
    print(f" • Modo de Operação:    {modo}")
    print(" • Política de Acesso:  SOMENTE LOCAL (127.0.0.1 / Loopback)")
    print(" • Permissões:          ESTRITAMENTE SOMENTE LEITURA (CH-1)")
    print(" • Invariantes C.H.:    D01 (Custo R$ 0,00) | D05 (Manual) | D06 (Fail-Closed)")
    print(" • Product Owner:       Hallan")
    print("=" * 68)
    print(" Pressione Ctrl+C para encerrar o servidor a qualquer momento.\n")

    uvicorn.run(
        "ch_control_center.app:app",
        host=host,
        port=porta,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
