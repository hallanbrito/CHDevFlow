"""Testes de regressão e garantia de qualidade da missão CC-QUALITY-01 (F0 a F5).

Abrange:
- F0/F1: Divergência de contadores resolvida, causas diagnósticas discriminadas,
         teste contra a falsa classificação 'tudo é cadastro'.
- F2: Cache em memória compartilhado, TTL, coalescência concorrente, tratamento STALE e ERROR.
- F3: UX minimalista do DAG, renderização dos cartões, modal acessível e busca na raia 4.
- F4: Endpoints de sincronização /api/sincronizacao e /api/sincronizar, CSRF e segurança.
- F5: Preservação das invariantes de segurança do DAG e ausência de execução de agentes.
"""
from __future__ import annotations

from copy import deepcopy
import json
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from jinja2 import Environment, FileSystemLoader

from ch_control_center.adapters.sentinela_adapter import SentinelFacade, SentinelaAdapterErro
from ch_control_center.config import (
    DIRETORIO_TEMPLATES,
    MODO_DEMO_OFFLINE,
    MODO_LIVE_GITHUB,
)
from ch_control_center.graph.dag_engine import (
    CAUSA_AGUARDANDO_PREDECESSORA,
    CAUSA_ANOMALIA_CICLO,
    CAUSA_ANOMALIA_ORFA,
    CAUSA_CADASTRO_INCOMPLETO,
    CAUSA_CONSULTA_INDISPONIVEL,
    CAUSA_HOMOLOGACAO_NAO_VERIFICADA,
    DAGEngine,
    STATUS_BLOQUEADA_DADOS,
    STATUS_BLOQUEADA_DEP,
    STATUS_ELEGIVEL,
)
from ch_control_center.security import obter_csrf_token
from ch_control_center.services.mission_service import EstadoSincronizacao, MissionService
from ch_sentinela.github_reader import LeitorGitHub, LeitorGitHubErro


def gerar_item_sintetico(
    numero: int,
    etapa: str = "BACKLOG",
    esteira: str = "AGY",
    autonomia: str = "CH-1",
    dep_state: str = "VERIFIED_EMPTY",
    dep_refs: list[dict[str, Any]] | None = None,
    diagnostic: str | None = None,
) -> dict[str, Any]:
    """Gera item estruturado reproduzindo a resposta nativa de gh project item-list."""
    item: dict[str, Any] = {
        "id": f"PVTI_sintetico_{numero}",
        "title": f"Missão de teste #{numero}",
        "labels": ["ch:workflow"],
        "status": "Todo",
        "repository": "hallanbrito/CHDevFlow",
        "content": {
            "type": "Issue",
            "number": numero,
            "title": f"Missão de teste #{numero}",
            "repository": "hallanbrito/CHDevFlow",
            "url": f"https://github.com/hallanbrito/CHDevFlow/issues/{numero}",
        },
    }
    if etapa != "NAO_INFORMADA":
        item["etapa CH"] = etapa
    if esteira != "NAO_INFORMADA":
        item["esteira"] = esteira
    if autonomia != "NAO_INFORMADA":
        item["autonomia CH"] = autonomia

    item["dependency_observation"] = {
        "issue_ref": f"hallanbrito/CHDevFlow#{numero}",
        "dependency_state": dep_state,
        "dependency_refs": dep_refs or [],
        "observed_at": "2026-11-06T19:45:00Z",
        "source": f"github_rest:/repos/hallanbrito/CHDevFlow/issues/{numero}/dependencies/blocked_by",
        "diagnostic": diagnostic,
    }
    return item


# ==============================================================================
# F0 / F1: CLASSIFICAÇÃO VERDADEIRA E COERÊNCIA DE CONTADORES
# ==============================================================================


