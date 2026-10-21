"""Testes de conformidade de segurança e configuração de rede do servidor.

Verifica restrição irrestrita a localhost (127.0.0.1) e salvaguardas da Decisão D05.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from ch_control_center.config import (
    HOST_PADRAO,
    PORTA_PADRAO,
    obter_host_configurado,
    obter_porta_configurada,
)


def test_host_padrao_e_localhost() -> None:
    """Garante que o host padrão é 127.0.0.1."""
    with patch.dict(os.environ, {}, clear=True):
        assert obter_host_configurado() == HOST_PADRAO
        assert HOST_PADRAO == "127.0.0.1"


def test_recusa_exposicao_em_zero_zero_zero_zero() -> None:
    """Fail-closed: recusa 0.0.0.0 ou coringas que exporiam o servidor na rede física."""
    perigosos = ["0.0.0.0", "::", "all"]
    for host_perigoso in perigosos:
        with patch.dict(os.environ, {"CH_CC_HOST": host_perigoso}):
            host_resolvido = obter_host_configurado()
            assert host_resolvido == "127.0.0.1", f"Falha para {host_perigoso}: permitiu {host_resolvido}"


def test_porta_padrao_e_customizada() -> None:
    """Verifica porta padrão e validação de porta numérica válida."""
    with patch.dict(os.environ, {}, clear=True):
        assert obter_porta_configurada() == PORTA_PADRAO
        assert PORTA_PADRAO == 8000

    with patch.dict(os.environ, {"CH_CC_PORT": "8080"}):
        assert obter_porta_configurada() == 8080

    with patch.dict(os.environ, {"CH_CC_PORT": "invalido"}):
        assert obter_porta_configurada() == PORTA_PADRAO
