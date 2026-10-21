"""Testes unitários para o MissionService.

Testa orquestração de leituras, alternância de modos demo/live e filtragem de missões.
"""
from __future__ import annotations

import pytest

from ch_control_center.config import MODO_DEMO_OFFLINE, MODO_LIVE_GITHUB
from ch_control_center.services.mission_service import MissionService


@pytest.fixture
def service() -> MissionService:
    return MissionService()


def test_modo_padrao_demo_offline(service: MissionService) -> None:
    """Verifica que o modo inicial é seguro (DEMO_OFFLINE)."""
    assert service.obter_modo_operacao() == MODO_DEMO_OFFLINE


def test_alternancia_de_modo_operacao(service: MissionService) -> None:
    """Verifica a alternância controlada entre LIVE_GITHUB e DEMO_OFFLINE."""
    modo = service.alternar_modo_operacao(MODO_LIVE_GITHUB)
    assert modo == MODO_LIVE_GITHUB
    assert service.obter_modo_operacao() == MODO_LIVE_GITHUB

    modo_demo = service.alternar_modo_operacao(MODO_DEMO_OFFLINE)
    assert modo_demo == MODO_DEMO_OFFLINE
    assert service.obter_modo_operacao() == MODO_DEMO_OFFLINE


def test_processamento_tarefas_brutas_contem_itens(service: MissionService) -> None:
    """Verifica que o processamento normaliza as tarefas da fixture."""
    tarefas = service.processar_tarefas_brutas()
    assert len(tarefas) >= 10
    ids = [t["id"] for t in tarefas]
    assert "item-w01" in ids
    assert "item-boot01" in ids
    assert "item-ciclo-a" in ids


def test_listar_missoes_com_filtros(service: MissionService) -> None:
    """Testa busca textual e filtros por status e esteira."""
    todas = service.listar_missoes()
    assert len(todas) >= 10

    # Filtro por esteira AGY
    missoes_agy = service.listar_missoes(filtro_esteira="AGY")
    assert len(missoes_agy) > 0
    assert all(m["esteira"].upper() == "AGY" for m in missoes_agy)

    # Filtro por status BLOQUEADA_CICLO
    ciclos = service.listar_missoes(filtro_status="BLOQUEADA_CICLO")
    assert len(ciclos) == 2  # DEMO-CICLO-A e DEMO-CICLO-B
    assert all(m["status_grafo"] == "BLOQUEADA_CICLO" for m in ciclos)

    # Busca textual
    busca_sentinela = service.listar_missoes(termo_busca="Sentinela")
    assert len(busca_sentinela) >= 1
    assert any("Sentinela" in m["title"] for m in busca_sentinela)


def test_obter_missao_por_id_existente_e_inexistente(service: MissionService) -> None:
    """Verifica busca de detalhe por ID."""
    m_w01 = service.obter_missao_por_id("item-w01")
    assert m_w01 is not None
    assert m_w01["id"] == "item-w01"
    assert "Kanban" in m_w01["title"]

    # Também localiza pelo atalho W-01 ou número da issue (2)
    assert service.obter_missao_por_id("W-01") is not None
    assert service.obter_missao_por_id("2") is not None

    m_invalido = service.obter_missao_por_id("NAO-EXISTE-999")
    assert m_invalido is None


def test_obter_resumo_estatisticas(service: MissionService) -> None:
    """Verifica cálculo dos contadores para os cards do dashboard."""
    stats = service.obter_resumo_estatisticas()
    assert stats["total_tarefas"] >= 10
    assert stats["total_concluidas"] >= 1
    assert stats["total_ciclos"] == 1  # 1 ciclo detectado (com 2 tarefas)
    assert stats["total_orfas"] == 1    # 1 tarefa com dependência órfã
    assert stats["modo_operacao"] == MODO_DEMO_OFFLINE