def test_f0_f1_divergencia_contadores_resolvida():
    """Garante que stats.total_dados_insuficientes é idêntico à contagem do grafo."""
    # Item com cadastro 100% completo, mas HOMOLOGADA sem prova de homologação humana
    item2 = gerar_item_sintetico(2, etapa="HOMOLOGADA", esteira="ChatGPT", autonomia="CH-2")
    # Item com cadastro incompleto
    item5 = gerar_item_sintetico(5, etapa="NAO_INFORMADA", esteira="NAO_INFORMADA", autonomia="NAO_INFORMADA")
    # Item elegível
    item6 = gerar_item_sintetico(6, etapa="BACKLOG", esteira="ChatGPT", autonomia="CH-1")

    service = MissionService()
    visao = service.construir_visao_operacional_completa(
        {"items": [item2, item5, item6]}, origem=MODO_LIVE_GITHUB
    )

    stats = visao["stats"]
    grafo = visao["grafo"]

    # Ambos os itens 2 e 5 estão bloqueados por dados insuficientes (homologação não verificada e campos)
    assert stats["total_dados_insuficientes"] == 2
    assert grafo.total_dados_insuficientes == 2
    assert len([n for n in grafo.nos.values() if n.status_grafo == STATUS_BLOQUEADA_DADOS]) == 2
    assert len([n for n in grafo.nos.values() if n.pendencias_dados]) == 2
    assert stats["total_elegiveis"] == 1


def test_f1_discriminacao_de_causas_refuta_tudo_e_cadastro():
    """Verifica que #2 é classificada exclusivamente como Homologação não verificada."""
    # Issue #2: Cadastro 100% completo, HOMOLOGADA sem prova humana
    item2 = gerar_item_sintetico(2, etapa="HOMOLOGADA", esteira="ChatGPT", autonomia="CH-2")
    # Issue #5: 3 campos ausentes
    item5 = gerar_item_sintetico(5, etapa="NAO_INFORMADA", esteira="NAO_INFORMADA", autonomia="NAO_INFORMADA")
    # Issue #8: INTEGRADA + autonomia ausente (múltiplas causas)
    item8 = gerar_item_sintetico(8, etapa="INTEGRADA", esteira="ChatGPT", autonomia="NAO_INFORMADA")

    service = MissionService()
    visao = service.construir_visao_operacional_completa(
        {"items": [item2, item5, item8]}, origem=MODO_LIVE_GITHUB
    )

    missoes_por_num = {m["number"]: m for m in visao["missoes"]}

    # Issue #2: NÃO é cadastro incompleto!
    m2 = missoes_por_num[2]
    assert CAUSA_HOMOLOGACAO_NAO_VERIFICADA in m2["causas_diagnosticas"]
    assert CAUSA_CADASTRO_INCOMPLETO not in m2["causas_diagnosticas"]
    assert m2["causas_diagnosticas"] == [CAUSA_HOMOLOGACAO_NAO_VERIFICADA]

    # Issue #5: É cadastro incompleto puro
    m5 = missoes_por_num[5]
    assert CAUSA_CADASTRO_INCOMPLETO in m5["causas_diagnosticas"]
    assert CAUSA_HOMOLOGACAO_NAO_VERIFICADA not in m5["causas_diagnosticas"]

    # Issue #8: Múltiplas causas concorrentes
    m8 = missoes_por_num[8]
    assert CAUSA_CADASTRO_INCOMPLETO in m8["causas_diagnosticas"]
    assert CAUSA_HOMOLOGACAO_NAO_VERIFICADA in m8["causas_diagnosticas"]

    # Contagem discriminada por causa no resumo de estatísticas
    contagem = visao["stats"]["contagem_por_causa"]
    assert contagem[CAUSA_HOMOLOGACAO_NAO_VERIFICADA] == 2  # #2 e #8
    assert contagem[CAUSA_CADASTRO_INCOMPLETO] == 2        # #5 e #8
    assert contagem[CAUSA_CONSULTA_INDISPONIVEL] == 0


def test_f1_causa_consulta_indisponivel_em_falha_de_leitura():
    """Verifica que respostas UNKNOWN ou falhas parciais geram CAUSA_CONSULTA_INDISPONIVEL."""
    item = gerar_item_sintetico(
        10,
        etapa="BACKLOG",
        esteira="AGY",
        autonomia="CH-1",
        dep_state="UNKNOWN",
        diagnostic="Leitura interrompida pelo orçamento temporal ou por falhas consecutivas.",
    )
    service = MissionService()
    visao = service.construir_visao_operacional_completa({"items": [item]}, origem=MODO_LIVE_GITHUB)
    missao = visao["missoes"][0]
    assert CAUSA_CONSULTA_INDISPONIVEL in missao["causas_diagnosticas"]
    assert CAUSA_CADASTRO_INCOMPLETO not in missao["causas_diagnosticas"]


