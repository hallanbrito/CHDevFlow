"""Verifica um recibo F7 assinado por um produtor externo confiavel."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from chdevflow.core.po_escalation import REPO, _json_unique, _read_evidence_bytes

SCHEMA = "CHDEVFLOW-F7-EXTERNAL-ATTESTATION/1"
SSH_NAMESPACE = "chdevflow-f7-execution"
ISSUER = "chdevflow-f7-producer"


def statement_bytes(statement: dict) -> bytes:
    return json.dumps(
        statement, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("ascii")


def execution_statement(outbox: dict, *, producer_sha: str, producer_run: str) -> dict:
    """Formato canônico para um produtor atestar dados que ele proprio observou."""
    if (not isinstance(producer_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", producer_sha)
            or not isinstance(producer_run, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:/_.-]{0,159}", producer_run)):
        raise ValueError("Identidade do produtor ou da execucao atestada invalida")
    return {
        "schema": SCHEMA, "repository": REPO,
        "producer_sha": producer_sha, "producer_run": producer_run,
        "issue": outbox["issue"], "mission_id": outbox["mission_id"],
        "execution_id": outbox["execution_id"],
        "attempts": outbox["attempts"], "returns": outbox["returns"],
        "third_attempt_status": outbox["third_attempt_status"],
        "code_sha256": outbox["code_sha256"],
        "isolated_tests": True,
        "provenance": outbox["provenance"],
    }


def validate_trusted_key(trusted_key: str, revoked_fingerprints: str) -> str:
    if not isinstance(trusted_key, str) or not re.fullmatch(
            r"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI[A-Za-z0-9+/]{43}", trusted_key):
        raise ValueError("Chave confiavel do produtor F7 ausente ou invalida")
    if revoked_fingerprints == "NONE":
        revoked_fingerprints = ""
    if not isinstance(revoked_fingerprints, str) or any(
            not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", value)
            for value in revoked_fingerprints.split()):
        raise ValueError("Lista de revogacao indisponivel ou invalida")
    key_blob = base64.b64decode(trusted_key.split()[1], validate=True)
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key_blob).digest()).decode().rstrip("=")
    if fingerprint in revoked_fingerprints.split():
        raise ValueError("Chave do atestador revogada")
    return fingerprint


def verify_external_attestation(
    path: Path, outbox: dict, *, trusted_key: str, trusted_producer_sha: str,
    revoked_fingerprints: str = "",
) -> dict:
    """A chave e o SHA esperados vem de uma politica externa ao dossie."""
    validate_trusted_key(trusted_key, revoked_fingerprints)
    receipt = _json_unique(_read_evidence_bytes(path, cap=30000))
    if not isinstance(receipt, dict) or set(receipt) != {"statement", "signature"}:
        raise ValueError("Recibo externo F7 invalido")
    supplied = receipt["statement"]
    if not isinstance(supplied, dict):
        raise ValueError("Declaracao assinada F7 invalida")
    expected = execution_statement(
        outbox, producer_sha=trusted_producer_sha, producer_run=supplied.get("producer_run"))
    payload = statement_bytes(expected)
    if statement_bytes(supplied) != payload:
        raise ValueError("Recibo externo diverge do dossie ou do produtor confiavel")
    signature = receipt["signature"]
    if (not isinstance(signature, str) or len(signature) > 4096
            or not signature.isascii() or not signature.startswith("-----BEGIN SSH SIGNATURE-----\n")
            or not signature.endswith("-----END SSH SIGNATURE-----\n")):
        raise ValueError("Assinatura OpenSSH F7 invalida")
    with TemporaryDirectory(prefix="ch-f7-attestation-") as folder:
        signers = Path(folder) / "signers"
        signers.write_bytes(f'{ISSUER} namespaces="{SSH_NAMESPACE}" {trusted_key}\n'.encode("ascii"))
        sig = Path(folder) / "statement.sig"
        sig.write_bytes(signature.encode("ascii"))
        try:
            verification = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", ISSUER,
                 "-n", SSH_NAMESPACE, "-s", str(sig)],
                input=payload, capture_output=True, check=False, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Verificador OpenSSH F7 indisponivel") from exc
    if verification.returncode:
        raise ValueError("Assinatura externa F7 nao corresponde ao produtor confiavel")
    return {"producer_sha": trusted_producer_sha, "producer_run": expected["producer_run"]}
