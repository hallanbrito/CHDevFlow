"""Testes unitários rigorosos para o motor de grafo DAG (DAGEngine).

Verifica ordenação topológica (Kahn), detecção de ciclos, detecção de dependências
órfãs, determinação de elegibilidade e conformidade com o princípio Fail-Closed (RNF-02).
"""
from __future__ import annotations

import pytest

from ch_control_center.graph.dag_engine import (
    STATUS_BLOQUEADA_CICLO,
    STATUS_BLOQUEADA_DEP,
    STATUS_BLOQUEADA_ORFA,
    STATUS_CONCLUIDA,
    STATUS_ELEGIVEL,
    DAGEngine,
)


@pytest.fixture
def dag() -> DAGEngine:
    return DAGEngine()


def test_grafo_vazio(dag: DAGEngine) -> None:
    """Verifica comportamento com lista vazia de tarefas."""
    resultado = dag.construir_grafo([])
    assert resultado.total_tarefas == 0
    assert resultado.total_elegiveis == 0
    assert resultado.total_bloqueadas == 0
    assert resultado.total_concluidas == 0
    assert resultado.ciclos_detectados == []
    assert resultado.dependencias_desconhecidas == {}


def test_fluxo_linear_simples(dag: DAGEngine) -> None:
    """A -> B -> C: A é raiz elegível, B e C estão bloqueadas por dependência."""
    tarefas = [
        {"id": "A", "title": "Tarefa A", "stage": "BACKLOG", "dependencies": []},
        {"id": "B", "title": "Tarefa B", "stage": "BACKLOG", "dependencies": ["A"]},
        {"id": "C", "title": "Tarefa C", "stage": "BACKLOG", "dependencies": ["B"]},
    ]
    res = dag.construir_grafo(tarefas)

    assert res.total_tarefas == 3
    assert res.nos["A"].status_grafo == STATUS_ELEGIVEL
    assert res.nos["B"].status_grafo == STATUS_BLOQUEADA_DEP
    assert res.nos["C"].status_grafo == STATUS_BLOQUEADA_DEP
    assert "A" in res.nos["B"].motivo_bloqueio
    assert "B" in res.nos["C"].motivo_bloqueio
    assert res.total_elegiveis == 1
    assert res.total_bloqueadas == 2


def test_tarefa_concluida_desbloqueia_sucessora(dag: DAGEngine) -> None:
    """Se A está CONCLUIDA (DONE/PROD_OK), B (que depende de A) torna-se ELEGIVEL."""
    tarefas = [
        {"id": "A", "title": "Tarefa A", "stage": "DONE", "dependencies": []},
        {"id": "B", "title": "Tarefa B", "stage": "BACKLOG", "dependencies": ["A"]},
    ]
    res = dag.construir_grafo(tarefas)

    assert res.nos["A"].status_grafo == STATUS_CONCLUIDA
    assert res.nos["B"].status_grafo == STATUS_ELEGIVEL
    assert res.total_concluidas == 1
    assert res.total_elegiveis == 1
    assert res.total_bloqueadas == 0


def test_diamante_com_conclusoes_parciais(dag: DAGEngine) -> None:
    """Padrão diamante: A -> B, A -> C; B & C -> D.
    A concluída; B concluída; C pendente => D deve continuar bloqueada por C."""
    tarefas = [
        {"id": "A", "title": "A", "stage": "PROD_OK", "dependencies": []},
        {"id": "B", "title": "B", "stage": "DONE", "dependencies": ["A"]},
        {"id": "C", "title": "C", "stage": "IN_PROGRESS", "dependencies": ["A"]},
        {"id": "D", "title": "D", "stage": "BACKLOG", "dependencies": ["B", "C"]},
    ]
    res = dag.construir_grafo(tarefas)

    assert res.nos["A"].status_grafo == STATUS_CONCLUIDA
    assert res.nos["B"].status_grafo == STATUS_CONCLUIDA
    assert res.nos["C"].status_grafo == STATUS_ELEGIVEL
    assert res.nos["D"].status_grafo == STATUS_BLOQUEADA_DEP
    assert "C" in res.nos["D"].motivo_bloqueio


