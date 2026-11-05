"""Despacho W2-B inteiramente simulado; nenhuma interface de execução real existe aqui."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any

from ch_sentinela.config import SCHEMA_WORKER_VERSAO
from ch_sentinela.contracts import (
    ContratoAutorizacao,
    ContratoWorkerResultado,
    validar_contrato_missao,
)
from ch_sentinela.security.policies import ViolacaoPoliticaSegurancaErro, validar_sha_commit
from chdevflow.adapters.base import sanitize_output


_LIMITES = {"max_parallel": 1, "timeout_seconds": 900,
            "max_retries_after_diagnosis": 1, "extra_cost_brl": 0}
_RECUSA = re.compile(r"permission denied|access denied|permiss[aã]o negada|not authorized|unauthorized", re.I)
_ERRO = re.compile(r"\berror\b|\bfatal\b|\bfailed\b|\berro\b|\bfalhou\b", re.I)
_INJECAO = re.compile(r"ignore (?:as |the )?(?:regras|instru[cç][oõ]es|policy|rules)|"
                     r"bypass (?:sandbox|policy|rules)|(?:publique|print|expose) (?:o )?token", re.I)


@dataclass(frozen=True)
class FixtureTrace:
    """Saída já capturada em fixture local; nunca contém comando ou processo."""

    stdout: tuple[str, ...]
    stderr: tuple[str, ...] = ()
    exit_code: int = 0
    elapsed_seconds: int = 0
    cancelled: bool = False
    crashed: bool = False
    cli_present: bool = True


@dataclass(frozen=True)
class NormalizedTrace:
    status: str
    reason: str
    events: tuple[dict[str, str], ...]
    worker_result: ContratoWorkerResultado


def _limpar(texto: str) -> str:
    """Reduz a saída não confiável a texto curto sem credenciais conhecidas."""
    return sanitize_output(texto)[:500]


class FakeAdapter:
    """Normaliza somente linhas JSON fornecidas pelo chamador em memória."""

    name = ""
    completion_type = ""

    def normalize(self, trace: FixtureTrace, run_id: str) -> NormalizedTrace:
        if not isinstance(trace, FixtureTrace):
            raise TypeError("A entrada deve ser uma FixtureTrace local.")
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
                # O payload permanece dado, nunca instrução para o dispatcher.
                mensagem = _limpar(str(data.get("message", data.get("result", ""))))
                events.append({"type": _limpar(kind), "message": mensagem})
                completed |= kind == self.completion_type and data.get("is_error") is not True
                refused |= bool(_RECUSA.search(line))
                injection |= bool(_INJECAO.search(mensagem))
                erro_evento |= (kind in {"error", "turn.failed"} or data.get("is_error") is True
                                or bool(_ERRO.search(mensagem)))
            except (TypeError, ValueError, json.JSONDecodeError):
                malformed = True
                events.append({"type": "malformed", "message": "JSONL inválido ou parcial"})
        refused |= any(_RECUSA.search(line) for line in trace.stderr)
        erro_evento |= any(_ERRO.search(line) for line in trace.stderr)
        if not trace.cli_present:
            status, reason = "BLOCKED", "CLI ausente na fixture"
        elif trace.crashed:
            status, reason = "INDETERMINATE", "Crash simulado; reconciliação necessária"
        elif trace.cancelled:
            status, reason = "CANCELLED", "Cancelamento simulado"
        elif trace.elapsed_seconds > 900:
            status, reason = "TIMED_OUT", "Limite simulado de 900 segundos excedido"
        elif refused:
            status, reason = "BLOCKED", "Permissão negada na saída simulada"
        elif injection:
            status, reason = "BLOCKED", "Instrução maliciosa na saída simulada"
        elif malformed:
            status, reason = "BLOCKED", "JSONL inválido ou parcial"
        elif trace.stderr or erro_evento or trace.exit_code != 0 or not completed:
            status, reason = "BLOCKED", "Saída incompleta, erro ou stderr presente"
        else:
            status, reason = "COMPLETED", "Fixture concluída; sem prova de execução real"
        resultado = ContratoWorkerResultado(
            schema=SCHEMA_WORKER_VERSAO, run_id=run_id, executor=self.name,
            status=status, exit_code=trace.exit_code, artifacts=[], tests=[],
            cost={"currency": "BRL", "additional": 0, "verified": False},
            event_log_ref=f"fixture://{run_id}/{self.name}",
        )
        return NormalizedTrace(status, reason, tuple(events), resultado)


class CodexExecFake(FakeAdapter):
    name = "codex_exec"
    completion_type = "turn.completed"


class AgyPrintFake(FakeAdapter):
    name = "agy_print"
    completion_type = "result"


_ADAPTERS = {"codex_exec": CodexExecFake(), "agy_print": AgyPrintFake()}


@dataclass(frozen=True)
class DryRunReport:
    status: str
    reason: str
    mission_digest: str | None
    executor: str | None
    plan: tuple[str, ...]
    run_authorized: bool = False


class DryRunDispatcher:
    """Prévia e reserva *somente em memória*; não possui método de RUN real."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._active: str | None = None
        self._history: dict[str, str] = {}
        self._executors: dict[str, str] = {}
        self._previews: dict[int, tuple[DryRunReport, str, str, str, str, tuple[str, ...]]] = {}
        self._claims: dict[str, tuple[DryRunReport, str | None, bool]] = {}
        self._reasons: dict[str, str] = {}

    def preview(
        self, payload: dict[str, Any], approval_fixture: ContratoAutorizacao | None,
        observed_sha: str, repo_root: Path, *, cost_fixture_verified: bool = False,
        interface_fixture_verified: bool = False,
    ) -> DryRunReport:
        plan = ("Validar missão e fixture de autorização", "Conferir escopo, SHA e limites",
                "Normalizar saída de fixture", "Encerrar em DRY_RUN sem processo externo")
        try:
            if set(payload) - {"schema", "mission_id", "source", "target", "worker",
                                "autonomy", "instruction_ref", "limits", "mission_digest"}:
                raise ValueError("Campo de missão não reconhecido")
            mission = validar_contrato_missao(payload)
            if set(mission.target) - {"repository", "base_sha", "allowed_paths", "blocked_paths"}:
                raise ValueError("Campo de destino não reconhecido")
            if mission.worker not in _ADAPTERS or mission.autonomy != "CH-2":
                raise ValueError("Executor ou autonomia não permitidos para W2-B")
            if mission.limits != _LIMITES or any(type(mission.limits[k]) is not int for k in _LIMITES):
                raise ValueError("Limites D06 devem coincidir exatamente com a política W2-B")
            if validar_sha_commit(observed_sha) != mission.target["base_sha"].lower():
                raise ValueError("Baseline observado diverge da missão")
            if not isinstance(repo_root, Path) or not repo_root.is_dir() or repo_root.is_symlink():
                raise ValueError("Raiz de trabalho inválida ou simbólica")
            for path in mission.target["allowed_paths"]:
                relative = Path(path)
                if relative.is_absolute() or ".." in relative.parts or any(c in path for c in "*?[]"):
                    raise ValueError("Caminho fora do escopo")
                candidate = repo_root
                for part in relative.parts:
                    candidate = candidate / part
                    if candidate.is_symlink():
                        raise ValueError("Symlink no escopo")
                if not candidate.resolve().is_relative_to(repo_root.resolve()):
                    raise ValueError("Escopo escapa da raiz")
            if approval_fixture is None or not isinstance(approval_fixture, ContratoAutorizacao):
                raise ValueError("Gate humano verificável ausente; fixture necessária na simulação")
            if not approval_fixture.is_simulation or approval_fixture.approval_type != "CH2_RUN_APPROVAL":
                raise ValueError("Aprovação real não é processada em W2-B")
            if approval_fixture.issue_ref != str(mission.source["issue"]):
                raise ValueError("Issue da fixture de autorização diverge")
            if not approval_fixture.event_id.startswith("fixture:") or not approval_fixture.approved_at:
                raise ValueError("Revisão da fixture de autorização inválida")
            approval_fixture.validar_contra_missao(mission)
            if not cost_fixture_verified:
                return DryRunReport("BLOQUEADO_CUSTO", "Custo/licença sem prova nem fixture", mission.mission_digest, mission.worker, plan)
            if not interface_fixture_verified:
                raise ValueError("Interface não comprovada por fixture")
            report = DryRunReport("DRY_RUN_ELIGIBLE", "Somente fixture sintética elegível", mission.mission_digest, mission.worker, plan)
            with self._lock:
                # Mantém a referência viva; igualdade de campos ou id reutilizado não autentica a prévia.
                self._previews[id(report)] = (report, str(mission.source["issue"]),
                                              mission.mission_digest, mission.worker,
                                              report.reason, report.plan)
            return report
        except (ValueError, KeyError, TypeError, ViolacaoPoliticaSegurancaErro) as exc:
            return DryRunReport("BLOCKED", _limpar(str(exc)), None, None, plan)

    def reserve_simulation(self, report: DryRunReport, issue_ref: str, attempt: int = 1,
                           diagnosis_ref: str | None = None, retry_fixture_approved: bool = False) -> str:
        """Reserva lógica local; replay devolve o mesmo identificador sem novo trabalho."""
        if type(attempt) is not int or attempt not in (1, 2):
            raise ValueError("Tentativa simulada inválida")
        if attempt == 1 and (diagnosis_ref is not None or retry_fixture_approved):
            raise ValueError("Primeira tentativa não aceita parâmetros de retry")
        if attempt == 2 and (not diagnosis_ref or retry_fixture_approved is not True):
            raise ValueError("Retry exige diagnóstico e nova aprovação simulada")
        with self._lock:
            binding = self._previews.get(id(report))
            if (type(report) is not DryRunReport or binding is None or binding[0] is not report
                    or type(issue_ref) is not str or issue_ref != binding[1]
                    or report.status != "DRY_RUN_ELIGIBLE" or report.mission_digest != binding[2]
                    or report.executor != binding[3] or report.reason != binding[4]
                    or report.plan != binding[5] or report.run_authorized is not False):
                raise ValueError("Prévia ausente, adulterada ou Issue divergente")
            key = f"{binding[1]}:{binding[2]}:{attempt}"
            if key in self._history:
                prior = self._claims[key]
                if prior[0] is not report or prior[1:] != (diagnosis_ref, retry_fixture_approved):
                    raise ValueError("Replay com prévia ou parâmetros divergentes")
                return key
            if self._active is not None:
                raise ValueError("Outra reserva simulada está ativa")
            if attempt == 2:
                previous = f"{binding[1]}:{binding[2]}:1"
                if self._history.get(previous) not in {"BLOCKED", "TIMED_OUT", "CANCELLED", "INDETERMINATE"}:
                    raise ValueError("Tentativa anterior sem falha reconciliada")
            self._active = key
            self._history[key] = "CLAIMED"
            self._executors[key] = binding[3]
            self._claims[key] = (report, diagnosis_ref, retry_fixture_approved)
            self._reasons[key] = "Reserva simulada ativa"
        return key

    def finish_simulation(self, key: str, trace: FixtureTrace) -> NormalizedTrace:
        with self._lock:
            if self._active != key:
                raise ValueError("Reserva não está ativa")
            executor = self._executors[key]
            try:
                result = _ADAPTERS[executor].normalize(trace, key)
                if not isinstance(result, NormalizedTrace):
                    raise TypeError("Resultado normalizado inválido")
            except Exception as exc:
                reason = f"Falha de normalização simulada ({type(exc).__name__}): {_limpar(str(exc))}"
                worker_result = ContratoWorkerResultado(
                    schema=SCHEMA_WORKER_VERSAO, run_id=key, executor=executor,
                    status="INDETERMINATE", exit_code=-1, artifacts=[], tests=[],
                    cost={"currency": "BRL", "additional": 0, "verified": False},
                    event_log_ref=f"fixture://{key}/{executor}",
                )
                result = NormalizedTrace("INDETERMINATE", reason, (), worker_result)
            self._history[key] = result.status
            self._reasons[key] = result.reason
            self._active = None
            return result

    def cancel_simulation(self, key: str) -> None:
        with self._lock:
            if self._active != key:
                raise ValueError("Reserva não está ativa")
            self._history[key] = "CANCELLED"
            self._reasons[key] = "Cancelamento simulado pelo operador"
            self._active = None

    def simulation_status(self, key: str) -> tuple[str, str]:
        """Consulta o estado e o diagnóstico da reserva nesta instância de simulação."""
        with self._lock:
            if key not in self._history:
                raise ValueError("Reserva simulada desconhecida")
            return self._history[key], self._reasons[key]
