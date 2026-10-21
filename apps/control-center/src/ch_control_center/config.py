"""Configurações e constantes centrais do CHDevFlow Control Center (CC-01).

Define parâmetros de inicialização, diretórios de templates, ativos estáticos,
fixtures para o modo de demonstração offline e restrições de segurança de rede local.
"""
from __future__ import annotations

import os
from pathlib import Path

# Restrição irrevogável de segurança de rede: somente localhost (RNF-01)
HOST_PADRAO: str = "127.0.0.1"
PORTA_PADRAO: int = 8000

# Modos de operação suportados
MODO_DEMO_OFFLINE: str = "DEMO_OFFLINE"
MODO_LIVE_GITHUB: str = "LIVE_GITHUB"
MODOS_OPERACAO_PERMITIDOS: tuple[str, ...] = (
    MODO_DEMO_OFFLINE,
    MODO_LIVE_GITHUB,
)

# Perfis de projetos autorizados
PERFIL_CHDEVFLOW: str = "chdevflow"
PERFIL_HALLANCRAFT: str = "hallancraft"
PERFIS_PERMITIDOS: tuple[str, ...] = (
    PERFIL_CHDEVFLOW,
    PERFIL_HALLANCRAFT,
)

# Diretórios base do pacote
DIRETORIO_PACOTE: Path = Path(__file__).resolve().parent
DIRETORIO_MODULO_APP: Path = DIRETORIO_PACOTE.parent.parent
DIRETORIO_TEMPLATES: Path = DIRETORIO_PACOTE / "templates"
DIRETORIO_STATIC: Path = DIRETORIO_PACOTE / "static"
DIRETORIO_FIXTURES: Path = DIRETORIO_MODULO_APP / "fixtures"

# Dados locais
DIRETORIO_DADOS_PADRAO: Path = Path(os.getenv("CH_CC_DATA_DIR", ".ch_control_center"))


def obter_host_configurado() -> str:
    """Retorna o host configurado, garantindo estritamente que não seja 0.0.0.0."""
    host = os.getenv("CH_CC_HOST", HOST_PADRAO)
    if host in ("0.0.0.0", "::", "all"):
        # Fail-closed de segurança: recusa exposição externa na rede
        return HOST_PADRAO
    return host


def obter_porta_configurada() -> int:
    """Retorna a porta configurada para o servidor web local."""
    try:
        return int(os.getenv("CH_CC_PORT", str(PORTA_PADRAO)))
    except ValueError:
        return PORTA_PADRAO


def obter_modo_operacao() -> str:
    """Retorna o modo de operação ativo (DEMO_OFFLINE ou LIVE_GITHUB)."""
    modo = os.getenv("CH_CC_MODE", MODO_DEMO_OFFLINE).upper()
    if modo not in MODOS_OPERACAO_PERMITIDOS:
        return MODO_DEMO_OFFLINE
    return modo


def obter_perfil_ativo() -> str:
    """Retorna o perfil de projeto ativo no painel."""
    perfil = os.getenv("CH_CC_PROJECT_PROFILE", PERFIL_CHDEVFLOW).lower()
    if perfil not in PERFIS_PERMITIDOS:
        return PERFIL_CHDEVFLOW
    return perfil


def obter_diretorio_dados_seguro() -> Path:
    """Garante que o diretório local de dados exista com permissão 0o700."""
    diretorio = Path(os.getenv("CH_CC_DATA_DIR", DIRETORIO_DADOS_PADRAO))
    diretorio.mkdir(mode=0o700, parents=True, exist_ok=True)
    return diretorio
