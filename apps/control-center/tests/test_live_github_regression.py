"""Regressões do formato real observado no teste manual do PO em 22/10/2026.

Os dados são sintéticos; a estrutura reproduz os campos relatados pelo PO.
Nenhum teste consulta rede ou usa credenciais.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

import pytest
from jinja2 import Environment, FileSystemLoader

from ch_control_center.adapters.sentinela_adapter import SentinelaAdapterErro
from ch_control_center.adapters.sentinela_adapter import SentinelFacade
from ch_sentinela.github_reader import LeitorGitHub
from ch_control_center.config import MODO_LIVE_GITHUB
from ch_control_center.config import DIRETORIO_TEMPLATES
from ch_control_center.dependencies import get_mission_service
from ch_control_center.services.mission_service import MissionService


def item_nativo(numero=1):
    """Representa a saída nativa de gh project item-list, sem dependencies."""
    return {
        "id": f"PVTI_sintetico_{numero}",
        "title": f"Missão de regressão {numero}",
        "labels": ["ch:workflow", "ch:agy"],
        "etapa CH": "PRONTA",
        "autonomia CH": "CH-2",
        "esteira": "AGY",
        "status": "Todo",
        "repository": "hallanbrito/CHDevFlow",
        "content": {
            "type": "Issue", "number": numero, "body": "Texto sintético.",
            "title": f"Missão de regressão {numero}",
            "repository": "hallanbrito/CHDevFlow",
            "url": f"https://github.com/hallanbrito/CHDevFlow/issues/{numero}",
        },
    }


def snapshot_nativo():
    return {"totalCount": 17, "items": [item_nativo(n) for n in range(1, 18)]}


def test_dezessete_itens_nativos_nao_sao_descartados_nem_inventam_dependencias():
    """O caso 17 recebidos/0 reconhecidos deve virar 17 visíveis, sem elegibilidade falsa."""
    snapshot = snapshot_nativo()
    original = deepcopy(snapshot)
    visao = MissionService().construir_visao_operacional_completa(snapshot, MODO_LIVE_GITHUB)
    assert len(visao["missoes"]) == 17
    assert visao["stats"]["total_recebidos"] == 17
    assert visao["stats"]["total_ignorados"] == 0
    assert visao["stats"]["total_elegiveis"] == 0
    assert visao["stats"]["total_bloqueadas"] == 17
    missao = visao["missoes"][0]
    assert missao["stage"] == "PRONTA"
    assert missao["autonomia"] == "CH-2"
    assert missao["dependencies_informadas"] is False
    assert missao["status_grafo"] == "BLOQUEADA_DADOS"
    assert "Dependências desconhecidas" in missao["motivo_bloqueio"]
    assert visao["grafo"].arestas == []
    assert visao["grafo"].ciclos_detectados == []
    assert visao["grafo"].dependencias_desconhecidas == {}
    assert snapshot == original


@pytest.mark.parametrize("labels", [["ch:workflow"], [{"name": "ch:workflow"}]])
def test_etiquetas_nativas_em_string_ou_objeto(labels):
    item = item_nativo()
    item["labels"] = labels
    assert len(MissionService().normalizar_itens_snapshot({"items": [item]})) == 1


def test_nao_amplia_filtro_para_etiqueta_parecida_outro_repo_ou_draft():
    itens = [item_nativo(n) for n in range(1, 5)]
    itens[0]["labels"] = ["outro-ch:workflow-invalido"]
    itens[1]["content"]["repository"] = "outra/organizacao"
    itens[2]["content"]["type"] = "DraftIssue"
    itens[3]["labels"] = []
    itens[3]["dependencies"] = []  # Dependências não substituem a etiqueta canônica.
    assert MissionService().normalizar_itens_snapshot({"items": itens}) == []


def test_campos_ausentes_nao_inferem_etapa_esteira_autonomia_ou_conclusao():
    item = item_nativo()
    for campo in ("etapa CH", "esteira", "autonomia CH"):
        del item[campo]
    item["status"] = "Done"
    item["dependencies"] = []
    visao = MissionService().construir_visao_operacional_completa({"items": [item]})
    missao = visao["missoes"][0]
    assert (missao["stage"], missao["esteira"], missao["autonomia"]) == ("NAO_INFORMADA",) * 3
    assert missao["status_grafo"] == "BLOQUEADA_DADOS"
    assert visao["stats"]["total_concluidas"] == 0


@pytest.mark.parametrize("deps", [None, "#1", [None], [""]])
def test_dependencias_malformadas_nao_viram_raiz_elegivel(deps):
    item = item_nativo()
    item["dependencies"] = deps
    visao = MissionService().construir_visao_operacional_completa({"items": [item]})
    assert visao["missoes"][0]["status_grafo"] == "BLOQUEADA_DADOS"


def test_lista_vazia_explicita_permite_raiz_e_dependente_de_dados_insuficientes_bloqueia():
    a, b, c = [item_nativo(n) for n in range(1, 4)]
    b["dependencies"] = [a["id"]]
    c["dependencies"] = []
    visao = MissionService().construir_visao_operacional_completa({"items": [a, b, c]})
    estados = [m["status_grafo"] for m in visao["missoes"]]
    assert estados == ["BLOQUEADA_DADOS", "BLOQUEADA_POR_DEPENDENCIA", "ELEGIVEL"]


def test_etapa_homologada_sem_prova_humana_permanece_bloqueada():
    item = item_nativo()
    item["etapa CH"] = "HOMOLOGADA"
    visao = MissionService().construir_visao_operacional_completa({"items": [item]})
    assert visao["missoes"][0]["status_grafo"] == "BLOQUEADA_DADOS"
    assert "Homologação humana" in visao["missoes"][0]["motivo_bloqueio"]
    assert visao["missoes"][0]["dependencies_informadas"] is False
    assert visao["stats"]["total_dados_insuficientes"] == 1
    assert visao["stats"]["total_elegiveis"] == 0


def test_leitura_nativa_resolve_issue_para_item_sem_liberar_etapa_integrada():
    a, b, externa = [item_nativo(n) for n in (1, 2, 3)]
    a["etapa CH"] = "INTEGRADA"
    def dep(repo: str, numero: int, estado: str = "closed") -> dict:
        return {"id": numero + 100, "node_id": f"I_{numero}", "number": numero,
                "repository_url": f"https://api.github.com/repos/{repo}",
                "html_url": f"https://github.com/{repo}/issues/{numero}", "state": estado}
    def resposta(args: list[str]) -> str:
        if "item-list" in args:
            return json.dumps({"items": [a, b, externa], "totalCount": 3})
        numero = int(args[-1].split("/issues/")[1].split("/")[0])
        paginas = {1: [[]], 2: [[dep("hallanbrito/CHDevFlow", 1)]],
                   3: [[dep("outro/repo", 99)]]}
        return json.dumps(paginas[numero])
    facade = SentinelFacade(leitor=LeitorGitHub(executor_customizado=resposta))
    snapshot = facade.obter_snapshot_ao_vivo()
    visao = MissionService(facade=facade).construir_visao_operacional_completa(snapshot, MODO_LIVE_GITHUB)
    m_a, m_b, m_externa = visao["missoes"]
    assert m_a["dependency_state"] == "VERIFIED_EMPTY"
    assert m_a["status_grafo"] == "BLOQUEADA_DADOS"
    assert m_b["dependency_refs"][0]["issue_ref"] == "hallanbrito/CHDevFlow#1"
    assert m_b["dependencies"] == [a["id"]]
    assert m_b["status_grafo"] == "BLOQUEADA_POR_DEPENDENCIA"
    assert m_externa["dependencies"] == ["outro/repo#99"]
    assert m_externa["status_grafo"] == "BLOQUEADA_ORFA"
    assert m_b["dependency_observed_at"] and m_b["dependency_source"].startswith("github_rest:")


def test_falha_parcial_da_api_nativa_e_dado_bruto_nao_liberam_missao():
    a, b = item_nativo(1), item_nativo(2)
    b["dependencies"] = []  # Campo bruto não substitui prova da API nativa.
    def resposta(args: list[str]) -> str:
        if "item-list" in args:
            return json.dumps({"items": [a, b], "totalCount": 2})
        if "/issues/1/" in args[-1]:
            return "[[]]"
        raise RuntimeError("HTTP 403: ghp_1234567890abcdefghijklmnopqrstuvwxyz")
    facade = SentinelFacade(leitor=LeitorGitHub(executor_customizado=resposta))
    snapshot = facade.obter_snapshot_ao_vivo()
    visao = MissionService(facade=facade).construir_visao_operacional_completa(snapshot, MODO_LIVE_GITHUB)
    assert visao["missoes"][0]["status_grafo"] == "ELEGIVEL"
    assert visao["missoes"][1]["dependency_state"] == "UNKNOWN"
    assert visao["missoes"][1]["status_grafo"] == "BLOQUEADA_DADOS"
    assert "ghp_1234567890" not in str(visao)


def test_json_nativo_invalido_fica_invalid_e_bloqueado():
    item = item_nativo(1)
    def resposta(args: list[str]) -> str:
        return json.dumps({"items": [item], "totalCount": 1}) if "item-list" in args else "{json quebrado"
    facade = SentinelFacade(leitor=LeitorGitHub(executor_customizado=resposta))
    visao = MissionService(facade=facade).construir_visao_operacional_completa(facade.obter_snapshot_ao_vivo(), MODO_LIVE_GITHUB)
    assert visao["missoes"][0]["dependency_state"] == "INVALID"
    assert visao["missoes"][0]["status_grafo"] == "BLOQUEADA_DADOS"


def test_multiplos_timeouts_interrompem_consultas_restantes():
    itens = [item_nativo(n) for n in range(1, 5)]
    chamadas_api = []
    def resposta(args: list[str]) -> str:
        if "item-list" in args:
            return json.dumps({"items": itens, "totalCount": len(itens)})
        chamadas_api.append(args[-1])
        raise TimeoutError("timeout simulado")
    facade = SentinelFacade(leitor=LeitorGitHub(executor_customizado=resposta))
    visao = MissionService(facade=facade).construir_visao_operacional_completa(facade.obter_snapshot_ao_vivo(), MODO_LIVE_GITHUB)
    assert len(chamadas_api) == 2
    assert [m["dependency_state"] for m in visao["missoes"]] == ["UNKNOWN"] * 4
    assert visao["stats"]["total_elegiveis"] == 0
    assert "interrompida" in visao["missoes"][2]["dependency_diagnostic"]


def test_resposta_apos_prazo_global_nao_e_aceita(monkeypatch):
    import ch_control_center.adapters.sentinela_adapter as modulo_adapter
    instante = [0.0]
    monkeypatch.setattr(modulo_adapter.time, "monotonic", lambda: instante[0])
    itens = [item_nativo(1), item_nativo(2)]
    chamadas_api = []
    def resposta(args: list[str]) -> str:
        if "item-list" in args:
            return json.dumps({"items": itens, "totalCount": 2})
        chamadas_api.append(args[-1])
        instante[0] = 31.0
        return "[[]]"
    facade = SentinelFacade(leitor=LeitorGitHub(executor_customizado=resposta))
    visao = MissionService(facade=facade).construir_visao_operacional_completa(facade.obter_snapshot_ao_vivo(), MODO_LIVE_GITHUB)
    assert len(chamadas_api) == 1
    assert [m["dependency_state"] for m in visao["missoes"]] == ["UNKNOWN", "UNKNOWN"]
    assert visao["stats"]["total_elegiveis"] == 0


def test_ids_duplicados_do_project_bloqueiam_grafo_inteiro():
    a, b = item_nativo(1), item_nativo(2)
    b["id"] = a["id"]
    with pytest.raises(SentinelaAdapterErro, match="duplicado"):
        MissionService().construir_visao_operacional_completa({"items": [a, b]}, MODO_LIVE_GITHUB)


def test_dashboard_separa_etapa_visual_de_homologacao_verificada():
    item = item_nativo(1)
    item["etapa CH"] = "HOMOLOGADA"
    item["dependencies"] = []
    visao = MissionService().construir_visao_operacional_completa({"items": [item]}, "DEMO_OFFLINE")
    assert visao["stats"]["total_etapas_conclusao_observadas"] == 1
    assert visao["stats"]["total_concluidas"] == 0
    ambiente = Environment(loader=FileSystemLoader(str(DIRETORIO_TEMPLATES)), autoescape=True)
    ambiente.globals["csrf_token"] = "fixture"
    html = ambiente.get_template("dashboard.html").render(stats=visao["stats"], missoes=visao["missoes"], modo_operacao="DEMO_OFFLINE")
    assert re.search(r"Homologações verificadas.*?stat-value[^>]*>0<", html, re.S)
    assert re.search(r"Etapas visuais de conclusão.*?stat-value[^>]*>1<", html, re.S)
    assert "não comprovam homologação" in html


def test_r3_templates_mostram_issue_ou_fallback_e_dados_insuficientes():
    com_issue = item_nativo(42)
    sem_issue = item_nativo(43)
    sem_issue["content"]["number"] = None
    sem_issue["content"]["url"] = "#"
    visao = MissionService().construir_visao_operacional_completa(
        {"items": [com_issue, sem_issue]}, "DEMO_OFFLINE",
    )
    ambiente = Environment(loader=FileSystemLoader(str(DIRETORIO_TEMPLATES)), autoescape=True)
    dashboard = ambiente.get_template("dashboard.html").render(
        stats=visao["stats"], missoes=visao["missoes"], erro_leitura=None,
    )
    missoes = ambiente.get_template("missions.html").render(
        missoes=visao["missoes"], modo_operacao="DEMO_OFFLINE",
        filtro_busca="", filtro_status="TODOS", filtro_esteira="TODAS",
    )
    grafo = ambiente.get_template("graph.html").render(grafo=visao["grafo"])

    for html in (dashboard, missoes):
        assert '<strong title="ID interno: PVTI_sintetico_42">#42</strong>' in html
        assert '<strong title="ID interno: PVTI_sintetico_43">PVTI_sintetico_43</strong>' in html
        assert re.search(r'<span class="badge-status badge-bloqueada">Dados insuficientes</span>', html)
    assert '/missoes?detalhe=PVTI_sintetico_42' in dashboard
    assert '<strong>ID interno:</strong> <code>PVTI_sintetico_42</code>' in missoes
    assert '<span class="node-id" title="ID interno: PVTI_sintetico_42">#42</span>' in grafo
    assert '<span class="node-id" title="ID interno: PVTI_sintetico_43">PVTI_sintetico_43</span>' in grafo
    assert "4. Dados insuficientes — análise pendente" in grafo
    # R1 de UX supera a presença de rodapé técnico na face: campos completos ficam no modal.
    assert "node-footer" not in grafo
    assert "Dependências: UNKNOWN • Origem: fixture_offline • Observado: não informado" not in grafo
    assert 'id="secao-dados-insuficientes"' in grafo


def test_r3_alertas_do_grafo_mostram_issue_e_preservam_id_tecnico():
    a, b, orfa = [item_nativo(n) for n in (10, 11, 12)]
    a["dependencies"] = [b["id"]]
    b["dependencies"] = [a["id"]]
    orfa["dependencies"] = ["outro/repo#99"]
    visao = MissionService().construir_visao_operacional_completa(
        {"items": [a, b, orfa]}, "DEMO_OFFLINE",
    )
    ambiente = Environment(loader=FileSystemLoader(str(DIRETORIO_TEMPLATES)), autoescape=True)
    grafo = ambiente.get_template("graph.html").render(grafo=visao["grafo"])
    assert '<span title="ID interno: PVTI_sintetico_10">#10</span>' in grafo
    assert '<span title="ID interno: PVTI_sintetico_11">#11</span>' in grafo
    assert '<strong title="ID interno: PVTI_sintetico_12">#12</strong> depende de:' in grafo
    assert "outro/repo#99" in grafo


def configurar_live(monkeypatch, snapshot):
    servico = get_mission_service()
    servico.alternar_modo_operacao(MODO_LIVE_GITHUB)
    monkeypatch.setattr(servico.facade, "obter_snapshot_ao_vivo", lambda: snapshot)
    return servico


def test_rotas_live_renderizam_missoes_reais_e_ausencia_de_dados(client, monkeypatch):
    servico = configurar_live(monkeypatch, snapshot_nativo())
    for rota in ("/", "/missoes", "/grafo"):
        resposta = client.get(rota)
        assert resposta.status_code == 200
        assert "Missão de regressão 1" in resposta.text
        assert "Dados insuficientes" in resposta.text
    assert "Nenhuma (Raiz)" not in client.get("/missoes").text
    filtrada = client.get("/missoes?status=BLOQUEADA_DADOS&esteira=AGY&busca=regress%C3%A3o")
    assert "Missões Encontradas (17)" in filtrada.text
    assert servico.obter_modo_operacao() == MODO_LIVE_GITHUB


def test_dashboard_falha_visivel_sanitizada_nao_finge_projeto_vazio(client, monkeypatch):
    servico = get_mission_service()
    servico.alternar_modo_operacao(MODO_LIVE_GITHUB)
    segredo = "ghp_" + "A" * 36

    def falhar():
        raise SentinelaAdapterErro(f"<script>alert(1)</script> token={segredo}")

    monkeypatch.setattr(servico.facade, "obter_snapshot_ao_vivo", falhar)
    resposta = client.get("/")
    assert resposta.status_code == 503
    assert "Falha na leitura do projeto" in resposta.text
    assert segredo not in resposta.text
    assert "<script>alert(1)</script>" not in resposta.text
    assert "&lt;script&gt;" in resposta.text
    assert 'class="stat-value"' not in resposta.text
    assert servico.obter_modo_operacao() == MODO_LIVE_GITHUB


def test_projeto_valido_vazio_nao_e_falha_de_leitura(client, monkeypatch):
    configurar_live(monkeypatch, {"items": [], "totalCount": 0})
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert "Falha na leitura do projeto" not in resposta.text
    assert "Nenhuma missão reconhecida" in resposta.text


def test_grafo_demo_renderiza_todos_os_onze_cartoes_inclusive_anomalias(client):
    resposta = client.get("/grafo")
    assert resposta.text.count('class="node-id" title=') == 11
