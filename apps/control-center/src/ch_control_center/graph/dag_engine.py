"""Motor de Grafo de Dependências (DAG Engine) do CHDevFlow Control Center.

Processa a ordem topológica entre Fatias W em modo ESTRITAMENTE SOMENTE LEITURA.
Identifica tarefas elegíveis, tarefas bloqueadas por dependências, ciclos circulares
e dependências desconhecidas ou ausentes, sem nunca inferir autorização executiva.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class NoGrafo:
    """Representa uma tarefa (Fatia W) como nó no grafo de dependências."""

    id: str                      # Identificador único (ex: "W-01", "#12")
    numero_issue: int | None     # Número da Issue no GitHub
    titulo: str                  # Título da tarefa
    etapa_ch: str                # BACKLOG, PRONTA, EM_EXECUCAO, INTEGRADA, HOMOLOGADA
    esteira: str                 # Codex, AGY, ChatGPT, PO
    autonomia: str               # CH-0, CH-1, CH-2
    dependencias: list[str]      # Lista de IDs das quais esta tarefa depende
    pendencias_dados: list[str] = field(default_factory=list) # Informações ainda não verificadas
    dependentes: list[str] = field(default_factory=list) # Tarefas que dependem desta
    grau_entrada: int = 0        # Número de dependências não concluídas
    status_grafo: str = "PENDENTE" # ELEGIVEL, BLOQUEADA_POR_DEPENDENCIA, BLOQUEADA_CICLO, BLOQUEADA_ORFA, CONCLUIDA
    motivo_bloqueio: str | None = None

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o nó para dicionário JSON."""
        return asdict(self)


