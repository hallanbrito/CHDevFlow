"""Serviço de gerenciamento e leitura de missões (MissionService).

Consome dados do GitHub Project #2 via SentinelFacade, alterna entre
modo ao vivo e demonstração offline (RF-06/CC-01) e processa dependências via DAGEngine.
"""
from __future__ import annotations

from typing import Any

from ch_control_center.adapters.sentinela_adapter import SentinelFacade, SentinelaAdapterErro
from ch_control_center.config import (
    DIRETORIO_FIXTURES,
    MODO_DEMO_OFFLINE,
    MODO_LIVE_GITHUB,
    obter_modo_operacao,
)
from ch_control_center.graph.dag_engine import DAGEngine, ResultadoGrafoDAG


class MissionService:
    """Orquestrador de leitura e consulta de missões do Control Center."""

    def __init__(
        self,
        facade: SentinelFacade | None = None,
        dag_engine: DAGEngine | None = None,
    ) -> None:
        caminho_demo = DIRETORIO_FIXTURES / "demo_project_snapshot.json"
        self.facade = facade or SentinelFacade(caminho_fixture_demo=caminho_demo)
        self.dag_engine = dag_engine or DAGEngine()
        self._modo_operacao = obter_modo_operacao()
        self.contador_leituras_snapshot: int = 0

    def obter_modo_operacao(self) -> str:
        """Retorna o modo de operação ativo (DEMO_OFFLINE ou LIVE_GITHUB)."""
        return self._modo_operacao

    def alternar_modo_operacao(self, novo_modo: str) -> str:
        """Alterna explicitamente entre modo ao vivo e demonstração offline."""
        modo = novo_modo.upper().strip()
        if modo in (MODO_DEMO_OFFLINE, MODO_LIVE_GITHUB):
            self._modo_operacao = modo
        return self._modo_operacao

    def obter_snapshot_ativo(self) -> tuple[dict[str, Any], str]:
        """Obtém o snapshot de dados conforme o modo ativo.

        Incrementa contador_leituras_snapshot para monitoramento e auditoria (AUD-05).

        Returns:
            Tupla (snapshot_dict, origem_dados_str).
        """
        self.contador_leituras_snapshot += 1

        if self._modo_operacao == MODO_LIVE_GITHUB:
            try:
                snapshot = self.facade.obter_snapshot_ao_vivo()
                return snapshot, MODO_LIVE_GITHUB
            except SentinelaAdapterErro:
                # Fail-closed informativo: não mascara o erro; se a consulta ao vivo falha,
                # e o usuário solicitou LIVE_GITHUB, não faz fallback silencioso.
                raise

        snapshot = self.facade.obter_snapshot_demo()
        return snapshot, MODO_DEMO_OFFLINE

    def normalizar_itens_snapshot(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Normaliza as tarefas a partir de um snapshot imutável em memória (AUD-05)."""
        itens = snapshot.get("items", [])
        tarefas_processadas: list[dict[str, Any]] = []

        for item in itens:
            if not isinstance(item, dict):
                continue

            content = item.get("content", {})
            labels = content.get("labels", []) if isinstance(content, dict) else []

            # Filtra itens com etiqueta de fluxo
            is_workflow = any("ch:workflow" in str(lbl).lower() for lbl in labels) or "dependencies" in item
            if not is_workflow:
                continue

            item_id = str(item.get("id") or f"W-{content.get('number', '0')}")
            titulo = content.get("title") or item.get("title") or "Sem título"
            numero = content.get("number")
            repo = content.get("repository", "hallanbrito/CHDevFlow")
            url = content.get("url", "#")
            stage = item.get("etapa_ch") or item.get("status") or "BACKLOG"
            esteira = item.get("esteira") or item.get("executor") or "AGY"
            autonomia = item.get("autonomia") or "CH-1"
            deps = item.get("dependencies", [])

            tarefas_processadas.append({
                "id": item_id,
                "number": numero,
                "title": titulo,
                "stage": stage,
                "esteira": esteira,
                "autonomia": autonomia,
                "repository": repo,
                "url": url,
                "dependencies": deps,
                "raw_item": item,
            })

        return tarefas_processadas

    def processar_tarefas_brutas(self) -> list[dict[str, Any]]:
        """Lê o snapshot ativo e normaliza a lista de tarefas para processamento do grafo."""
        snapshot, _ = self.obter_snapshot_ativo()
        return self.normalizar_itens_snapshot(snapshot)

    def construir_visao_operacional_completa(
        self,
        snapshot: dict[str, Any] | None = None,
        origem: str | None = None,
    ) -> dict[str, Any]:
        """Gera a visão consolidada a partir de uma ÚNICA leitura de snapshot (AUD-05).

        Garante consistência atômica: grafo, lista de missões e contadores métricos
        derivam exatamente do mesmo snapshot imutável.
        """
        if snapshot is None:
            snapshot, modo = self.obter_snapshot_ativo()
        else:
            modo = origem or self._modo_operacao

        tarefas = self.normalizar_itens_snapshot(snapshot)
        grafo = self.dag_engine.construir_grafo(tarefas)

        # Enriquecimento atômico das tarefas com o estado do grafo
        missoes_enriquecidas: list[dict[str, Any]] = []
        for t in tarefas:
            task_id = t["id"]
            no = grafo.nos.get(task_id)
            missao = dict(t)
            missao["status_grafo"] = no.status_grafo if no else "PENDENTE"
            missao["motivo_bloqueio"] = no.motivo_bloqueio if no else None
            missoes_enriquecidas.append(missao)

        stats = {
            "total_tarefas": grafo.total_tarefas,
            "total_elegiveis": grafo.total_elegiveis,
            "total_bloqueadas": grafo.total_bloqueadas,
            "total_concluidas": grafo.total_concluidas,
            "total_ciclos": len(grafo.ciclos_detectados),
            "total_orfas": len(grafo.dependencias_desconhecidas),
            "modo_operacao": modo,
        }

        return {
            "snapshot": snapshot,
            "modo_operacao": modo,
            "tarefas": tarefas,
            "grafo": grafo,
            "stats": stats,
            "missoes": missoes_enriquecidas,
        }

    def obter_contexto_dashboard(self) -> dict[str, Any]:
        """Retorna o contexto completo do dashboard garantindo exatamente 1 leitura de snapshot (AUD-05)."""
        return self.construir_visao_operacional_completa()

    def obter_grafo_dag(self) -> ResultadoGrafoDAG:
        """Gera e retorna o Grafo DAG de Dependências estruturado."""
        visao = self.construir_visao_operacional_completa()
        return visao["grafo"]

    def listar_missoes(
        self,
        filtro_status: str | None = None,
        filtro_esteira: str | None = None,
        termo_busca: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna a lista de missões enriquecidas com a classificação do grafo DAG."""
        visao = self.construir_visao_operacional_completa()
        todas = visao["missoes"]
        resultado: list[dict[str, Any]] = []

        for m in todas:
            status_grafo = m["status_grafo"]
            # Filtros
            if filtro_status and filtro_status != "TODOS" and status_grafo != filtro_status:
                continue
            if filtro_esteira and filtro_esteira != "TODAS" and m["esteira"].upper() != filtro_esteira.upper():
                continue
            if termo_busca:
                busca = termo_busca.lower()
                if busca not in m["title"].lower() and busca not in m["id"].lower():
                    continue

            resultado.append(m)

        return resultado

    def obter_missao_por_id(self, mission_id: str) -> dict[str, Any] | None:
        """Localiza e retorna os detalhes completos de uma missão por ID, número ou prefixo."""
        missoes = self.listar_missoes()
        alvo = mission_id.strip()
        alvo_limpo = alvo.lower().replace("item-", "").replace("-", "")

        for m in missoes:
            mid = m["id"]
            mid_limpo = mid.lower().replace("item-", "").replace("-", "")

            # 1. Correspondência exata ou sem traço/item
            if mid == alvo or mid.lower() == alvo.lower() or mid_limpo == alvo_limpo:
                return m

            # 2. Correspondência por número de issue
            if str(m.get("number")) == alvo.lstrip("#"):
                return m

            # 3. Correspondência se o título iniciar com o ID
            titulo = m.get("title", "")
            if titulo.upper().startswith(alvo.upper() + " ") or titulo.upper().startswith(alvo.upper() + " —"):
                return m

        return None

    def obter_resumo_estatisticas(self) -> dict[str, Any]:
        """Calcula métricas e contadores para os cartões de resumo do Dashboard."""
        grafo = self.obter_grafo_dag()
        return {
            "total_tarefas": grafo.total_tarefas,
            "total_elegiveis": grafo.total_elegiveis,
            "total_bloqueadas": grafo.total_bloqueadas,
            "total_concluidas": grafo.total_concluidas,
            "total_ciclos": len(grafo.ciclos_detectados),
            "total_orfas": len(grafo.dependencias_desconhecidas),
            "modo_operacao": self._modo_operacao,
        }
