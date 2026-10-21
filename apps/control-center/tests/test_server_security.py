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


def test_recusa_estrita_enderecos_externos_aud01() -> None:
    """AUD-01: Garante que qualquer endereço diferente de 127.0.0.1 é forçado para 127.0.0.1."""
    enderecos_proibidos = [
        "192.168.1.20",
        "10.0.0.5",
        "8.8.8.8",
        "172.16.0.1",
        "localhost_malformado",
        "localhost:8000",
        "",
        "   ",
        "0.0.0.0",
        "::1",
    ]
    for endereco in enderecos_proibidos:
        with patch.dict(os.environ, {"CH_CC_HOST": endereco}):
            assert obter_host_configurado() == "127.0.0.1", f"Falha de isolamento para '{endereco}'"


def test_porta_padrao_e_customizada() -> None:
    """Verifica porta padrão e validação de porta numérica válida no intervalo 1–65535."""
    with patch.dict(os.environ, {}, clear=True):
        assert obter_porta_configurada() == PORTA_PADRAO
        assert PORTA_PADRAO == 8000

    with patch.dict(os.environ, {"CH_CC_PORT": "8080"}):
        assert obter_porta_configurada() == 8080

    with patch.dict(os.environ, {"CH_CC_PORT": "1"}):
        assert obter_porta_configurada() == 1

    with patch.dict(os.environ, {"CH_CC_PORT": "65535"}):
        assert obter_porta_configurada() == 65535

    # Casos inválidos (fora do intervalo 1-65535 ou não numéricos)
    invalidas = ["0", "-1", "65536", "70000", "invalido", "", "porta"]
    for porta_invalida in invalidas:
        with patch.dict(os.environ, {"CH_CC_PORT": porta_invalida}):
            assert obter_porta_configurada() == PORTA_PADRAO
