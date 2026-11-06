"""Serviço de gerenciamento e leitura de missões (MissionService).

Consome dados do GitHub Project #2 via SentinelFacade, alterna entre
modo ao vivo e demonstração offline (RF-06/CC-01) e processa dependências via DAGEngine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from typing import Any

from ch_sentinela.config import REPOSITORIO_CANONICO

from ch_control_center.adapters.sentinela_adapter import SentinelFacade, SentinelaAdapterErro
from ch_control_center.config import (
    DIRETORIO_FIXTURES,
    MODO_DEMO_OFFLINE,
    MODO_LIVE_GITHUB,
    obter_modo_operacao,
)
from ch_control_center.graph.dag_engine import DAGEngine, ETAPAS_FECHAMENTO_VISUAL, ResultadoGrafoDAG

TTL_CACHE_PADRAO_SEGUNDOS: float = 60.0


@dataclass
class EstadoSincronizacao:
    """Estado do ciclo de sincronização de dados do Control Center (F2/F4)."""

    source: str
    status: str = "OK"  # "SYNCING" | "OK" | "STALE" | "ERROR"
    last_success_at: str | None = None
    last_attempt_at: str | None = None
    total_received: int = 0
    total_recognized: int = 0
    error_code: str | None = None
    diagnostic: str | None = None
    snapshot_id: str | None = None

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa o estado para dicionário seguro para API."""
        return asdict(self)