def test_f1_matriz_trinta_issues_sintetica_reproduz_diagnostico_real():
    """Reproduz a composição exata das 30 missões observadas no teste ao vivo do PO."""
    itens = []
    # 3 Elegíveis: #6, #58, #59
    itens.append(gerar_item_sintetico(6, etapa="BACKLOG", esteira="ChatGPT", autonomia="CH-1"))
    itens.append(gerar_item_sintetico(58, etapa="BACKLOG", esteira="AGY", autonomia="CH-1"))
    itens.append(gerar_item_sintetico(59, etapa="BACKLOG", esteira="Codex", autonomia="CH-1"))

    # 2 Homologadas com cadastro completo: #2, #7
    itens.append(gerar_item_sintetico(2, etapa="HOMOLOGADA", esteira="ChatGPT", autonomia="CH-2"))
    itens.append(gerar_item_sintetico(7, etapa="HOMOLOGADA", esteira="Hallan", autonomia="CH-0"))

    # 7 Cadastro Incompleto puro: #5, #10, #24, #32, #40, #54, #56
    for num in (5, 54, 56):
        itens.append(gerar_item_sintetico(num, etapa="NAO_INFORMADA", esteira="NAO_INFORMADA", autonomia="NAO_INFORMADA"))
    for num in (32, 40):
        itens.append(gerar_item_sintetico(num, etapa="NAO_INFORMADA", esteira="AGY", autonomia="NAO_INFORMADA"))
    itens.append(gerar_item_sintetico(10, etapa="BACKLOG", esteira="Hallan", autonomia="NAO_INFORMADA"))
    itens.append(gerar_item_sintetico(24, etapa="AGUARDANDO_PO", esteira="ChatGPT", autonomia="NAO_INFORMADA"))

    # 18 Múltiplas causas (Homologada/Integrada + Autonomia ausente): #8, 12, 13, 14, 16, 18, 19, 21, 27, 28, 29, 33..38, 41
    for num in (12, 13, 14, 16, 28, 29):
        itens.append(gerar_item_sintetico(num, etapa="HOMOLOGADA", esteira="AGY", autonomia="NAO_INFORMADA"))
    for num in (8, 18, 19, 21, 27, 33, 34, 35, 36, 37, 38, 41):
        itens.append(gerar_item_sintetico(num, etapa="INTEGRADA", esteira="AGY", autonomia="NAO_INFORMADA"))

    service = MissionService()
    visao = service.construir_visao_operacional_completa({"items": itens}, origem=MODO_LIVE_GITHUB)
    stats = visao["stats"]

    assert stats["total_tarefas"] == 30
    assert stats["total_elegiveis"] == 3
    assert stats["total_bloqueadas"] == 27
    assert stats["total_concluidas"] == 0
    assert stats["total_dados_insuficientes"] == 27  # Coerente!

    contagem = stats["contagem_por_causa"]
    assert contagem[CAUSA_HOMOLOGACAO_NAO_VERIFICADA] == 20  # 2 puros + 18 múltiplos
    assert contagem[CAUSA_CADASTRO_INCOMPLETO] == 25         # 7 puros + 18 múltiplos


# ==============================================================================
# F2: DESEMPENHO LIVE_GITHUB, CACHE EM MEMÓRIA E COALESCÊNCIA
# ==============================================================================


