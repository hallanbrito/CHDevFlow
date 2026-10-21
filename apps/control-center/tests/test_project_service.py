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


def test_alternancia_perfil_para_hallancraft_mantem_chdevflow_aud03(service: ProjectService) -> None:
    """AUD-03: Garante que o perfil HallanCraft permanece preparatório e não substitui os dados do CHDevFlow.

    Impede que a interface exiba 'HallanCraft' enquanto os dados observados pertencem ao CHDevFlow.
    """
    perfil = service.alternar_perfil(PERFIL_HALLANCRAFT)
    # Na CC-01, o perfil ativo permanece CHDevFlow para evitar divergência de dados
    assert perfil["project_key"] == PERFIL_CHDEVFLOW
    assert service.obter_perfil_ativo_key() == PERFIL_CHDEVFLOW

    # Verifica que o catálogo de perfis define HallanCraft como preparatório com proteção estrita
    perfis = service.listar_perfis()
    hc = next(p for p in perfis if p["project_key"] == PERFIL_HALLANCRAFT)
    assert "PREPARATÓRIO — SEM TROCA DE DADOS" in hc["display_name"]

    # Verifica isolamento inegociável de mundos, saves, .env e produção no HallanCraft (D04 e AUD-03)
    policy = hc.get("security_policy", {})
    proibidos = policy.get("prohibited_patterns", [])
    assert any("worlds" in p for p in proibidos)
    assert any("saves" in p for p in proibidos)
    assert any(".env" in p for p in proibidos)
    assert any("server.properties" in p for p in proibidos)


def test_coerencia_estrita_entre_perfil_e_dados_aud03(service: ProjectService) -> None:
    """AUD-03: Comprova que perfil ativo e fonte de dados nunca divergem."""
    from ch_control_center.services.mission_service import MissionService
    mission_svc = MissionService()

    perfil_ativo = service.obter_perfil_ativo()
    missoes = mission_svc.listar_missoes()

    # Todos os dados observados devem corresponder ao repositório do perfil ativo
    for m in missoes:
        assert m["repository"] == perfil_ativo["repository"]


def test_ignora_perfil_invalido_sem_modificar_ativo(service: ProjectService) -> None:
    """Tentativa de alternar para perfil inexistente mantém o perfil atual inalterado (fail-closed)."""
    original = service.obter_perfil_ativo_key()
    service.alternar_perfil("perfil_inexistente_hacker")
    assert service.obter_perfil_ativo_key() == original
