"""F7 E3-C5: verificador independente de ORIGEM para futuro atestador V1.

Somente prova de identidade LIVE do produtor; NAO prova missao real.
Sempre falha fechado ate existir contrato de artefato validado (E3-C6).
Nao assina nem publica dados. Zero segredos ou escrita remota.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

REPO = "hallanbrito/CHDevFlow"
REPO_ID = 1424359000
PRODUCER_WORKFLOW_PATH = ".github/workflows/f7-v1-producer.yml"
PO_ID = 113695320
SCHEMA = "CHDEVFLOW-F7-V1-ATTESTOR-ORIGIN/1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
# Politica *versionada*, intencionalmente ausente ate contrato V1 auditado.
PRODUCER_SHA_PIN = ""
PRODUCER_WORKFLOW_ID_PIN = 0
ATTESTOR_SIGNING_ENABLED = False


class AttestorAdmissionError(ValueError):
    """Origem GH V1 insuficiente, nao autorizada ou nao atestavel."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, value in pairs:
        if name in output:
            raise AttestorAdmissionError("JSON de origem com chave duplicada")
        output[name] = value
    return output


def _gh_run(run_id: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com",
             f"repos/{REPO}/actions/runs/{run_id}"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AttestorAdmissionError("Run produtor GH LIVE indisponivel") from exc
    if result.returncode or not 0 < len(result.stdout) <= 150_000:
        raise AttestorAdmissionError("Resposta GH LIVE ausente/excessiva")
    try:
        data = json.loads(result.stdout, object_pairs_hook=_strict_object)
    except (ValueError, UnicodeError) as exc:
        raise AttestorAdmissionError("JSON GH LIVE invalido") from exc
    if not isinstance(data, dict):
        raise AttestorAdmissionError("Run GH LIVE nao e objeto")
    return data


def check_origin(event: dict[str, Any], live: dict[str, Any],
                 *, pinned_sha: str = PRODUCER_SHA_PIN,
                 pinned_workflow_id: int = PRODUCER_WORKFLOW_ID_PIN) -> dict[str, Any]:
    """Verifica EVENTO + segundo readback LIVE; não confere teste AGY/Codex."""
    if (not isinstance(pinned_sha, str) or not SHA40.fullmatch(pinned_sha)
            or type(pinned_workflow_id) is not int or pinned_workflow_id < 1):
        raise AttestorAdmissionError("Pin do produtor V1 nao provisionado")
    if not isinstance(event, dict) or not isinstance(live, dict):
        raise AttestorAdmissionError("Origem V1 nao e objeto")
    event_run = event.get("workflow_run")
    if not isinstance(event_run, dict):
        raise AttestorAdmissionError("Evento sem run GH")
    fields = ("id", "workflow_id", "head_sha", "head_branch",
              "event", "run_attempt", "status", "conclusion")
    for field in fields:
        if event_run.get(field) != live.get(field):
            raise AttestorAdmissionError("Evento e readback GH LIVE divergentes")
    for field in ("id", "workflow_id", "run_attempt"):
        if type(live.get(field)) is not int or live[field] < 1:
            raise AttestorAdmissionError("Identificador/tentativa GH nao inteiro")
    if (live["workflow_id"] != pinned_workflow_id
            or live.get("head_sha") != pinned_sha
            or live.get("head_branch") != "main"
            or live.get("event") != "workflow_dispatch"
            or live.get("status") != "completed"
            or live.get("conclusion") != "success"
            or live.get("path") not in (
                PRODUCER_WORKFLOW_PATH,
                PRODUCER_WORKFLOW_PATH + "@refs/heads/main",
            )
            or type(live.get("id")) is not int
            or type(live.get("run_attempt")) is not int):
        raise AttestorAdmissionError("Produtor nao corresponde ao workflow protegido")
    for name in ("actor", "triggering_actor"):
        actor = live.get(name)
        if (not isinstance(actor, dict)
                or actor.get("login") != "hallanbrito"
                or type(actor.get("id")) is not int or actor["id"] != PO_ID):
            raise AttestorAdmissionError("Produtor nao foi disparado pelo PO")
    for name in ("repository", "head_repository"):
        record = live.get(name)
        if (not isinstance(record, dict)
                or record.get("full_name") != REPO
                or type(record.get("id")) is not int or record["id"] != REPO_ID):
            raise AttestorAdmissionError("Origem de fork/fora do repositorio")
    event_repo = event.get("repository")
    if (not isinstance(event_repo, dict)
            or type(event_repo.get("id")) is not int
            or event_repo["id"] != REPO_ID):
        raise AttestorAdmissionError("Evento nao foi entregue pelo repositorio alvo")
    return {
        "schema": SCHEMA,
        "producer_run_id": live["id"],
        "producer_attempt": live["run_attempt"],
        "producer_sha": pinned_sha,
        "producer_workflow_id": pinned_workflow_id,
        "state": "ORIGIN_ONLY_NOT_MISSION_ATTESTED",
        "agents_verified": False,
        "outbox_verified": False,
        "signature_emitted": False,
    }


def main() -> int:
    if ATTESTOR_SIGNING_ENABLED:
        raise AttestorAdmissionError("Atestador V1 ainda nao implementa assinatura")
    location = os.environ.get("GITHUB_EVENT_PATH")
    if not location:
        raise AttestorAdmissionError("Arquivo de evento GitHub ausente")
    path = Path(location)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 200_000:
        raise AttestorAdmissionError("Evento GH invalido")
    try:
        event = json.loads(path.read_bytes(), object_pairs_hook=_strict_object)
    except (ValueError, UnicodeError) as exc:
        raise AttestorAdmissionError("Payload do evento GH invalido") from exc
    run = event.get("workflow_run") if isinstance(event, dict) else None
    if not isinstance(run, dict) or type(run.get("id")) is not int:
        raise AttestorAdmissionError("Run de origem nao indicado pelo GitHub")
    live = _gh_run(run["id"])
    origin = check_origin(event, live)
    print(json.dumps(origin, sort_keys=True, separators=(",", ":")), flush=True)
    # O run correto, sozinho, NUNCA concede assinatura: faltam AGY real,
    # logs independentes, bytes da outbox, manifesto e prova do contêiner.
    raise AttestorAdmissionError(
        "Recibo de missao V1 nao verificavel: bloqueio E3-C5 esperado")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AttestorAdmissionError as exc:
        print("E3C5_V1_ATTESTOR_FAIL_CLOSED: " + str(exc), flush=True)
        raise SystemExit(42)