def test_f2_cache_em_memoria_reutiliza_snapshot_nas_rotas():
    """Garante que a navegação pelas rotas executa exatamente 1 leitura ao vivo dentro do TTL."""
    chamadas_ao_vivo = 0

    def mock_obter_snapshot():
        nonlocal chamadas_ao_vivo
        chamadas_ao_vivo += 1
        item = gerar_item_sintetico(1, etapa="BACKLOG", esteira="AGY", autonomia="CH-1")
        return {"items": [item], "totalCount": 1}

    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = mock_obter_snapshot
    facade.sanitizar.side_effect = lambda s: s

    service = MissionService(facade=facade, ttl_cache_segundos=60.0)
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    # 1. Dashboard
    ctx1 = service.obter_contexto_dashboard()
    assert chamadas_ao_vivo == 1

    # 2. Grafo
    grafo = service.obter_grafo_dag()
    assert chamadas_ao_vivo == 1

    # 3. Lista de missões
    missoes = service.listar_missoes()
    assert chamadas_ao_vivo == 1

    # 4. Detalhes de missão
    missao = service.obter_missao_por_id("PVTI_sintetico_1")
    assert chamadas_ao_vivo == 1
    assert missao is not None

    # 5. Resumo de estatísticas
    stats = service.obter_resumo_estatisticas()
    assert chamadas_ao_vivo == 1

    # Forçar atualização manual invalida o cache e chama a fonte novamente
    service.obter_contexto_dashboard(forcar_atualizacao=True)
    assert chamadas_ao_vivo == 2


def test_f2_coalescencia_concorrente_impede_leituras_duplicadas():
    """Garante que múltiplas threads simultâneas executam apenas 1 consulta via lock."""
    chamadas = 0

    def consulta_lenta():
        nonlocal chamadas
        chamadas += 1
        time.sleep(0.05)
        item = gerar_item_sintetico(1, etapa="BACKLOG", esteira="AGY", autonomia="CH-1")
        return {"items": [item], "totalCount": 1}

    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = consulta_lenta
    facade.sanitizar.side_effect = lambda s: s

    service = MissionService(facade=facade, ttl_cache_segundos=60.0)
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    threads = []
    resultados = [None] * 5

    def worker(idx):
        resultados[idx] = service.obter_contexto_dashboard()

    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Exatamente 1 chamada executada para todas as 5 threads concorrentes
    assert chamadas == 1
    for r in resultados:
        assert r is not None
        assert r["stats"]["total_tarefas"] == 1


def test_f2_falha_apos_sucesso_gera_estado_stale_sem_mascarar():
    """Se o GitHub falhar após um snapshot prévio, retorna STALE e preserva os dados com aviso."""
    item = gerar_item_sintetico(1, etapa="BACKLOG", esteira="AGY", autonomia="CH-1")
    snapshot_ok = {"items": [item], "totalCount": 1}

    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = [
        snapshot_ok,
        SentinelaAdapterErro("Timeout simulado de rede no GitHub"),
    ]
    facade.sanitizar.side_effect = lambda s: s

    service = MissionService(facade=facade, ttl_cache_segundos=0.0)  # TTL zero para forçar refresh
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    # 1. Primeira consulta com sucesso
    v1 = service.obter_contexto_dashboard()
    estado1 = service.obter_estado_sincronizacao()
    assert estado1.status == "OK"
    assert v1["stats"]["total_tarefas"] == 1

    # 2. Segunda consulta com falha de rede
    v2 = service.obter_contexto_dashboard()
    estado2 = service.obter_estado_sincronizacao()
    assert estado2.status == "STALE"
    assert "Timeout simulado" in estado2.diagnostic
    # Não mascara como 0 itens nem cai para DEMO!
    assert v2["stats"]["total_tarefas"] == 1
    assert service.obter_modo_operacao() == MODO_LIVE_GITHUB


def test_f2_falha_inicial_sem_cache_gera_estado_error():
    """Se a primeira consulta falhar sem snapshot prévio, marca ERROR e lança exceção."""
    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = SentinelaAdapterErro("Falha de conexão inicial")
    facade.sanitizar.side_effect = lambda s: s

    service = MissionService(facade=facade)
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    with pytest.raises(SentinelaAdapterErro):
        service.obter_contexto_dashboard()

    estado = service.obter_estado_sincronizacao()
    assert estado.status == "ERROR"
    assert "Falha de conexão inicial" in estado.diagnostic


# ==============================================================================
# F3: UX MINIMALISTA DO DAG E ACESSIBILIDADE
# ==============================================================================


