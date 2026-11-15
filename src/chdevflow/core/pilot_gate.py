"""CH-PIPE-01/F3 — pré-gate read-only do piloto supervisionado.

Somente verifica evidência PO obtida da API autenticada do GitHub, vinculada
ao digest/escopo/HEAD. O resultado NUNCA concede permissão de executar agentes:
custo independente, lock global, isolamento e novo aceite de piloto ainda
precisam ser comprovados. Nenhum método deste módulo invoca AGY/Codex.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from chdevflow.core.manual_pipeline_runner import Mission, PipelinePlan

OWNER_LOGIN = "hallanbrito"
OWNER_ID = 113695320
REPO = "hallanbrito/CHDevFlow"
DECISION_SCHEMA = "chdevflow.pilot-approval/v1"
COMMENT_PATTERN = re.compile(r"\A```ch-pilot-approval\n(\{[^\x00]*\})\n```\Z", re.S)
HEX_NONCE = re.compile(r"^[a-f0-9]{32}$")
_SHA = re.compile(r"^[a-f0-9]{40}$", re.I)
_EXPECTED_FIELDS = {
    "schema", "decision", "repository", "issue", "mission_id",
    "mission_digest", "baseline_sha", "allowed_paths",
    "timeout_seconds", "max_extra_cost_brl", "nonce", "expires_at",
}


@dataclass(frozen=True)
class PilotGateAssessment:
    status: str
    reason: str
    po_evidence_verified: bool
    cost_proof_verified: bool = False
    isolation_verified: bool = False
    replay_lock_verified: bool = False
    agents_authorized: bool = False
    approval_comment_id: int | None = None
    mission_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Timestamp inválido")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp sem fuso")
    return dt.astimezone(timezone.utc)


def assess_po_comment(
    mission: Mission, plan: PipelinePlan, comment: dict[str, Any],
    comment_id: int, *, now: datetime | None = None,
) -> PilotGateAssessment:
    """Inspeciona payload fornecido pelo GitHub. Não autentica JSON isolado.

    A proveniência depende do chamador usar fetch_live_po_comment contra
    a API GitHub com identidade verificada. Fixtures são apenas para teste.
    """
    digest = mission.digest
    def blocked(reason: str, status: str = "BLOQUEADO") -> PilotGateAssessment:
        return PilotGateAssessment(status, reason, False,
                                   approval_comment_id=comment_id,
                                   mission_digest=digest)
    if not isinstance(comment, dict):
        return blocked("Resposta da API inválida")
    if type(comment_id) is not int or comment_id < 1:
        return blocked("ID de comentário inválido")
    if plan.state != "PLANEJADO_AGUARDANDO_GATE" or plan.mission_digest != digest:
        return blocked("Missão sem plano válido/atual")
    if mission.repository != REPO or mission.issue < 1 or mission.base_sha != mission.base_sha.lower():
        return blocked("Repositório, Issue ou SHA fora do piloto")
    try:
        user = comment["user"]
        if (not isinstance(user, dict)
                or user.get("login") != OWNER_LOGIN
                or type(user.get("id")) is not int or user["id"] != OWNER_ID
                or comment.get("author_association") != "OWNER"):
            raise ValueError("Autor do comentário não é o PO verificado")
        if comment.get("id") != comment_id or type(comment.get("id")) is not int:
            raise ValueError("ID de comentário divergente")
        expected_issue = f"https://api.github.com/repos/{REPO}/issues/{mission.issue}"
        expected_comment = f"https://api.github.com/repos/{REPO}/issues/comments/{comment_id}"
        if comment.get("issue_url") != expected_issue or comment.get("url") != expected_comment:
            raise ValueError("Comentário pertence a outra Issue/repositório")
        created = _parse_utc(comment["created_at"])
        updated = _parse_utc(comment["updated_at"])
        now_utc = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
        if updated != created or created > now_utc + timedelta(minutes=1):
            raise ValueError("Comentário editado ou data inconsistente")
        body = comment.get("body")
        match = COMMENT_PATTERN.fullmatch(body) if isinstance(body, str) else None
        if match is None or len(body) > 4096:
            raise ValueError("Formato de decisão inválido")
        payload = json.loads(match.group(1))
        if not isinstance(payload, dict) or set(payload) != _EXPECTED_FIELDS:
            raise ValueError("Campos de autorização inesperados/ausentes")
        if payload.get("schema") != DECISION_SCHEMA or payload.get("decision") != "APPROVE_ONE_MANUAL_PILOT":
            raise ValueError("Decisão do PO não corresponde ao contrato")
        if (payload.get("repository") != mission.repository
                or type(payload.get("issue")) is not int
                or payload["issue"] != mission.issue
                or payload.get("mission_id") != mission.mission_id
                or payload.get("mission_digest") != digest
                or payload.get("baseline_sha") != mission.base_sha
                or payload.get("allowed_paths") != list(mission.allowed_paths)
                or type(payload.get("timeout_seconds")) is not int
                or payload["timeout_seconds"] != mission.timeout_seconds
                or type(payload.get("max_extra_cost_brl")) is not int
                or payload["max_extra_cost_brl"] != 0
                or not isinstance(payload.get("nonce"), str)
                or HEX_NONCE.fullmatch(payload["nonce"]) is None):
            raise ValueError("Missão, digest, escopo, SHA, timeout, custo ou nonce divergentes")
        expires = _parse_utc(payload["expires_at"])
        if not (created <= now_utc < expires <= created + timedelta(hours=24)):
            raise ValueError("Decisão expirada ou validade superior a 24 horas")
    except (ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError) as exc:
        return blocked(str(exc)[:180])
    # Autoria/escopo verificados pelo GitHub NÃO provam gratuidade, sandbox,
    # ausência de replay ou autorização para autoexecução.
    return PilotGateAssessment(
        status="BLOQUEADO_CUSTO",
        reason="PO verificável; custo/licença independentes, sandbox e reserva antirreplay pendentes",
        po_evidence_verified=True,
        approval_comment_id=comment_id,
        mission_digest=digest,
    )


def fetch_live_po_comment(
    mission: Mission, comment_id: int, *,
    runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Consulta Github via `gh api` read-only, sem seguir URLs arbitrárias."""
    if (mission.repository != REPO or type(mission.issue) is not int
            or mission.issue < 1 or type(comment_id) is not int or comment_id < 1):
        raise ValueError("Repositório/Issue/comentário inválido")
    api_path = f"repos/{REPO}/issues/comments/{comment_id}"
    if runner is None:
        runner = subprocess.run
    result = runner(
        ["gh", "api", "-H", "Accept: application/vnd.github+json", api_path],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if result.returncode != 0 or len(result.stdout or "") > 64_000:
        raise ValueError("GitHub indisponível ou leitura recusada")
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("Resposta GitHub inválida")
    return data


def check_gate_live(mission: Mission, plan: PipelinePlan, comment_id: int,
                    *, runner: Callable[..., Any] | None = None,
                    now: datetime | None = None) -> PilotGateAssessment:
    """Preflight read-only. Erro de acesso ou de formato => BLOQUEADO."""
    try:
        record = fetch_live_po_comment(mission, comment_id, runner=runner)
    except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return PilotGateAssessment(
            status="BLOQUEADO_GITHUB", reason="Decisão PO não verificável ao vivo",
            po_evidence_verified=False, approval_comment_id=comment_id,
            mission_digest=mission.digest,
        )
    return assess_po_comment(mission, plan, record, comment_id, now=now)


def approval_template(mission: Mission, *, nonce: str,
                      expires_at: str) -> str:
    """Gera texto RASCUNHO. NÃO publica comentário, NÃO aprova nada."""
    if not HEX_NONCE.fullmatch(nonce):
        raise ValueError("Nonce deve conter 32 hexadecimais minúsculos")
    expires = _parse_utc(expires_at)
    payload = {
        "schema": DECISION_SCHEMA,
        "decision": "APPROVE_ONE_MANUAL_PILOT",
        "repository": mission.repository,
        "issue": mission.issue,
        "mission_id": mission.mission_id,
        "mission_digest": mission.digest,
        "baseline_sha": mission.base_sha,
        "allowed_paths": list(mission.allowed_paths),
        "timeout_seconds": mission.timeout_seconds,
        "max_extra_cost_brl": 0,
        "nonce": nonce,
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    return "```ch-pilot-approval\n" + json.dumps(
        payload, sort_keys=True, ensure_ascii=False, indent=2
    ) + "\n```"
