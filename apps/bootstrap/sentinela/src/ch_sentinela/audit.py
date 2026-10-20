"""Sistema de auditoria local em formato JSONL (Append-Only).

Registra trilhas imutáveis e sanitizadas de cada evento da execução,
garantindo rastreabilidade sem exposição de segredos e sem sobrescrita.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ch_sentinela.config import (
    NOME_ARQUIVO_AUDITORIA,
    obter_diretorio_dados,
)
from ch_sentinela.security.policies import sanitizar_texto_segredos


@dataclass(frozen=True)
class EventoAuditoria:
    """Estrutura imutável de um evento de auditoria gravado no arquivo JSONL."""

    timestamp_utc: str
    run_id: str
    mission_id: str
    mission_digest: str
    executor: str
    origem_dados: str
    estado_anterior: str
    estado_posterior: str
    duracao_segundos: float
    testes_realizados: list[dict[str, Any]]
    bloqueios_erros: list[str]
    resultado_final: str

    def para_dicionario(self) -> dict[str, Any]:
        """Converte o evento para dicionário serializável."""
        return asdict(self)


class Auditoria:
    """Gerencia a emissão e gravação estritamente incremental (append-only) de eventos."""

    def __init__(self, caminho_arquivo: Path | None = None) -> None:
        """Inicializa a auditoria.

        Args:
            caminho_arquivo: Caminho opcional do arquivo JSONL (útil para testes isolados).
        """
        if caminho_arquivo is not None:
            self.caminho_arquivo = caminho_arquivo
        else:
            self.caminho_arquivo = obter_diretorio_dados() / NOME_ARQUIVO_AUDITORIA

    def registrar_evento(
        self,
        run_id: str,
        mission_id: str,
        mission_digest: str,
        executor: str,
        origem_dados: str,
        estado_anterior: str,
        estado_posterior: str,
        duracao_segundos: float = 0.0,
        testes_realizados: list[dict[str, Any]] | None = None,
        bloqueios_erros: list[str] | None = None,
        resultado_final: str = "EM_ANDAMENTO",
    ) -> EventoAuditoria:
        """Registra um novo evento no arquivo de auditoria em modo append-only.

        Aplica sanitização em todos os campos de texto e garante permissões restritas (0o600).

        Args:
            run_id: Identificador da execução.
            mission_id: Identificador da missão.
            mission_digest: Hash canônico da missão.
            executor: Executor responsável (ex: 'fake').
            origem_dados: Fonte da leitura (ex: 'FIXTURE_OFFLINE', 'LIVE_GITHUB').
            estado_anterior: Estado de origem da máquina de estados.
            estado_posterior: Novo estado atingido.
            duracao_segundos: Tempo transcorrido até o evento.
            testes_realizados: Lista de verificações e evidências de testes.
            bloqueios_erros: Lista de erros ou bloqueios ocorridos.
            resultado_final: Status final ou situacional da execução.

        Returns:
            O EventoAuditoria gravado.
        """
        agora = datetime.now(timezone.utc).isoformat()

        # Sanitiza strings de erros e bloqueios
        erros_limpos = [
            sanitizar_texto_segredos(str(e)) for e in (bloqueios_erros or [])
        ]

        evento = EventoAuditoria(
            timestamp_utc=agora,
            run_id=sanitizar_texto_segredos(run_id),
            mission_id=sanitizar_texto_segredos(mission_id),
            mission_digest=sanitizar_texto_segredos(mission_digest),
            executor=sanitizar_texto_segredos(executor),
            origem_dados=sanitizar_texto_segredos(origem_dados),
            estado_anterior=estado_anterior,
            estado_posterior=estado_posterior,
            duracao_segundos=round(duracao_segundos, 3),
            testes_realizados=testes_realizados or [],
            bloqueios_erros=erros_limpos,
            resultado_final=resultado_final,
        )

        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)

        linha = json.dumps(evento.para_dicionario(), ensure_ascii=False) + "\n"

        # Modo estritamente 'a' (append), garantindo que nunca sobrescreva dados anteriores
        with open(self.caminho_arquivo, "a", encoding="utf-8") as f:
            f.write(linha)

        # Ajusta permissões do arquivo para leitura/escrita apenas pelo usuário proprietário (0o600)
        try:
            os.chmod(self.caminho_arquivo, 0o600)
        except OSError:
            pass  # Em alguns ambientes virtuais ou sistemas de arquivos pode ser no-op

        return evento

    def ler_eventos(self, run_id_filtro: str | None = None) -> list[dict[str, Any]]:
        """Lê os eventos persistidos no arquivo JSONL.

        Args:
            run_id_filtro: Opcional, filtra eventos apenas do run_id informado.

        Returns:
            Lista de dicionários de eventos em ordem cronológica.
        """
        if not self.caminho_arquivo.exists():
            return []

        eventos = []
        with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
            for linha in f:
                linha_limpa = linha.strip()
                if not linha_limpa:
                    continue
                try:
                    evento = json.loads(linha_limpa)
                    if run_id_filtro is None or evento.get("run_id") == run_id_filtro:
                        eventos.append(evento)
                except json.JSONDecodeError:
                    continue

        return eventos
