"""Testes das rotas HTTP da aplicação FastAPI.

Verifica conformidade estrita com o modo somente leitura (CH-1), integridade de páginas HTML,
APIs de consulta JSON e cabeçalhos de segurança contra vulnerabilidades web (RNF-01).
"""
from __future__ import annotations

import pytest


def test_rota_healthcheck(client) -> None:
    """Verifica resposta e cabeçalhos da rota de integridade /health."""
    resp = client.get("/health")
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["status"] == "ok"
    assert dados["modo"] == "SOMENTE_LEITURA"
    assert dados["versao"] == "0.2.0"
    assert resp.headers.get("x-governanca-modo") == "SOMENTE_LEITURA"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_rota_dashboard_html(client) -> None:
    """Verifica renderização da página principal do Dashboard."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Control Center" in resp.text
    assert "Dashboard de Supervisão" in resp.text
    assert "Total de Fatias W" in resp.text
    assert "Modo Estudante" in resp.text


def test_rota_missoes_html_com_filtros(client) -> None:
    """Verifica renderização da página de missões e filtros."""
    resp = client.get("/missoes")
    assert resp.status_code == 200
    assert "Central de Missões e Fatias W" in resp.text
    assert "W-01" in resp.text

    # Com filtro de busca
    resp_filtro = client.get("/missoes?busca=Sentinela")
    assert resp_filtro.status_code == 200
    assert "Sentinela" in resp_filtro.text


def test_rota_grafo_html(client) -> None:
    """Verifica renderização da visualização do Grafo DAG."""
    resp = client.get("/grafo")
    assert resp.status_code == 200
    assert "Grafo Visual de Dependências" in resp.text
    assert "ALERTA CRÍTICO: Ciclo(s) de Dependência Circular" in resp.text
    assert "Linha de Frente" in resp.text


def test_rota_estudante_html(client) -> None:
    """Verifica renderização da página didática do Modo Estudante."""
    resp = client.get("/estudante")
    assert resp.status_code == 200
    assert "Modo Estudante Didático" in resp.text
    assert "Fail-Closed" in resp.text
    assert "Digest Criptográfico" in resp.text
    assert "As 5 Invariantes Canônicas" in resp.text


def test_api_detalhe_missao(client) -> None:
    """Verifica consulta de detalhes de missão via API JSON."""
    resp = client.get("/api/missoes/item-w01")
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["id"] == "item-w01"
    assert "Kanban" in dados["title"]

    resp_404 = client.get("/api/missoes/INEXISTENTE-999")
    assert resp_404.status_code == 404


def test_api_grafo_json(client) -> None:
    """Verifica dados estruturados do Grafo DAG via API."""
    resp = client.get("/api/grafo")
    assert resp.status_code == 200
    dados = resp.json()
    assert "total_tarefas" in dados
    assert "ciclos_detectados" in dados
    assert "dependencias_desconhecidas" in dados
    assert len(dados["ciclos_detectados"]) >= 1


def test_api_glossario_estudante(client) -> None:
    """Verifica catálogo completo de termos didáticos via API."""
    resp = client.get("/api/estudante/glossario")
    assert resp.status_code == 200
    termos = resp.json()
    assert isinstance(termos, list)
    assert len(termos) >= 7
    ids = [t["id"] for t in termos]
    assert "fail_closed" in ids
    assert "mission_digest" in ids


def test_alternar_modo_demo_via_post(client) -> None:
    """Verifica alternância de modo de demonstração via POST."""
    resp = client.post("/demo/alternar", data="modo=LIVE_GITHUB")
    assert resp.status_code == 303

    status_resp = client.get("/api/demo/status")
    assert status_resp.json()["modo_operacao"] == "LIVE_GITHUB"

    # Alterna de volta para demo
    client.post("/demo/alternar", data="modo=DEMO_OFFLINE")
    status_resp2 = client.get("/api/demo/status")
    assert status_resp2.json()["modo_operacao"] == "DEMO_OFFLINE"


def test_alternar_projeto_ativo_via_post(client) -> None:
    """Verifica alternância de perfil de projeto via POST."""
    resp = client.post("/projetos/alternar", data="project_key=hallancraft")
    assert resp.status_code == 303

    proj_resp = client.get("/api/projetos/ativo")
    assert proj_resp.json()["project_key"] == "hallancraft"


def test_ausencia_de_rotas_mutativas_executivas(client) -> None:
    """Garante que não existem endpoints que disparem robôs ou modifiquem o código."""
    for rota in ["/executar", "/api/dispatch", "/api/agentes/iniciar", "/admin/deploy"]:
        resp = client.post(rota)
        assert resp.status_code in (404, 405)
