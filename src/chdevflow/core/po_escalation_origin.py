"""F7 V1: admissao de origem GH LIVE, independente do ambiente do executor.

A origem so pode ser uma execucao de PRODUTOR V1 aprovada na main.
Nao aceita recibos de sonda, origem local, repositorio diferente ou ZIP sem
metadados GH e digest. Este modulo NAO cria produtor V1, nem autoriza POST.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

from chdevflow.core.po_escalation import REPO

REPOSITORY_ID = 1424359000
V1_PRODUCER_PATH = ".github/workflows/f7-v1-producer.yml"
MAX_ARCHIVE = 2_000_000
V1_ORIGIN = re.compile(
    r"^github-actions:v1:([1-9][0-9]{0,18}):([1-9][0-9]{0,8}):"
    r"([1-9][0-9]{0,18}):(sha256:[0-9a-f]{64})$"
)


class ProducerOriginError(ValueError):
    """Prova de origem de outbox V1 recusada; fail-closed."""


def verify_v1_producer_origin(
    origin: str, *, producer_sha: str, workflow_id: int,
    api: Callable[[str], dict], archive: Callable[[str], bytes],
) -> dict[str, Any]:
    """Compara recibo assinado com execucao e artefato GH ao vivo.

    A funcao exige origem v1, metadados de run/artefato inteiros,
    workflow fixo, tentativa atual, digest e repositorio oficial. A
    confianca nos endpoints GH depende de credenciais e host confiaveis.
    """
    if (not isinstance(origin, str) or not V1_ORIGIN.fullmatch(origin)
            or not isinstance(producer_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", producer_sha)
            or type(workflow_id) is not int or workflow_id < 1):
        raise ProducerOriginError("Origem V1/identidade do produtor ausente")
    match = V1_ORIGIN.fullmatch(origin)
    assert match is not None
    run_id, attempt, artifact_id = (int(item) for item in match.groups()[:3])
    digest = match.group(4)
    run = api(f"repos/{REPO}/actions/runs/{run_id}")
    if not isinstance(run, dict):
        raise ProducerOriginError("Run GitHub V1 nao verificavel")
    source = run.get("repository")
    head_source = run.get("head_repository")
    if (run.get("id") != run_id
            or run.get("workflow_id") != workflow_id
            or run.get("path") not in (V1_PRODUCER_PATH, V1_PRODUCER_PATH + "@refs/heads/main")
            or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != "main"
            or run.get("head_sha") != producer_sha
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("run_attempt") != attempt
            or not isinstance(source, dict) or source.get("id") != REPOSITORY_ID
            or not isinstance(head_source, dict) or head_source.get("id") != REPOSITORY_ID):
        raise ProducerOriginError("Run V1 diverge de workflow, SHA ou tentativa autorizados")
    artifact = api(f"repos/{REPO}/actions/artifacts/{artifact_id}")
    if not isinstance(artifact, dict):
        raise ProducerOriginError("Artefato V1 nao verificavel")
    binding = artifact.get("workflow_run")
    if (not isinstance(binding, dict)
            or artifact.get("id") != artifact_id
            or artifact.get("name") != f"f7-v1-evidence-{run_id}-{attempt}"
            or artifact.get("digest") != digest
            or artifact.get("expired") is not False
            or binding.get("id") != run_id
            or binding.get("head_branch") != "main"
            or binding.get("head_sha") != producer_sha
            or binding.get("repository_id") != REPOSITORY_ID
            or binding.get("head_repository_id") != REPOSITORY_ID):
        raise ProducerOriginError("Artefato V1 nao corresponde ao produtor LIVE")
    data = archive(f"repos/{REPO}/actions/artifacts/{artifact_id}/zip")
    if (not isinstance(data, bytes) or not 0 < len(data) <= MAX_ARCHIVE
            or "sha256:" + hashlib.sha256(data).hexdigest() != digest):
        raise ProducerOriginError("ZIP do artefato V1 diverge do digest GitHub")
    # Segunda consulta: run_attempt pode mudar durante o readback.
    repeated = api(f"repos/{REPO}/actions/runs/{run_id}")
    if (not isinstance(repeated, dict)
            or repeated.get("run_attempt") != attempt
            or repeated.get("head_sha") != producer_sha
            or repeated.get("status") != "completed"
            or repeated.get("conclusion") != "success"):
        raise ProducerOriginError("Origem V1 alterada durante verificacao")
    return {
        "run_id": run_id, "run_attempt": attempt, "artifact_id": artifact_id,
        "artifact_digest": digest, "workflow_id": workflow_id,
        "producer_sha": producer_sha,
    }