def test_f3_template_grafo_cartoes_minimos_e_modal_acessivel():
    """Garante que os cartões não contêm URLs REST/PVTI e o modal possui estrutura acessível."""
    item = gerar_item_sintetico(42, etapa="HOMOLOGADA", esteira="ChatGPT", autonomia="CH-2")
    service = MissionService()
    visao = service.construir_visao_operacional_completa({"items": [item]}, origem=MODO_LIVE_GITHUB)

    ambiente = Environment(loader=FileSystemLoader(str(DIRETORIO_TEMPLATES)), autoescape=True)
    html = ambiente.get_template("graph.html").render(
        grafo=visao["grafo"], modo_operacao="LIVE_GITHUB", csrf_token="token_teste"
    )

    # 1. Cartão mínimo: #Issue visível, atributos acessíveis
    assert '<span class="node-id" title="ID interno: PVTI_sintetico_42">#42</span>' in html
    assert 'class="graph-node-card clickable-card' in html
    assert 'role="button"' in html
    assert 'tabindex="0"' in html
    assert 'onclick="abrirModalDetalhesMissao(this)"' in html

    # 2. Modal acessível presente no DOM
    assert '<div id="modal-detalhes-missao" class="modal-overlay" role="dialog" aria-modal="true"' in html
    assert 'onclick="fecharModalDetalhesMissao()"' in html
    assert 'modal-node-title' in html
    assert 'modal-node-issue' in html

    # 3. Raia 4 recolhível e pesquisável (recolhida por padrão na R1)
    assert "4. Dados insuficientes — análise pendente (1)" in html
    assert 'id="filtro-dados-insuficientes"' in html
    assert 'id="secao-dados-insuficientes"' in html
    assert "<details" in html
    assert "<details open" not in html


# ==============================================================================
# F4: ROTAS DE SINCRONIZAÇÃO E SEGURANÇA
# ==============================================================================


def test_f4_api_sincronizacao_status(client):
    """Verifica endpoint GET /api/sincronizacao."""
    resp = client.get("/api/sincronizacao")
    assert resp.status_code == 200
    dados = resp.json()
    assert "status" in dados
    assert "source" in dados
    assert dados["source"] == MODO_DEMO_OFFLINE


def test_f4_api_sincronizar_manual_com_csrf(client):
    """Verifica acionamento manual de sincronização com CSRF válido."""
    token = obter_csrf_token()
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/grafo",
        "X-CSRF-Token": token,
    }
    resp = client.post("/api/sincronizar", headers=headers)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["status"] == "OK"
    assert "stats" in dados


def test_f4_api_sincronizar_rejeita_sem_csrf(client):
    """Rejeita requisição POST sem CSRF token por segurança."""
    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/grafo",
    }
    resp = client.post("/api/sincronizar", headers=headers)
    assert resp.status_code == 403


def test_f4_demo_offline_nao_faz_chamadas_externas():
    """No modo DEMO_OFFLINE, obter_visao_operacional não consulta a Sentinela ao vivo."""
    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_demo.return_value = {"items": [], "totalCount": 0}
    facade.sanitizar.side_effect = lambda s: s

    service = MissionService(facade=facade)
    assert service.obter_modo_operacao() == MODO_DEMO_OFFLINE
    service.obter_contexto_dashboard()

    facade.obter_snapshot_ao_vivo.assert_not_called()
    facade.obter_snapshot_demo.assert_called_once()


# ==============================================================================
# R1 / CH-AUDIT: REGRESSÕES REAIS IDENTIFICADAS NA REVISÃO INDEPENDENTE
# ==============================================================================

def test_r1_f3_card_minimalista_nao_mostra_diagnostico_interno():
    """Não confundir o JSON oculto do modal com texto visível no cartão DAG."""
    from pathlib import Path
    source = (Path(DIRETORIO_TEMPLATES) / "graph.html").read_text(encoding="utf-8")
    macro = source.split("{% macro render_node_card(", 1)[1].split("{% endmacro %}", 1)[0]
    for nome_tecnico in ("no.dependency_source", "no.dependency_observed_at", "no.motivo_bloqueio"):
        assert nome_tecnico not in macro
    assert '<details open' not in source
    assert 'id="secao-dados-insuficientes"' in source
    assert 'render_node_card(no' in source


