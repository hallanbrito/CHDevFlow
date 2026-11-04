"""Regressões do formato real observado no teste manual do PO em 22/10/2026.

Os dados são sintéticos; a estrutura reproduz os campos relatados pelo PO.
Nenhum teste consulta rede ou usa credenciais.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from ch_control_center.adapters.sentinela_adapter import SentinelaAdapterErro
from ch_control_center.config import MODO_LIVE_GITHUB
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
    assert "Dependências não informadas" in missao["motivo_bloqueio"]
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


def test_etapa_homologada_observada_e_preservada_com_dependencias_nao_informadas():
    item = item_nativo()
    item["etapa CH"] = "HOMOLOGADA"
    visao = MissionService().construir_visao_operacional_completa({"items": [item]})
    assert visao["missoes"][0]["status_grafo"] == "CONCLUIDA"
    assert visao["missoes"][0]["dependencies_informadas"] is False
    assert visao["stats"]["total_dados_insuficientes"] == 1
    assert visao["stats"]["total_elegiveis"] == 0


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
    assert resposta.text.count('class="node-id"') == 11