class MissionService:
    """Orquestrador de leitura e consulta de missões do Control Center."""

    def __init__(
        self,
        facade: SentinelFacade | None = None,
        dag_engine: DAGEngine | None = None,
        ttl_cache_segundos: float = TTL_CACHE_PADRAO_SEGUNDOS,
    ) -> None:
        caminho_demo = DIRETORIO_FIXTURES / "demo_project_snapshot.json"
        self.facade = facade or SentinelFacade(caminho_fixture_demo=caminho_demo)
        self.dag_engine = dag_engine or DAGEngine()
        self._modo_operacao = obter_modo_operacao()
        self.contador_leituras_snapshot: int = 0
        self.ttl_cache_segundos = ttl_cache_segundos

        # Cache em memória e controle de concorrência (F2)
        self._lock_snapshot = threading.Lock()
        self._cache_visao: dict[str, Any] | None = None
        self._cache_timestamp: float = 0.0
        self._cache_origem: str | None = None
        self._estado_sincronizacao = EstadoSincronizacao(
            source=self._modo_operacao,
            status="OK",
        )

    def obter_modo_operacao(self) -> str:
        """Retorna o modo de operação ativo (DEMO_OFFLINE ou LIVE_GITHUB)."""
        return self._modo_operacao

    def alternar_modo_operacao(self, novo_modo: str) -> str:
        """Alterna explicitamente entre modo ao vivo e demonstração offline."""
        modo = novo_modo.upper().strip()
        if modo in (MODO_DEMO_OFFLINE, MODO_LIVE_GITHUB):
            with self._lock_snapshot:
                if self._modo_operacao != modo:
                    self._modo_operacao = modo
                    self._cache_visao = None
                    self._cache_timestamp = 0.0
                    self._cache_origem = None
                    self._estado_sincronizacao.source = modo
                    self._estado_sincronizacao.status = "OK"
                    self._estado_sincronizacao.error_code = None
                    self._estado_sincronizacao.diagnostic = None
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

    def normalizar_itens_snapshot(self, snapshot: dict[str, Any], origem: str | None = None) -> list[dict[str, Any]]:
        """Normaliza as tarefas a partir de um snapshot imutável em memória (AUD-05)."""
        itens = snapshot.get("items", [])
        tarefas_processadas: list[dict[str, Any]] = []
        ids_vistos: set[str] = set()
        refs_vistas: set[str] = set()

        for item in itens:
            if not isinstance(item, dict):
                continue

            content = item.get("content")
            if not isinstance(content, dict) or content.get("type") != "Issue":
                continue
            if content.get("repository") != REPOSITORIO_CANONICO:
                continue

            # gh entrega labels na raiz; a fixture legada usa content.labels.
            # Uma etiqueta parecida ou um campo dependencies não autorizam inclusão.
            labels = item.get("labels", content.get("labels", []))
            if not isinstance(labels, list):
                continue
            nomes = {
                nome.strip().lower()
                for label in labels
                if isinstance(nome := label.get("name") if isinstance(label, dict) else label, str)
            }
            if "ch:workflow" not in nomes:
                continue

            item_id = str(item.get("id") or f"W-{content.get('number', '0')}")
            if item_id in ids_vistos:
                raise SentinelaAdapterErro("ID de item do Project duplicado; grafo inconclusivo.")
            ids_vistos.add(item_id)
            titulo = content.get("title") or item.get("title") or "Sem título"
            numero = content.get("number")
            repo = content.get("repository", "hallanbrito/CHDevFlow")
            url = content.get("url", "#")
            issue_ref = f"{repo}#{numero}" if isinstance(numero, int) and not isinstance(numero, bool) and numero > 0 else None
            if issue_ref in refs_vistas:
                raise SentinelaAdapterErro("Issue duplicada no Project; grafo inconclusivo.")
            if issue_ref:
                refs_vistas.add(issue_ref)
            # Nomes nativos do Project têm espaços. Campos ausentes permanecem
            # desconhecidos: Status=Done não equivale a homologação pelo PO.
            stage = item.get("etapa CH") or item.get("etapa_ch")
            esteira = item.get("esteira") or item.get("executor")
            autonomia = item.get("autonomia CH") or item.get("autonomia")
            pendencias_dados = []
            valores = []
            for nome, valor in (("Etapa CH", stage), ("Esteira", esteira), ("Autonomia CH", autonomia)):
                if not isinstance(valor, str) or not valor.strip():
                    pendencias_dados.append(f"{nome} não informada")
                    valor = "NAO_INFORMADA"
                valores.append(valor.strip())
            stage, esteira, autonomia = valores

            observacao = item.get("dependency_observation") if origem == MODO_LIVE_GITHUB else None
            if origem == MODO_LIVE_GITHUB:
                estado_deps = observacao.get("dependency_state") if isinstance(observacao, dict) else "UNKNOWN"
                refs = observacao.get("dependency_refs") if isinstance(observacao, dict) else None
                source = observacao.get("source") if isinstance(observacao, dict) else "github_rest:blocked_by"
                observed_at = observacao.get("observed_at") if isinstance(observacao, dict) else None
                fonte_esperada = f"github_rest:/repos/{repo}/issues/{numero}/dependencies/blocked_by"
                if (not isinstance(observacao, dict) or observacao.get("issue_ref") != issue_ref
                    or not isinstance(refs, list) or estado_deps not in ("VERIFIED_EMPTY", "VERIFIED_NONEMPTY")
                    or (estado_deps == "VERIFIED_EMPTY" and refs) or (estado_deps == "VERIFIED_NONEMPTY" and not refs)
                    or (estado_deps in ("VERIFIED_EMPTY", "VERIFIED_NONEMPTY") and (source != fonte_esperada or not isinstance(observed_at, str) or not observed_at))
                    or any(not isinstance(ref, dict) or not isinstance(ref.get("issue_ref"), str) or not ref.get("issue_ref") or not isinstance(ref.get("url"), str) or not isinstance(ref.get("node_id"), str) for ref in refs)):
                    if estado_deps not in ("INVALID", "UNKNOWN"):
                        estado_deps = "INVALID"
                    refs = []
                dependency_refs = refs
                deps = []  # resolvidas depois que todas as Issues do Project forem indexadas
                deps_informadas = estado_deps in ("VERIFIED_EMPTY", "VERIFIED_NONEMPTY")
                diagnostic = observacao.get("diagnostic") if isinstance(observacao, dict) else None
            else:
                deps_raw = item.get("dependencies")
                deps_informadas = isinstance(deps_raw, list) and all(isinstance(dep, str) and bool(dep.strip()) for dep in deps_raw)
                deps = [dep.strip() for dep in deps_raw] if deps_informadas else []
                estado_deps = ("VERIFIED_NONEMPTY" if deps else "VERIFIED_EMPTY") if deps_informadas else "UNKNOWN"
                dependency_refs = []
                source, observed_at, diagnostic = "fixture_offline", None, None
            if not deps_informadas:
                pendencias_dados.append("Dependências desconhecidas ou inválidas")
            if issue_ref is None or url != f"https://github.com/{repo}/issues/{numero}":
                pendencias_dados.append("Identidade da Issue inválida")

            tarefas_processadas.append({
                "id": item_id,
                "project_item_id": item.get("id"),
                "issue_ref": issue_ref,
                "number": numero,
                "title": titulo,
                "stage": stage,
                "esteira": esteira,
                "autonomia": autonomia,
                "repository": repo,
                "url": url,
                "dependencies": deps,
                "dependency_refs": dependency_refs,
                "dependency_state": estado_deps,
                "dependency_source": source,
                "dependency_observed_at": observed_at,
                "dependency_diagnostic": diagnostic,
                "dependencies_informadas": deps_informadas,
                "homologacao_verificada": False,
                "pendencias_dados": pendencias_dados,
                "raw_item": item,
            })

        if origem == MODO_LIVE_GITHUB:
            indice = {t["issue_ref"]: t["id"] for t in tarefas_processadas if t["issue_ref"]}
            for tarefa in tarefas_processadas:
                if not tarefa["dependencies_informadas"]:
                    continue
                resolvidas = [indice.get(ref["issue_ref"], ref["issue_ref"]) for ref in tarefa["dependency_refs"]]
                if len(set(resolvidas)) != len(resolvidas):
                    tarefa["dependency_state"] = "INVALID"
                    tarefa["dependencies_informadas"] = False
                    tarefa["pendencias_dados"].append("Dependências duplicadas")
                else:
                    tarefa["dependencies"] = resolvidas
        return tarefas_processadas

    def processar_tarefas_brutas(self) -> list[dict[str, Any]]:
        """Lê o snapshot ativo e normaliza a lista de tarefas para processamento do grafo."""
        snapshot, modo = self.obter_snapshot_ativo()
        return self.normalizar_itens_snapshot(snapshot, modo)

    def construir_visao_operacional_completa(
        self,
        snapshot: dict[str, Any] | None = None,
        origem: str | None = None,
    ) -> dict[str, Any]:
        """Gera a visão consolidada a partir de uma ÚNICA leitura de snapshot (AUD-05).

        Grafo, lista e métricas derivam do mesmo conjunto de respostas desta
        requisição. A API GitHub não fornece transação atômica entre endpoints.
        """
        if snapshot is None:
            snapshot, modo = self.obter_snapshot_ativo()
        else:
            modo = origem or self._modo_operacao

        tarefas = self.normalizar_itens_snapshot(snapshot, modo)
        grafo = self.dag_engine.construir_grafo(tarefas)

        # Enriquecimento atômico das tarefas com o estado do grafo
        missoes_enriquecidas: list[dict[str, Any]] = []
        for t in tarefas:
            task_id = t["id"]
            no = grafo.nos.get(task_id)
            missao = dict(t)
            missao["status_grafo"] = no.status_grafo if no else "PENDENTE"
            missao["motivo_bloqueio"] = no.motivo_bloqueio if no else None
            # Sincroniza pendencias_dados e causas_diagnosticas derivadas do DAG (F1)
            if no:
                missao["pendencias_dados"] = list(no.pendencias_dados)
                missao["causas_diagnosticas"] = list(no.causas_diagnosticas)
            else:
                missao["causas_diagnosticas"] = []
            missoes_enriquecidas.append(missao)

        stats = {
            "total_tarefas": grafo.total_tarefas,
            "total_elegiveis": grafo.total_elegiveis,
            "total_bloqueadas": grafo.total_bloqueadas,
            "total_concluidas": grafo.total_concluidas,
            "total_etapas_conclusao_observadas": sum(t["stage"].upper() in ETAPAS_FECHAMENTO_VISUAL for t in tarefas),
            "total_ciclos": len(grafo.ciclos_detectados),
            "total_orfas": len(grafo.dependencias_desconhecidas),
            "modo_operacao": modo,
            "total_recebidos": len(snapshot.get("items", [])),
            "total_ignorados": len(snapshot.get("items", [])) - len(tarefas),
            "total_dados_insuficientes": grafo.total_dados_insuficientes,
            "contagem_por_causa": grafo.contagem_por_causa,
        }

        return {
            "snapshot": snapshot,
            "modo_operacao": modo,
            "tarefas": tarefas,
            "grafo": grafo,
            "stats": stats,
            "missoes": missoes_enriquecidas,
        }

    def obter_visao_operacional(self, forcar_atualizacao: bool = False) -> dict[str, Any]:
        """Obtém a visão operacional ativa usando cache em memória compartilhado (F2).

        Garante coalescência de requisições concorrentes e impede leituras repetitivas
        ao GitHub por tela/cartão, respeitando o TTL configurado.
        """
        # 1. Leitura rápida do cache sem lock se válido e fresco
        if not forcar_atualizacao:
            with self._lock_snapshot:
                if (
                    self._cache_visao is not None
                    and self._cache_origem == self._modo_operacao
                    and (time.monotonic() - self._cache_timestamp) < self.ttl_cache_segundos
                ):
                    return self._cache_visao

        # 2. Seção crítica de atualização: apenas uma thread consulta a fonte
        with self._lock_snapshot:
            # Double-check: outra thread pode ter acabado de atualizar enquanto aguardávamos o lock
            if not forcar_atualizacao:
                if (
                    self._cache_visao is not None
                    and self._cache_origem == self._modo_operacao
                    and (time.monotonic() - self._cache_timestamp) < self.ttl_cache_segundos
                ):
                    return self._cache_visao

            agora_iso = datetime.now(timezone.utc).isoformat()
            self._estado_sincronizacao.status = "SYNCING"
            self._estado_sincronizacao.last_attempt_at = agora_iso

            try:
                snapshot, modo = self.obter_snapshot_ativo()
                visao = self.construir_visao_operacional_completa(snapshot=snapshot, origem=modo)
                self._cache_visao = visao
                self._cache_timestamp = time.monotonic()
                self._cache_origem = modo

                # Atualiza estado de sincronização de sucesso (F4)
                self._estado_sincronizacao.source = modo
                self._estado_sincronizacao.status = "OK"
                self._estado_sincronizacao.last_success_at = agora_iso
                self._estado_sincronizacao.total_received = len(snapshot.get("items", []))
                self._estado_sincronizacao.total_recognized = len(visao["tarefas"])
                self._estado_sincronizacao.error_code = None
                self._estado_sincronizacao.diagnostic = None

                raw_bytes = json.dumps(snapshot, sort_keys=True).encode("utf-8")
                self._estado_sincronizacao.snapshot_id = hashlib.sha256(raw_bytes).hexdigest()[:16]

                return visao
            except Exception as exc:
                erro_sanitizado = self.facade.sanitizar(str(exc))
                codigo_erro = type(exc).__name__
                self._estado_sincronizacao.error_code = codigo_erro
                self._estado_sincronizacao.diagnostic = erro_sanitizado

                # Se já havia snapshot prévio em memória, preserva-o com status STALE (F2)
                if self._cache_visao is not None:
                    self._estado_sincronizacao.status = "STALE"
                    return self._cache_visao

                # Se não há snapshot prévio (falha na inicialização), marca ERROR e propaga
                self._estado_sincronizacao.status = "ERROR"
                raise

    def obter_estado_sincronizacao(self) -> EstadoSincronizacao:
        """Retorna o estado atual da sincronização de dados (F4)."""
        return self._estado_sincronizacao

    def sincronizar_agora(self) -> dict[str, Any]:
        """Força atualização imediata da sincronização e retorna resumo estruturado (F4)."""
        visao = self.obter_visao_operacional(forcar_atualizacao=True)
        return {
            "status": self._estado_sincronizacao.status,
            "estado": self._estado_sincronizacao.para_dicionario(),
            "stats": visao["stats"],
        }

    def obter_contexto_dashboard(self, forcar_atualizacao: bool = False) -> dict[str, Any]:
        """Retorna o contexto completo do dashboard garantindo exatamente 1 leitura de snapshot (AUD-05)."""
        return self.obter_visao_operacional(forcar_atualizacao=forcar_atualizacao)

    def obter_grafo_dag(self, forcar_atualizacao: bool = False) -> ResultadoGrafoDAG:
        """Gera e retorna o Grafo DAG de Dependências estruturado."""
        visao = self.obter_visao_operacional(forcar_atualizacao=forcar_atualizacao)
        return visao["grafo"]

    def listar_missoes(
        self,
        filtro_status: str | None = None,
        filtro_esteira: str | None = None,
        termo_busca: str | None = None,
        forcar_atualizacao: bool = False,
    ) -> list[dict[str, Any]]:
        """Retorna a lista de missões enriquecidas com a classificação do grafo DAG."""
        visao = self.obter_visao_operacional(forcar_atualizacao=forcar_atualizacao)
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

    def obter_resumo_estatisticas(self, forcar_atualizacao: bool = False) -> dict[str, Any]:
        """Calcula métricas e contadores para os cartões de resumo do Dashboard."""
        return self.obter_visao_operacional(forcar_atualizacao=forcar_atualizacao)["stats"]