def test_deteccao_ciclo_simples_dois_nos(dag: DAGEngine) -> None:
    """A depende de B, B depende de A: ambos devem ser marcados como BLOQUEADA_CICLO."""
    tarefas = [
        {"id": "A", "title": "Tarefa A", "stage": "BACKLOG", "dependencies": ["B"]},
        {"id": "B", "title": "Tarefa B", "stage": "BACKLOG", "dependencies": ["A"]},
    ]
    res = dag.construir_grafo(tarefas)

    assert len(res.ciclos_detectados) >= 1
    assert res.nos["A"].status_grafo == STATUS_BLOQUEADA_CICLO
    assert res.nos["B"].status_grafo == STATUS_BLOQUEADA_CICLO
    assert "circular" in res.nos["A"].motivo_bloqueio.lower()
    assert res.total_bloqueadas == 2
    assert res.total_elegiveis == 0


def test_deteccao_auto_dependencia(dag: DAGEngine) -> None:
    """A depende de si mesma (auto-loop)."""
    tarefas = [
        {"id": "A", "title": "Auto Loop", "stage": "BACKLOG", "dependencies": ["A"]},
    ]
    res = dag.construir_grafo(tarefas)

    assert len(res.ciclos_detectados) >= 1
    assert res.nos["A"].status_grafo == STATUS_BLOQUEADA_CICLO


def test_deteccao_dependencia_orfa_ou_desconhecida(dag: DAGEngine) -> None:
    """A depende de X, mas X não existe no snapshot."""
    tarefas = [
        {"id": "A", "title": "Tarefa Órfã", "stage": "BACKLOG", "dependencies": ["X-INEXISTENTE"]},
    ]
    res = dag.construir_grafo(tarefas)

    assert "A" in res.dependencias_desconhecidas
    assert "X-INEXISTENTE" in res.dependencias_desconhecidas["A"]
    assert res.nos["A"].status_grafo == STATUS_BLOQUEADA_ORFA
    assert "inexistente" in res.nos["A"].motivo_bloqueio.lower()


def test_grafo_misto_isolamento_de_anomalias(dag: DAGEngine) -> None:
    """Um grafo que contém tarefas saudáveis e um ciclo isolado não deve corromper
    as tarefas saudáveis (princípio de isolamento)."""
    tarefas = [
        {"id": "OK-1", "title": "Saudável 1", "stage": "DONE", "dependencies": []},
        {"id": "OK-2", "title": "Saudável 2", "stage": "BACKLOG", "dependencies": ["OK-1"]},
        {"id": "CICLO-1", "title": "Ciclo 1", "stage": "BACKLOG", "dependencies": ["CICLO-2"]},
        {"id": "CICLO-2", "title": "Ciclo 2", "stage": "BACKLOG", "dependencies": ["CICLO-1"]},
        {"id": "ORFA-1", "title": "Órfã 1", "stage": "BACKLOG", "dependencies": ["NAO-EXISTE"]},
    ]
    res = dag.construir_grafo(tarefas)

    # Saudáveis
    assert res.nos["OK-1"].status_grafo == STATUS_CONCLUIDA
    assert res.nos["OK-2"].status_grafo == STATUS_ELEGIVEL

    # Anomalias
    assert res.nos["CICLO-1"].status_grafo == STATUS_BLOQUEADA_CICLO
    assert res.nos["CICLO-2"].status_grafo == STATUS_BLOQUEADA_CICLO
    assert res.nos["ORFA-1"].status_grafo == STATUS_BLOQUEADA_ORFA

    # Contagens
    assert res.total_tarefas == 5
    assert res.total_concluidas == 1
    assert res.total_elegiveis == 1
    assert res.total_bloqueadas == 3