def test_r1_f4_post_stale_nao_retorna_falso_ok(client):
    """Falha após snapshot válido devolve 503/STALE, não 200/OK."""
    from ch_control_center.dependencies import get_mission_service

    service = get_mission_service()
    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = [
        {"items": [gerar_item_sintetico(42)], "totalCount": 1},
        SentinelaAdapterErro("Falha temporária simulada"),
    ]
    facade.sanitizar.side_effect = lambda texto: texto
    service.facade = facade
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)
    service.obter_contexto_dashboard()

    headers = {
        "Host": "127.0.0.1:8000",
        "Origin": "http://127.0.0.1:8000",
        "Referer": "http://127.0.0.1:8000/grafo",
        "X-CSRF-Token": obter_csrf_token(),
    }
    resposta = client.post("/api/sincronizar", headers=headers)
    assert resposta.status_code == 503
    assert resposta.json()["status"] == "STALE"
    assert resposta.json()["estado"]["status"] == "STALE"
    assert service.obter_estado_sincronizacao().last_success_at is not None


def test_r1_f4_parcial_nao_afirma_sucesso_completo():
    """Project lido, mas relações UNKNOWN impedem status global OK."""
    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.return_value = {
        "items": [gerar_item_sintetico(43, dep_state="UNKNOWN")],
        "totalCount": 1,
    }
    facade.sanitizar.side_effect = lambda texto: texto
    service = MissionService(facade=facade)
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    resultado = service.sincronizar_agora()
    assert resultado["status"] == "PARTIAL"
    assert resultado["estado"]["error_code"] == "DEPENDENCIES_PARTIAL"
    assert resultado["estado"]["last_success_at"] is None
    assert resultado["stats"]["total_dados_insuficientes"] == 1


def test_r1_f2_coalesce_dois_refreshes_forcados_em_uma_leitura():
    """Duas abas que pedem refresh no mesmo instante não duplicam 30 comandos gh."""
    from concurrent.futures import ThreadPoolExecutor

    chamadas = 0
    barreira = threading.Barrier(2)

    def mock_github():
        nonlocal chamadas
        chamadas += 1
        time.sleep(0.15)
        return {"items": [gerar_item_sintetico(45)], "totalCount": 1}

    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = mock_github
    facade.sanitizar.side_effect = lambda texto: texto
    service = MissionService(facade=facade)
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    def job():
        barreira.wait(timeout=2)
        return service.sincronizar_agora()

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(job)
        b = executor.submit(job)
        assert a.result(timeout=5)["status"] == "OK"
        assert b.result(timeout=5)["status"] == "OK"
    assert chamadas == 1


def test_r1_f2_status_api_responde_enquanto_github_esta_lento(client):
    """Async event loop não pode bloquear durante sync de uma rota distinta."""
    import asyncio
    from ch_control_center.dependencies import get_mission_service

    service = get_mission_service()
    iniciado = threading.Event()
    liberar = threading.Event()

    def github_lento():
        iniciado.set()
        if not liberar.wait(timeout=3):
            raise SentinelaAdapterErro("Timeout simulado")
        return {"items": [gerar_item_sintetico(49)], "totalCount": 1}

    facade = MagicMock(spec=SentinelFacade)
    facade.obter_snapshot_ao_vivo.side_effect = github_lento
    facade.sanitizar.side_effect = lambda texto: texto
    service.facade = facade
    service.alternar_modo_operacao(MODO_LIVE_GITHUB)

    async def verificar():
        primeira = asyncio.create_task(client._async_request("GET", "/api/grafo"))
        try:
            assert await asyncio.to_thread(iniciado.wait, 2)
            status = await asyncio.wait_for(
                client._async_request("GET", "/api/sincronizacao"),
                timeout=1.5,
            )
            assert status.status_code == 200
            assert status.json()["status"] == "SYNCING"
        finally:
            liberar.set()
        resultado = await asyncio.wait_for(primeira, timeout=3)
        assert resultado.status_code == 200

    asyncio.run(verificar())


def test_r1_f4_js_atualiza_dom_sem_reload_integral():
    """Polling deve refletir o novo snapshot na UI e manter contexto do usuário."""
    from pathlib import Path
    js = (Path(DIRETORIO_TEMPLATES).parent / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "window.location.reload()" not in js
    assert "async function atualizarConteudoVisivel()" in js
    assert "await atualizarConteudoVisivel()" in js
    assert "window.scrollTo(scrollX, scrollY)" in js
    assert 'filtroNovo.dispatchEvent(new Event("input"' in js
    assert "visibilitychange" in js
