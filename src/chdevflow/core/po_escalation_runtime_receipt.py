"""F7 E3-C4: prova EXTERNA de consumo de executor em uma missao real.

Sigstore do TAR E3-B prova a origem do BUILD, nao seu uso numa missao.
Para admitir F7 com modo E3-B, exige um recibo de consumo assinado por
workflow atestador independente e ligado a TODOS os hashes do dossie.
Nenhum workflow V1 real esta habilitado nesta entrega. Pins vazios negam tudo.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from chdevflow.core.po_escalation import (
    _evidence_text, _json_unique, _read_evidence_bytes, _safe_file_within,
)
from chdevflow.core.attested_executor import (
    IMAGE_ID, SOURCE_SHA as EXECUTOR_SOURCE_SHA, TAR_SHA256,
)

SCHEMA = "CHDEVFLOW-F7-E3C4-RUNTIME-RECEIPT/1"
REPO = "hallanbrito/CHDevFlow"
REPO_ID = 1424359000
SIGNER = "hallanbrito/CHDevFlow/.github/workflows/f7-v1-attestor.yml"
WORKFLOW_PATH = ".github/workflows/f7-v1-attestor.yml"
RECEIPT_FILE = "f7-runtime-receipt.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
# Apenas PO, apos workflow V1 real, auditoria Codex e aprovacao de pins.
ATTESTOR_SHA_PIN = ""
ATTESTOR_WORKFLOW_ID_PIN = 0
REQUIRED = frozenset({
    "schema", "repository", "repository_id", "execution_id", "mission_id",
    "mission_digest", "producer_run_id", "producer_run_attempt",
    "attestor_run_id", "attestor_run_attempt", "outbox_sha256",
    "files_sha256", "executor_tar_sha256", "executor_image_id",
    "executor_build_sha", "test_mode", "authorization",
})


class ExternalRuntimeReceiptError(ValueError):
    """Sem prova independente do executor consumido nesta missao."""


def _live_attestor_run(run_id: int) -> dict:
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com",
             f"repos/{REPO}/actions/runs/{run_id}"],
            capture_output=True, stdin=subprocess.DEVNULL, check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalRuntimeReceiptError("Atestador GH LIVE indisponivel") from exc
    if result.returncode or len(result.stdout) > 120_000:
        raise ExternalRuntimeReceiptError("Atestador GH LIVE nao acessivel")
    try:
        response = _json_unique(_evidence_text(result.stdout))
    except (ValueError, UnicodeError) as exc:
        raise ExternalRuntimeReceiptError("Resposta do atestador invalida") from exc
    if not isinstance(response, dict):
        raise ExternalRuntimeReceiptError("Run do atestador nao e objeto")
    return response


def _verify_sigstore(payload: bytes, *, sha: str) -> None:
    """Verifica assinatura de bytes congelados em pasta privada, nao path mutavel."""
    with TemporaryDirectory(prefix="ch-f7-e3c4-") as temp:
        file = Path(temp) / RECEIPT_FILE
        file.write_bytes(payload)
        try:
            result = subprocess.run(
                ["gh", "attestation", "verify", str(file),
                 "-R", REPO, "--signer-workflow", SIGNER,
                 "--source-digest", sha, "--source-ref", "refs/heads/main",
                 "--deny-self-hosted-runners"],
                capture_output=True, stdin=subprocess.DEVNULL, check=False,
                timeout=50,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExternalRuntimeReceiptError("Sigstore F7 indisponivel") from exc
        if result.returncode:
            raise ExternalRuntimeReceiptError("Recibo nao possui assinatura Sigstore valida")


def verify_runtime_receipt(root: Path, outbox: dict, provenance: dict) -> dict:
    """Exige recibo assinado, manifesto integro e execucao LIVE atestadora.

    Um log local ou flag booleana nao constitui prova. Falha FECHADO se
    nao existe attestor na main com SHA/ID revisados e assinatura verificavel.
    """
    if (not isinstance(ATTESTOR_SHA_PIN, str) or not SHA40.fullmatch(ATTESTOR_SHA_PIN)
            or type(ATTESTOR_WORKFLOW_ID_PIN) is not int
            or ATTESTOR_WORKFLOW_ID_PIN < 1):
        raise ExternalRuntimeReceiptError("Atestador V1 nao esta pinado/autorizado")
    try:
        raw = _read_evidence_bytes(_safe_file_within(root, RECEIPT_FILE), cap=32000)
        receipt = _json_unique(_evidence_text(raw))
        original = _read_evidence_bytes(
            _safe_file_within(root, "escalonamento_po.json"), cap=15000)
        loaded = _json_unique(_evidence_text(original))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ExternalRuntimeReceiptError("Recibo/outbox F7 nao confiavel") from exc
    if (not isinstance(receipt, dict) or set(receipt) != REQUIRED
            or not isinstance(loaded, dict) or loaded != outbox):
        raise ExternalRuntimeReceiptError("Recibo nao corresponde ao contrato/outbox")
    if (receipt["schema"] != SCHEMA or receipt["repository"] != REPO
            or type(receipt["repository_id"]) is not int
            or receipt["repository_id"] != REPO_ID
            or receipt["execution_id"] != outbox.get("execution_id")
            or receipt["mission_id"] != outbox.get("mission_id")
            or receipt["mission_digest"] != provenance.get("mission_digest")
            or receipt["executor_tar_sha256"] != TAR_SHA256
            or receipt["executor_image_id"] != IMAGE_ID
            or receipt["executor_build_sha"] != EXECUTOR_SOURCE_SHA
            or receipt["test_mode"] != "docker-attested-e3b-sigstore"
            or receipt["authorization"] != "V1_ATTESTOR_RUN_ONLY_NO_POST"):
        raise ExternalRuntimeReceiptError("Vinculo executor/missao F7 divergente")
    if (not isinstance(receipt["outbox_sha256"], str)
            or not SHA64.fullmatch(receipt["outbox_sha256"])
            or receipt["outbox_sha256"] != hashlib.sha256(original).hexdigest()
            or receipt["files_sha256"] != provenance.get("files_sha256")):
        raise ExternalRuntimeReceiptError("Hashes da missao/dossie divergentes")
    for key in ("producer_run_id", "producer_run_attempt",
                "attestor_run_id", "attestor_run_attempt"):
        if type(receipt.get(key)) is not int or receipt[key] < 1:
            raise ExternalRuntimeReceiptError("Run/tentativa invalido no recibo")
    attestor_run = _live_attestor_run(receipt["attestor_run_id"])
    if (type(attestor_run.get("id")) is not int
            or attestor_run["id"] != receipt["attestor_run_id"]
            or type(attestor_run.get("workflow_id")) is not int
            or attestor_run["workflow_id"] != ATTESTOR_WORKFLOW_ID_PIN
            or attestor_run.get("path") not in (
                WORKFLOW_PATH, WORKFLOW_PATH + "@refs/heads/main")
            or attestor_run.get("head_sha") != ATTESTOR_SHA_PIN
            or attestor_run.get("head_branch") != "main"
            or attestor_run.get("status") != "completed"
            or attestor_run.get("conclusion") != "success"
            or type(attestor_run.get("run_attempt")) is not int
            or attestor_run["run_attempt"] != receipt["attestor_run_attempt"]
            or not isinstance(attestor_run.get("repository"), dict)
            or attestor_run["repository"].get("id") != REPO_ID):
        raise ExternalRuntimeReceiptError("Run atestador nao corresponde ao pin LIVE")
    _verify_sigstore(raw, sha=ATTESTOR_SHA_PIN)
    return {
        "schema": SCHEMA,
        "attestor_run_id": receipt["attestor_run_id"],
        "attestor_run_attempt": receipt["attestor_run_attempt"],
        "producer_run_id": receipt["producer_run_id"],
        "receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "executor_tar_sha256": TAR_SHA256,
        "executor_image_id": IMAGE_ID,
    }