@dataclass
class ResultadoGrafoDAG:
    """Resultado estruturado da análise topológica do grafo de dependências."""

    schema: str
    projeto: str
    gerado_em_utc: str
    nos: dict[str, NoGrafo]
    arestas: list[dict[str, str]]
    ordem_topologica: list[str]
    ciclos_detectados: list[list[str]]
    dependencias_desconhecidas: dict[str, list[str]]
    total_tarefas: int
    total_elegiveis: int
    total_bloqueadas: int
    total_concluidas: int

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o resultado completo para dicionário serializável."""
        return {
            "schema": self.schema,
            "projeto": self.projeto,
            "gerado_em_utc": self.gerado_em_utc,
            "nos": {k: v.para_dicionario() for k, v in self.nos.items()},
            "arestas": self.arestas,
            "ordem_topologica": self.ordem_topologica,
            "ciclos_detectados": self.ciclos_detectados,
            "dependencias_desconhecidas": self.dependencias_desconhecidas,
            "total_tarefas": self.total_tarefas,
            "total_elegiveis": self.total_elegiveis,
            "total_bloqueadas": self.total_bloqueadas,
            "total_concluidas": self.total_concluidas,
        }


STATUS_ELEGIVEL: str = "ELEGIVEL"
STATUS_CONCLUIDA: str = "CONCLUIDA"
STATUS_BLOQUEADA_DEP: str = "BLOQUEADA_POR_DEPENDENCIA"
STATUS_BLOQUEADA_CICLO: str = "BLOQUEADA_CICLO"
STATUS_BLOQUEADA_ORFA: str = "BLOQUEADA_ORFA"
STATUS_BLOQUEADA_DADOS: str = "BLOQUEADA_DADOS"

ETAPAS_CONCLUIDAS: tuple[str, ...] = ("INTEGRADA", "HOMOLOGADA", "DONE", "CLOSED", "PROD_OK")


class DAGEngine:
    """Processador de análise topológica e integridade de dependências."""

    def __init__(self, projeto_key: str = "chdevflow") -> None:
        self.projeto_key = projeto_key

    def construir_grafo(self, tarefas: list[dict[str, Any]]) -> ResultadoGrafoDAG:
        """Constrói o grafo a partir de uma lista de tarefas e realiza ordenação topológica.

        Args:
            tarefas: Lista de dicionários contendo campos da tarefa (id, title, stage, dependencies).

        Returns:
            ResultadoGrafoDAG com nós categorizados e detecção de anomalias.
        """
        nos: dict[str, NoGrafo] = {}
        arestas: list[dict[str, str]] = []
        dependencias_desconhecidas: dict[str, list[str]] = defaultdict(list)

        # 1. Registro inicial de todos os nós
        for item in tarefas:
            task_id = str(item.get("id") or item.get("mission_id") or f"W-{item.get('number', 0)}")
            titulo = str(item.get("title") or item.get("titulo") or "Sem título")
            etapa = str(item.get("stage") or item.get("etapa_ch") or "BACKLOG").upper()
            esteira = str(item.get("esteira") or item.get("executor") or "AGY")
            autonomia = str(item.get("autonomia") or "CH-1")
            numero_issue = item.get("number") or item.get("numero_issue")

            deps_raw = item.get("dependencies") or item.get("dependencias") or []
            deps = [str(d).strip() for d in deps_raw if str(d).strip()]

            no = NoGrafo(
                id=task_id,
                numero_issue=int(numero_issue) if numero_issue else None,
                titulo=titulo,
                etapa_ch=etapa,
                esteira=esteira,
                autonomia=autonomia,
                dependencias=deps,
                pendencias_dados=list(item.get("pendencias_dados", [])),
            )
            # Preserva a etapa concluída explicitamente observada no Project.
            # Dados incompletos continuam sinalizados, mas não reescrevem essa etapa.
            if etapa in ETAPAS_CONCLUIDAS:
                no.status_grafo = "CONCLUIDA"
            elif no.pendencias_dados:
                no.status_grafo = STATUS_BLOQUEADA_DADOS

            nos[task_id] = no

        # 2. Resolução de dependências e construção de arestas
        ids_existentes = set(nos.keys())

        for task_id, no in nos.items():
            for dep_id in no.dependencias:
                if dep_id not in ids_existentes:
                    # Dependência órfã / desconhecida
                    dependencias_desconhecidas[task_id].append(dep_id)
                else:
                    # Aresta direcionada: dep_id -> task_id (dep_id precede task_id)
                    nos[dep_id].dependentes.append(task_id)
                    arestas.append({"source": dep_id, "target": task_id})

        # 3. Cálculo de graus de entrada (considerando apenas dependências NÃO concluídas)
        for task_id, no in nos.items():
            if no.status_grafo == "CONCLUIDA":
                no.grau_entrada = 0
                continue

            deps_pendentes = [
                d for d in no.dependencias
                if d in ids_existentes and nos[d].status_grafo != "CONCLUIDA"
            ]
            no.grau_entrada = len(deps_pendentes) + len(dependencias_desconhecidas.get(task_id, []))

        # 4. Ordenação Topológica via Algoritmo de Kahn & Detecção de Ciclos
        graus_trabalho = {k: v.grau_entrada for k, v in nos.items() if v.status_grafo != STATUS_CONCLUIDA}
        fila_kahn: deque[str] = deque([
            k for k, grau in graus_trabalho.items()
            if grau == 0 and not dependencias_desconhecidas.get(k) and not nos[k].pendencias_dados
        ])
        nos_elegiveis_iniciais: set[str] = set(fila_kahn)

        ordem_topologica: list[str] = [k for k, v in nos.items() if v.status_grafo == STATUS_CONCLUIDA]
        visitados_kahn: set[str] = set()

        while fila_kahn:
            atual_id = fila_kahn.popleft()
            visitados_kahn.add(atual_id)
            ordem_topologica.append(atual_id)

            for dependente_id in nos[atual_id].dependentes:
                if dependente_id in graus_trabalho:
                    graus_trabalho[dependente_id] -= 1
                    if (
                        graus_trabalho[dependente_id] == 0
                        and not dependencias_desconhecidas.get(dependente_id)
                        and not nos[dependente_id].pendencias_dados
                    ):
                        fila_kahn.append(dependente_id)

        # 5. Classificação dos nós que não puderam ser ordenados (Ciclos)
        ciclos_detectados: list[list[str]] = []
        nos_nao_ordenados = set(graus_trabalho.keys()) - visitados_kahn

        if nos_nao_ordenados:
            ciclos_detectados = self._identificar_ciclos_dfs(nos, nos_nao_ordenados)

        # AUD-04: Coleta estrita dos nós que efetivamente são membros de ciclos detectados
        nos_em_ciclos: set[str] = {no_id for ciclo in ciclos_detectados for no_id in ciclo}

        # 6. Atualização final de status e motivos de bloqueio
        for task_id, no in nos.items():
            if no.status_grafo == STATUS_CONCLUIDA:
                continue

            if no.pendencias_dados:
                no.status_grafo = STATUS_BLOQUEADA_DADOS
                no.motivo_bloqueio = "Dados insuficientes: " + "; ".join(no.pendencias_dados)
            elif dependencias_desconhecidas.get(task_id):
                no.status_grafo = STATUS_BLOQUEADA_ORFA
                faltantes = ", ".join(dependencias_desconhecidas[task_id])
                no.motivo_bloqueio = f"Dependência(s) ausente(s) ou não concluída(s): {faltantes}"
            elif task_id in nos_em_ciclos:
                no.status_grafo = STATUS_BLOQUEADA_CICLO
                no.motivo_bloqueio = "Ciclo de dependência circular detectado!"
            elif task_id in nos_elegiveis_iniciais:
                no.status_grafo = STATUS_ELEGIVEL
                no.motivo_bloqueio = None
            else:
                no.status_grafo = STATUS_BLOQUEADA_DEP
                deps_abertas = [d for d in no.dependencias if d in nos and nos[d].status_grafo != STATUS_CONCLUIDA]
                no.motivo_bloqueio = f"Aguardando conclusão de: {', '.join(deps_abertas)}"

        # Estatísticas
        total_elegiveis = sum(1 for n in nos.values() if n.status_grafo == "ELEGIVEL")
        total_bloqueadas = sum(1 for n in nos.values() if n.status_grafo.startswith("BLOQUEADA"))
        total_concluidas = sum(1 for n in nos.values() if n.status_grafo == "CONCLUIDA")

        agora_utc = datetime.now(timezone.utc).isoformat()

        return ResultadoGrafoDAG(
            schema="chdevflow.control-center.graph-view/0.1",
            projeto=self.projeto_key,
            gerado_em_utc=agora_utc,
            nos=nos,
            arestas=arestas,
            ordem_topologica=ordem_topologica,
            ciclos_detectados=ciclos_detectados,
            dependencias_desconhecidas=dict(dependencias_desconhecidas),
            total_tarefas=len(nos),
            total_elegiveis=total_elegiveis,
            total_bloqueadas=total_bloqueadas,
            total_concluidas=total_concluidas,
        )

    def _identificar_ciclos_dfs(
        self,
        nos: dict[str, NoGrafo],
        candidatos: set[str],
    ) -> list[list[str]]:
        """Identifica componentes de ciclos direcionados usando DFS."""
        ciclos: list[list[str]] = []
        visitado: dict[str, int] = {k: 0 for k in candidatos}  # 0: não visitado, 1: na pilha, 2: finalizado
        pilha: list[str] = []

        def dfs(atual: str) -> None:
            visitado[atual] = 1
            pilha.append(atual)

            for vizinho in nos[atual].dependentes:
                if vizinho in candidatos:
                    if visitado[vizinho] == 1:
                        # Ciclo encontrado: extrai a fatia da pilha a partir de vizinho
                        idx = pilha.index(vizinho)
                        ciclo = list(pilha[idx:])
                        if ciclo not in ciclos:
                            ciclos.append(ciclo)
                    elif visitado[vizinho] == 0:
                        dfs(vizinho)

            pilha.pop()
            visitado[atual] = 2

        for no_id in candidatos:
            if visitado[no_id] == 0:
                dfs(no_id)

        return ciclos
