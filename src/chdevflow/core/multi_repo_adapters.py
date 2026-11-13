"""Adaptadores de agentes com arquitetura real e trava rigorosa de desativação por padrão.

Implementa os requisitos de contenção e segurança da missão CH-AUTO-MULTI-01:
- EXECUCAO_AUTONOMA_HABILITADA = False permanente nesta fase.
- Qualquer tentativa de acionamento real sem autorização explícita do PO é
  interrompida imediatamente com ExecucaoAutonomaNaoAutorizadaErro.
- Suporte a execução em modo DRY_RUN inteiramente inerte.
- Sanitização determinística de saídas e logs contra vazamento de segredos.
- Reutilização dos contratos da Sentinela (ContratoWorkerResultado).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from ch_sentinela.config import (
    CUSTO_ADICIONAL_PERMITIDO_BRL,
    LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    SCHEMA_WORKER_VERSAO,
)
from ch_sentinela.contracts import ContratoWorkerResultado
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
)
from chdevflow.adapters.base import sanitize_output
from chdevflow.core.dry_run_dispatcher import FixtureTrace, NormalizedTrace


# TRAVA IRREVOGÁVEL DE SEGURANÇA DA FASE CH-AUTO-MULTI-01
# Qualquer alteração deste valor requer autorização explícita e nominal do PO em nova Issue.
EXECUCAO_AUTONOMA_HABILITADA: bool = False

_PADRAO_RECUSA = re.compile(
    r"permission denied|access denied|permiss[aã]o negada|not authorized|unauthorized",
    re.IGNORECASE,
)
_PADRAO_ERRO = re.compile(
    r"\berror\b|\bfatal\b|\bfailed\b|\berro\b|\bfalhou\b",
    re.IGNORECASE,
)
_PADRAO_INJECAO = re.compile(
    r"ignore (?:as |the )?(?:regras|instru[cç][oõ]es|policy|rules)|"
    r"bypass (?:sandbox|policy|rules)|(?:publique|print|expose) (?:o )?token",
    re.IGNORECASE,
)


class ExecucaoAutonomaNaoAutorizadaErro(RuntimeError):
    """Exceção levantada quando se tenta acionar um agente com a trava de segurança ativa."""


class AdaptadorAgenteBase:
    """Classe base para adaptadores de agentes com salvaguardas rigorosas."""

    nome_executor: str = ""
    marcador_conclusao: str = ""

    def __init__(self) -> None:
        self.bloqueio_ativo: bool = not EXECUCAO_AUTONOMA_HABILITADA

    def executar_missao(
        self,
        run_id: str,
        repositorio: str,
        issue_number: int,
        caminho_worktree: Path,
        instrucao: str,
        sha_baseline: str,
        timeout_segundos: int = LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    ) -> ContratoWorkerResultado:
        """Tentativa de execução real de agente no host.

        Fail-closed: Enquanto EXECUCAO_AUTONOMA_HABILITADA for False, bloqueia incondicionalmente.

        Raises:
            ExecucaoAutonomaNaoAutorizadaErro: Sempre levantada enquanto a execução autônoma estiver desativada.
        """
        if not EXECUCAO_AUTONOMA_HABILITADA:
            raise ExecucaoAutonomaNaoAutorizadaErro(
                f"Execução autônoma de agentes desativada na fase CH-AUTO-MULTI-01! "
                f"Tentativa de acionar executor '{self.nome_executor}' bloqueada com segurança. "
                f"A operação automática futura dependerá de nova autorização explícita do PO."
            )

        # Caso futuro em que o PO autorizar: este método exigirá novo gate.
        raise NotImplementedError("Execução real ainda não habilitada pelo PO.")

    def executar_dry_run(
        self, run_id: str, trace_simulado: FixtureTrace | None = None
    ) -> NormalizedTrace:
        """Executa um ciclo em modo DRY-RUN estritamente inerte, sem tocar em processos reais.

        Args:
            run_id: Identificador da execução.
            trace_simulado: Dados simulados opcionais para teste.

        Returns:
            NormalizedTrace com o resultado normalizado e verificado.
        """
        if trace_simulado is None:
            # Traço inerte padrão de prévia
            trace_simulado = FixtureTrace(
                stdout=(
                    json.dumps(
                        {
                            "type": self.marcador_conclusao,
                            "result": f"Dry-run simulado inerte com sucesso para {self.nome_executor}.",
                        }
                    ),
                ),
                stderr=(),
                exit_code=0,
                elapsed_seconds=1,
            )

        return self.normalizar_saida(trace_simulado, run_id)

    def normalizar_saida(self, trace: FixtureTrace, run_id: str) -> NormalizedTrace:
        """Normaliza e sanitiza a saída do agente tratando saídas como dados não confiáveis."""
        if not isinstance(trace, FixtureTrace):
            raise TypeError("A entrada deve ser uma FixtureTrace.")

        events: list[dict[str, str]] = []
        malformed = False
        completed = False
        refused = False
        erro_evento = False
        injection = False

        for line in trace.stdout:
            try:
                data = json.loads(line)
                if not isinstance(data, dict) or not isinstance(data.get("type"), str):
                    raise ValueError("Evento sem type")
                kind = data["type"]
                mensagem = sanitize_output(str(data.get("message", data.get("result", ""))))[:500]
                events.append({"type": sanitize_output(kind)[:100], "message": mensagem})

                completed |= (kind == self.marcador_conclusao and data.get("is_error") is not True)
                refused |= bool(_PADRAO_RECUSA.search(line))
                injection |= bool(_PADRAO_INJECAO.search(mensagem))
                erro_evento |= (
                    kind in {"error", "turn.failed"}
                    or data.get("is_error") is True
                    or bool(_PADRAO_ERRO.search(mensagem))
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                malformed = True
                events.append({"type": "malformed", "message": "JSONL inválido ou parcial"})

        refused |= any(_PADRAO_RECUSA.search(line) for line in trace.stderr)
        erro_evento |= any(_PADRAO_ERRO.search(line) for line in trace.stderr)

        if not trace.cli_present:
            status, reason = "BLOCKED", "CLI do agente ausente no ambiente"
        elif trace.crashed:
            status, reason = "INDETERMINATE", "Processo terminou de forma inesperada (crash)"
        elif trace.cancelled:
            status, reason = "CANCELLED", "Execução cancelada pelo operador"
        elif trace.elapsed_seconds > LIMITE_TEMPO_EXECUCAO_SEGUNDOS:
            status, reason = "TIMED_OUT", f"Tempo limite de {LIMITE_TEMPO_EXECUCAO_SEGUNDOS}s excedido"
        elif refused:
            status, reason = "BLOCKED", "Permissão negada na saída do processo"
        elif injection:
            status, reason = "BLOCKED", "Tentativa de injeção de instruções detectada na saída"
        elif malformed:
            status, reason = "BLOCKED", "JSONL inválido ou corrompido"
        elif trace.stderr or erro_evento or trace.exit_code != 0 or not completed:
            status, reason = "BLOCKED", "Saída incompleta, erro retornado ou marcador de conclusão ausente"
        else:
            status, reason = "COMPLETED", "Simulação concluída com sucesso; zero execução autônoma real"

        resultado = ContratoWorkerResultado(
            schema=SCHEMA_WORKER_VERSAO,
            run_id=run_id,
            executor=self.nome_executor,
            status=status,
            exit_code=trace.exit_code,
            artifacts=[],
            tests=[],
            cost={"currency": "BRL", "additional": 0.0, "verified": True},
            event_log_ref=f"fixture://{run_id}/{self.nome_executor}",
        )
        return NormalizedTrace(status, reason, tuple(events), resultado)


class AdaptadorAGY(AdaptadorAgenteBase):
    """Adaptador para o agente AGY (Antigravity Peão)."""

    nome_executor = "agy"
    marcador_conclusao = "result"


class AdaptadorCodex(AdaptadorAgenteBase):
    """Adaptador para o agente Codex."""

    nome_executor = "codex"
    marcador_conclusao = "turn.completed"


_ADAPTADORES_DISPONIVEIS: dict[str, AdaptadorAgenteBase] = {
    "agy": AdaptadorAGY(),
    "codex": AdaptadorCodex(),
}


def obter_adaptador(nome_executor: str) -> AdaptadorAgenteBase:
    """Retorna o adaptador correspondente ao nome do agente.

    Args:
        nome_executor: Nome do agente ('agy' ou 'codex').

    Raises:
        ViolacaoPoliticaSegurancaErro: Se o executor for desconhecido.
    """
    normalizado = nome_executor.strip().lower()
    if normalizado not in _ADAPTADORES_DISPONIVEIS:
        raise ViolacaoPoliticaSegurancaErro(
            f"Executor '{nome_executor}' não reconhecido! "
            f"Adaptadores suportados: {tuple(_ADAPTADORES_DISPONIVEIS.keys())}."
        )
    return _ADAPTADORES_DISPONIVEIS[normalizado]
