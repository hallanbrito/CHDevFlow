"""CCC-01: um piloto manual com no maximo tres AGY e duas devolucoes.

O ciclo nunca usa um veredito falso ou erro de infraestrutura para continuar.
Cada tentativa e um laboratorio F5 fresco; um run existente NAO e reiniciado
automaticamente para evitar gasto/reexecucao duplicada apos crash.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from chdevflow.core.experimental_pilot import (
    ACCEPTANCE_CCC, MISSION, SOURCE, LabResult, _clean, _files, _validate_estoque_ast,
    run_local_pilot,
)

MAX_AGY_ATTEMPTS = 3
MAX_RETURNS = 2
_TECHNICAL = frozenset(("CODEX_REPROVOU", "TESTES_REPROVADOS"))
_INITIAL_FEEDBACK = (
    "Contrato adicional obrigatorio: tipo de movimentacao deve ser string "
    "real. Valide type(tipo) is str antes de comparar com 'entrada'/'saida'. "
    "Objetos com __eq__ enganoso devem gerar ValueError; nao contorne testes."
)


@dataclass
class CycleReport:
    status: str = "INICIADO"
    execution_id: str = ""
    workspace: str = ""
    evidence_dir: str = ""
    max_attempts: int = MAX_AGY_ATTEMPTS
    max_returns: int = MAX_RETURNS
    returns_used: int = 0
    attempts: list[dict] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    cost_verified: bool = False
    os_isolation_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _save(evidence: Path, report: CycleReport) -> None:
    """Write-ahead state: nunca renomear uma tentativa para pendente silenciosamente."""
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    temporary = evidence / "execucao.json.tmp"
    with temporary.open("w", encoding="utf-8") as out:
        out.write(payload)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, evidence / "execucao.json")
    lines = [
        "# CHDevFlow — CCC-01 / ciclo de correcao controlada",
        "",
        f"Execucao: {report.execution_id}",
        f"Estado: {report.status}",
        f"Tentativas AGY: {len(report.attempts)}/{report.max_attempts}",
        f"Devolucoes: {report.returns_used}/{report.max_returns}",
        "Custo e sandbox de SO nao comprovados.",
        "",
        "## Historico (logs completos em cada attempt-NN)",
    ]
    for attempt in report.attempts:
        lines.append(
            f"- {attempt['number']}/3: {attempt['status']} | "
            f"tipo={attempt.get('failure_kind', 'N/D')} | "
            f"Codex={attempt.get('codex_verdict', 'NAO_EXECUTADO')} | "
            f"SHA={attempt.get('code_sha256') or 'N/D'}"
        )
    lines.extend(["", "## Achados", *[f"- {x}" for x in report.findings],
                  "", "Nao executa merge, deploy, cron nem altera Project #2."])
    (evidence / "RELATORIO_COMPLETO_CH1.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def _feedback_from_attempt(*, attempt: int, workspace: Path,
                           evidence: Path, result: LabResult,
                           execution_id: str) -> tuple[str, str]:
    """Devolve o proprio codigo + relatorio autentico. Nunca modifica teste."""
    found = _files(workspace)
    if SOURCE not in found or set(found) != {
        "mission.txt", "tests/test_acceptance.py", SOURCE
    }:
        raise ValueError("Retorno inseguro: escopo do ultimo laboratorio foi alterado")
    source = found[SOURCE].decode("utf-8")
    _validate_estoque_ast(source)
    sha = hashlib.sha256(found[SOURCE]).hexdigest()
    if result.code_sha256 != sha:
        raise ValueError("Retorno inseguro: hash do codigo divergiu do dossie")
    if (workspace / "tests" / "test_acceptance.py").read_text(
        encoding="utf-8") != ACCEPTANCE_CCC:
        raise ValueError("Retorno inseguro: aceite independente alterado")
    if (workspace / "mission.txt").read_text(encoding="utf-8") != MISSION:
        raise ValueError("Retorno inseguro: missao original alterada")
    testlog = evidence / "logs_testes.txt"
    codexlog = evidence / "auditoria_codex.md"
    if result.failure_kind == "CODEX_REPROVOU" and not codexlog.is_file():
        raise ValueError("Retorno inseguro: veto do Codex sem parecer final")
    if result.failure_kind == "TESTES_REPROVADOS" and not testlog.is_file():
        raise ValueError("Retorno inseguro: falha de teste sem log")
    audit = _clean(codexlog.read_text(encoding="utf-8"))[-5000:] if codexlog.is_file() else "Codex nao executado"
    tests = _clean(testlog.read_text(encoding="utf-8"))[-3500:] if testlog.is_file() else "Sem testes"
    feedback = (
        _INITIAL_FEEDBACK + "\n"
        f"EXECUTION_ID={execution_id} | tentativa anterior={attempt}/3 | "
        f"devolucao={attempt}/2 | SHA256={sha}\n"
        "Corrija o modulo anterior, sem editar os testes independentes. "
        "Preserve funcoes e assinatura. Retorne o modulo Python completo.\n"
        f"RESULTADO DOS TESTES:\n{tests}\n"
        f"PARECER FINAL DO CODEX:\n{audit}\n"
    )
    return source, feedback[:11000]


def run_controlled_pilot(*, workspace: Path, evidence: Path,
                         accepted: bool, timeout: int = 480) -> CycleReport:
    """Rodada unica opt-in, no maximo 3 AGY + 3 Codex, sem loop de infraestrutura.

    Timeout e o teto TOTAL das tentativas, nao por agente/tentativa.
    Qualquer pasta ja existente bloqueia (nao ha replays nem reinicio
    automatico de tentativas com cobranca potencial).
    """
    if not accepted:
        raise PermissionError("Aceite --i-accept-local-risk obrigatorio")
    if type(timeout) is not int or not 120 <= timeout <= 900:
        raise ValueError("Tempo TOTAL permitido: 120 a 900 segundos")
    workspace, evidence = workspace.expanduser().absolute(), evidence.expanduser().absolute()
    if workspace == evidence or workspace in evidence.parents or evidence in workspace.parents:
        raise ValueError("Workspace e evidencia nao podem ser aninhados")
    for path in (workspace, evidence):
        if path.exists() or path.is_symlink():
            raise ValueError("Recusa reutilizar execucao anterior; nao repetir cobrancas")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise ValueError("Pai do laboratorio nao existe ou e link")
    workspace.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    result = CycleReport(execution_id=uuid4().hex, workspace=str(workspace),
                         evidence_dir=str(evidence))
    deadline = time.monotonic() + timeout
    feedback = _INITIAL_FEEDBACK
    previous_source: str | None = None
    _save(evidence, result)

    for attempt in range(1, MAX_AGY_ATTEMPTS + 1):
        remaining = int(deadline - time.monotonic())
        if remaining < 120:
            result.status = "ORCAMENTO_ESGOTADO"
            result.findings.append("Tempo global restante insuficiente para nova tentativa")
            break
        row: dict = {
            "number": attempt,
            "status": "EM_EXECUCAO",
            "workspace": f"attempt-{attempt:02d}",
            "evidence_dir": f"attempt-{attempt:02d}",
            "failure_kind": "NENHUMA",
            "codex_verdict": "NAO_EXECUTADO",
        }
        result.attempts.append(row)
        result.status = "EM_EXECUCAO"
        _save(evidence, result)  # marca chamada iniciada ANTES do subprocesso AGY
        attempt_workspace = workspace / row["workspace"]
        attempt_evidence = evidence / row["evidence_dir"]
        try:
            outcome = run_local_pilot(
                workspace=attempt_workspace, evidence=attempt_evidence,
                accepted=True, timeout=min(remaining, 900),
                feedback=feedback, previous_source=previous_source,
                acceptance_source=ACCEPTANCE_CCC,
            )
            row.update(
                status=outcome.status,
                failure_kind=outcome.failure_kind,
                codex_verdict=outcome.codex_verdict,
                code_sha256=outcome.code_sha256,
                stages=outcome.stages,
                findings=outcome.findings,
                agent_calls=outcome.agent_calls,
            )
        except (ValueError, OSError, UnicodeError) as exc:
            result.status = "BLOQUEADO_INFRA"
            row["status"] = "BLOQUEADO_INFRA"
            result.findings.append(_clean(str(exc)))
            _save(evidence, result)
            break
        _save(evidence, result)

        if (outcome.status == "LAB_APROVADO_AGUARDANDO_CH1"
                and outcome.codex_verdict == "APROVAR_LAB"
                and outcome.stages.get("TESTES") == "PASS"):
            result.status = "APROVADO_AGUARDANDO_CH1"
            break
        if outcome.failure_kind not in _TECHNICAL:
            result.status = "BLOQUEADO_INFRA"
            result.findings.append(
                f"Tentativa {attempt}: falha nao tecnica; proibido retry automatico")
            break
        if attempt == MAX_AGY_ATTEMPTS:
            result.status = "AGUARDANDO_PO"
            result.findings.append(
                "Terceira tentativa reprovada. Sem quarta chamada AGY; revisar dossie.")
            break
        try:
            previous_source, feedback = _feedback_from_attempt(
                attempt=attempt, workspace=attempt_workspace,
                evidence=attempt_evidence, result=outcome,
                execution_id=result.execution_id)
        except (OSError, ValueError, UnicodeError) as exc:
            result.status = "BLOQUEADO_INFRA"
            result.findings.append(_clean(str(exc)))
            break
        (attempt_evidence / "feedback_para_agy.md").write_text(
            _clean(feedback), encoding="utf-8")
        result.returns_used += 1
        result.status = "CORRECAO_PENDENTE"
        _save(evidence, result)

    if result.status in ("INICIADO", "EM_EXECUCAO", "CORRECAO_PENDENTE"):
        result.status = "BLOQUEADO_INFRA"
        result.findings.append("Ciclo encerrado sem estado terminal comprovado")
    _save(evidence, result)
    return result
