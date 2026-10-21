"""Testes unitários para o ProjectService.

Testa isolamento de perfis multi-projeto (CHDevFlow vs HallanCraft) e políticas de segurança (RF-09).
"""
from __future__ import annotations

import pytest

from ch_control_center.config import PERFIL_CHDEVFLOW, PERFIL_HALLANCRAFT
from ch_control_center.services.project_service import ProjectService


@pytest.fixture
def service() -> ProjectService:
    return ProjectService()


def test_carregamento_perfis_padrao(service: ProjectService) -> None:
    """Verifica que os perfis canônicos são carregados do disco."""
    perfis = service.listar_perfis()
    chaves = [p["project_key"] for p in perfis]
    assert PERFIL_CHDEVFLOW in chaves
    assert PERFIL_HALLANCRAFT in chaves


def test_perfil_ativo_padrao(service: ProjectService) -> None:
    """Verifica que o perfil ativo padrão é o CHDevFlow."""
    ativo = service.obter_perfil_ativo()
    assert ativo["project_key"] == PERFIL_CHDEVFLOW
    assert "CHDevFlow" in ativo["display_name"]
    assert ativo["default_branch"] == "main"


def test_alternancia_perfil_para_hallancraft(service: ProjectService) -> None:
    """Alterna para o perfil HallanCraft e confere isolamento de caminhos."""
    perfil = service.alternar_perfil(PERFIL_HALLANCRAFT)
    assert perfil["project_key"] == PERFIL_HALLANCRAFT
    assert service.obter_perfil_ativo_key() == PERFIL_HALLANCRAFT
    assert "HallanCraft" in perfil["display_name"]

    # Verifica isolamento de mundos e saves de produção no HallanCraft (D04)
    policy = perfil.get("security_policy", {})
    proibidos = policy.get("prohibited_patterns", [])
    assert any("worlds" in p for p in proibidos)
    assert any("saves" in p for p in proibidos)


def test_ignora_perfil_invalido_sem_modificar_ativo(service: ProjectService) -> None:
    """Tentativa de alternar para perfil inexistente mantém o perfil atual inalterado (fail-closed)."""
    original = service.obter_perfil_ativo_key()
    service.alternar_perfil("perfil_inexistente_hacker")
    assert service.obter_perfil_ativo_key() == original
