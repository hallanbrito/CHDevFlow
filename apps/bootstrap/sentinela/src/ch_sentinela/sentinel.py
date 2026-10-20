"""Módulo da Sentinela de Observação (CHDevFlow Sentinel).

Implementa a observação pontual de execução única (`watch --once --dry-run`):
- Consulta o estado autorizado no GitHub ou via fixtures offline.
- Identifica tarefas candidatas, duplicadas ou inválidas.
- Emite eventos estruturados sem disparar nenhuma execução automática.
- Encerra o ciclo imediatamente, respeitando a Decisão D05 (sem loop contínuo).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ch_sentinela.audit import Auditoria
from ch_sentinela.config import REPOSITORIO_CANONICO
from ch_sentinela.github_reader import LeitorGitHub, validar_snapshot_projeto


@dataclass(frozen=True)
class EventoSentinela:
    """Representa um evento estruturado gerado pela observação da Sentinela."""

    tipo_evento: str  # DISCOVERED, DUPLICATE_IGNORED, INVALID_IGNORED, etc.
    numero_issue: int | None
    repositorio: str
    titulo: str
    detalhes: str
    timestamp_utc: str
    dados_extras: dict[str, Any]

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o evento para dicionário serializável."""
        return asdict(self)


class Sentinela:
    """Observador conservador e pontual do GitHub para identificação de missões."""

    def __init__(
        self,
        leitor: LeitorGitHub | None = None,
        auditoria: Auditoria | None = None,
    ) -> None:
        """Inicializa a Sentinela.

        Args:
            leitor: Instância configurada de LeitorGitHub. Se None, cria uma padrão.
            auditoria: Instância opcional de Auditoria para registrar eventos gerados.
        """
        self.leitor = leitor or LeitorGitHub()
        self.auditoria = auditoria

    def observar_uma_vez(
        self,
        snapshot_projeto: dict[str, Any] | None = None,
        fonte_dados: str = "LIVE_GITHUB",
    ) -> list[EventoSentinela]:
        """Executa uma única rodada de observação ('watch --once') e encerra.

        Analisa a fotografia (snapshot) dos itens do GitHub Project, filtra tarefas
        com a etiqueta 'ch:workflow', detecta inconsistências e retorna eventos estruturados.

        Args:
            snapshot_projeto: Dados pré-carregados (para modo offline ou testes).
            fonte_dados: Identificador da origem dos dados para auditoria.

        Returns:
            Lista de EventoSentinela produzidos durante a consulta.
        """
        # 1. Obtenção e validação estrutural estrita do snapshot: via fixture offline ou via GitHub CLI
        if snapshot_projeto is not None:
            dados = snapshot_projeto
            origem = "FIXTURE_OFFLINE"
        else:
            dados = self.leitor.listar_itens_projeto()
            origem = fonte_dados

        validar_snapshot_projeto(dados)

        itens = dados["items"]
        eventos_gerados: list[EventoSentinela] = []
        issues_vistas: set[int] = set()

        agora = datetime.now(timezone.utc).isoformat()

        # 2. Processamento individual de cada item com validação estrita
        for item in itens:
            if not isinstance(item, dict):
                evento = EventoSentinela(
                    tipo_evento="INVALID_IGNORED",
                    numero_issue=None,
                    repositorio=REPOSITORIO_CANONICO,
                    titulo="Item corrompido",
                    detalhes="Item da lista do Project não é um objeto JSON válido.",
                    timestamp_utc=agora,
                    dados_extras={},
                )
                eventos_gerados.append(evento)
                continue

            content = item.get("content")
            if not isinstance(content, dict):
                continue

            # Apenas itens do tipo 'Issue' e pertencentes ao repositório oficial
            tipo_item = content.get("type")
            repo_item = content.get("repository")

            if tipo_item != "Issue" or repo_item != REPOSITORIO_CANONICO:
                continue

            numero_issue = content.get("number")
            titulo_issue = content.get("title", f"Issue #{numero_issue}")
            url_issue = content.get("url", "")

            # Validação de integridade do número da Issue
            if not isinstance(numero_issue, int) or numero_issue <= 0:
                evento = EventoSentinela(
                    tipo_evento="INVALID_IGNORED",
                    numero_issue=None,
                    repositorio=str(repo_item),
                    titulo=str(titulo_issue),
                    detalhes="Número de Issue inválido ou não-positivo.",
                    timestamp_utc=agora,
                    dados_extras={"item_bruto": item},
                )
                eventos_gerados.append(evento)
                continue

            # Validação de duplicidade na mesma fotografia
            if numero_issue in issues_vistas:
                evento = EventoSentinela(
                    tipo_evento="DUPLICATE_IGNORED",
                    numero_issue=numero_issue,
                    repositorio=str(repo_item),
                    titulo=str(titulo_issue),
                    detalhes=f"Issue #{numero_issue} duplicada detectada na mesma consulta do Project.",
                    timestamp_utc=agora,
                    dados_extras={},
                )
                eventos_gerados.append(evento)
                continue

            issues_vistas.add(numero_issue)

            # Validação da URL canônica
            url_esperada = f"https://github.com/{REPOSITORIO_CANONICO}/issues/{numero_issue}"
            if url_issue != url_esperada:
                evento = EventoSentinela(
                    tipo_evento="INVALID_IGNORED",
                    numero_issue=numero_issue,
                    repositorio=str(repo_item),
                    titulo=str(titulo_issue),
                    detalhes=f"URL '{url_issue}' divergente da URL oficial esperada '{url_esperada}'.",
                    timestamp_utc=agora,
                    dados_extras={},
                )
                eventos_gerados.append(evento)
                continue

            # Verificação de labels estruturadas
            labels = item.get("labels", [])
            if not isinstance(labels, list) or not all(isinstance(l, str) for l in labels):
                evento = EventoSentinela(
                    tipo_evento="INVALID_IGNORED",
                    numero_issue=numero_issue,
                    repositorio=str(repo_item),
                    titulo=str(titulo_issue),
                    detalhes=f"Issue #{numero_issue} possui campo 'labels' inválido ou corrompido.",
                    timestamp_utc=agora,
                    dados_extras={},
                )
                eventos_gerados.append(evento)
                continue

            # Exige etiqueta ch:workflow para elegibilidade no fluxo
            if "ch:workflow" not in labels:
                evento = EventoSentinela(
                    tipo_evento="NO_WORKFLOW_IGNORED",
                    numero_issue=numero_issue,
                    repositorio=str(repo_item),
                    titulo=str(titulo_issue),
                    detalhes=f"Issue #{numero_issue} sem etiqueta 'ch:workflow'; mantida inalterada.",
                    timestamp_utc=agora,
                    dados_extras={"labels": labels},
                )
                eventos_gerados.append(evento)
                continue

            # Tarefa elegível identificada com sucesso
            evento = EventoSentinela(
                tipo_evento="DISCOVERED",
                numero_issue=numero_issue,
                repositorio=str(repo_item),
                titulo=str(titulo_issue),
                detalhes=f"Issue #{numero_issue} reconhecida como candidata a missão.",
                timestamp_utc=agora,
                dados_extras={
                    "labels": labels,
                    "url": url_issue,
                    "origem": origem,
                },
            )
            eventos_gerados.append(evento)

            # Registro opcional em trilha de auditoria
            if self.auditoria:
                self.auditoria.registrar_evento(
                    run_id=f"discovery-issue-{numero_issue}",
                    mission_id=f"ISSUE-{numero_issue}",
                    mission_digest="N/A",
                    executor="sentinela",
                    origem_dados=origem,
                    estado_anterior="N/A",
                    estado_posterior="DISCOVERED",
                    resultado_final="DESCOBERTO",
                )

        # Encerra estritamente sem loops e sem acionamento de workers
        return eventos_gerados
