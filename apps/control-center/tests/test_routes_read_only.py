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


def test_cabecalho_csp_presente_e_estrito_aud02(client) -> None:
    """AUD-02: Comprova que a política Content-Security-Policy (CSP) está ativa e estrita."""
    resp = client.get("/")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert csp != "", "Cabeçalho Content-Security-Policy ausente"
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp


def test_alternar_modo_demo_via_post(client) -> None:
    """Verifica alternância de modo de demonstração via POST com origem local válida (AUD-02)."""
    headers_locais = {
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/missoes",
    }
    resp = client.post("/demo/alternar", data="modo=LIVE_GITHUB", headers=headers_locais)
    assert resp.status_code == 303
    assert resp.headers.get("location") == "http://127.0.0.1:8000/missoes" or resp.headers.get("location") == "/missoes"

    status_resp = client.get("/api/demo/status")
    assert status_resp.json()["modo_operacao"] == "LIVE_GITHUB"

    # Alterna de volta para demo
    client.post("/demo/alternar", data="modo=DEMO_OFFLINE", headers=headers_locais)
    status_resp2 = client.get("/api/demo/status")
    assert status_resp2.json()["modo_operacao"] == "DEMO_OFFLINE"


def test_bloqueio_post_com_origin_externo_aud02(client) -> None:
    """AUD-02: Rejeita POST originado de domínio externo (403 Forbidden)."""
    headers_maliciosos = {"Origin": "https://attacker.site"}
    resp = client.post("/demo/alternar", data="modo=LIVE_GITHUB", headers=headers_maliciosos)
    assert resp.status_code == 403


def test_bloqueio_post_com_referer_externo_aud02(client) -> None:
    """AUD-02: Rejeita POST cujo Referer aponta para domínio externo (403 Forbidden)."""
    headers_maliciosos = {"Referer": "https://phishing.site/fake-page"}
    resp = client.post("/demo/alternar", data="modo=LIVE_GITHUB", headers=headers_maliciosos)
    assert resp.status_code == 403


def test_bloqueio_post_sem_origem_nem_csrf_aud02(client) -> None:
    """AUD-02: Rejeita POST sem nenhum cabeçalho de origem ou token CSRF (403 Forbidden)."""
    resp = client.post("/demo/alternar", data="modo=LIVE_GITHUB")
    assert resp.status_code == 403


def test_redirecionamento_seguro_e_sanitizado_aud02(client) -> None:
    """AUD-02: Valida redirecionamento local e sanitização contra open-redirect."""
    headers_local = {"Origin": "http://127.0.0.1:8000", "Referer": "http://127.0.0.1:8000/grafo"}
    resp_valido = client.post("/demo/alternar", data="modo=LIVE_GITHUB", headers=headers_local)
    assert resp_valido.status_code == 303
    assert "/grafo" in resp_valido.headers.get("location", "")

    # Se referer for rota desconhecida, sanitiza seguramente para '/'
    headers_desconhecido = {"Origin": "http://127.0.0.1:8000", "Referer": "http://127.0.0.1:8000/rota_inexistente_hacker"}
    resp_sanitizado = client.post("/demo/alternar", data="modo=DEMO_OFFLINE", headers=headers_desconhecido)
    assert resp_sanitizado.status_code == 303
    assert resp_sanitizado.headers.get("location") == "/"


def test_alternar_projeto_ativo_via_post_aud03(client) -> None:
    """AUD-03: Alternância para HallanCraft preserva CHDevFlow para evitar divergência de dados."""
    headers_local = {"Origin": "http://127.0.0.1:8000", "Referer": "http://127.0.0.1:8000/"}
    resp = client.post("/projetos/alternar", data="project_key=hallancraft", headers=headers_local)
    assert resp.status_code == 303

    proj_resp = client.get("/api/projetos/ativo")
    # Perfil ativo permanece CHDevFlow na CC-01
    assert proj_resp.json()["project_key"] == "chdevflow"


def test_snapshot_consistente_contador_chamadas_aud05(client) -> None:
    """AUD-05: Garante exatamente 1 leitura de snapshot por operação composta do dashboard."""
    from ch_control_center.dependencies import get_mission_service

    svc = get_mission_service()
    antes = svc.contador_leituras_snapshot

    resp = client.get("/")
    assert resp.status_code == 200

    depois = svc.contador_leituras_snapshot
    assert depois - antes == 1, f"Esperado exatamente 1 leitura de snapshot, ocorreram {depois - antes}"


def test_ausencia_de_rotas_mutativas_executivas(client) -> None:
    """Garante que não existem endpoints que disparem robôs ou modifiquem o código."""
    headers_local = {"Origin": "http://127.0.0.1:8000", "Referer": "http://127.0.0.1:8000/"}
    for rota in ["/executar", "/api/dispatch", "/api/agentes/iniciar", "/admin/deploy"]:
        resp = client.post(rota, headers=headers_local)
        assert resp.status_code in (404, 405)
