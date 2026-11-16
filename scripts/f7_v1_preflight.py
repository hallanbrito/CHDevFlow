"""E3-C1: preflight de V1 em modo somente-leitura, SEM executor de agentes.

Distingue evidencia LAB E3-C0 de uma origem confiavel V1. Nunca autoriza
AGY/Codex, publica comentario, gera outbox V1 ou altera o Project #2.
A assinatura Sigstore deve ser conferida POR OUTRO PROCESSO antes deste CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "CHDEVFLOW-F7-E3C1-READINESS/1"
LAB_SCHEMA = "CHDEVFLOW-F7-E3C0-CONSUMER/1"
LAB_AUTH = "E3C0_LAB_ONLY_NO_AGENTS_NO_OUTBOX_NO_POST"
V1_SCHEMA = "CHDEVFLOW-F7-V1-EXECUTION/1"
ORIGIN = "github-actions:v1:"
REPO = "hallanbrito/CHDevFlow"
SOURCE_SHA = "389bcc61342cbcdd3183e291a18eef42ad78f488"
E3C0_SHA = "075ddbdb39bd32a824b212cd531461543d1307d9"
TAR_SHA = "b7b912afad6422f134501fd997eb13cc1bf70de8aa88de43e0988841a84b0242"
IMAGE_ID = "sha256:e0c1bddedb8763803370d0a02b9d05371a30d9c4c82f0fe0b8813bb3b5b9f7ed"
READ_LIMIT = 32_000

MISSING_GATES = (
    "PO_APPROVAL_FOR_EXACT_MISSION",
    "PROTECTED_MAIN_V1_PRODUCER_RUN",
    "REAL_AGY_EXECUTION_AND_CODEX_AUDIT",
    "V1_OUTBOX_INDEPENDENT_ATTESTATION",
    "TRUST_PINS_AND_REVOCATION",
    "GATE4_PRE_POST_COMMIT",
    "GATE5_CONTROLLED_REAL_PILOT",
)


def read_json_safely(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= READ_LIMIT:
        raise ValueError("Documento de preflight ausente, simbolico ou excessivo")
    try:
        document = json.loads(path.read_bytes(),
                              object_pairs_hook=_no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("JSON de preflight nao confiavel") from exc
    if not isinstance(document, dict):
        raise ValueError("Documento de preflight nao e objeto JSON")
    return document


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("JSON com chaves duplicadas")
        out[key] = value
    return out


def classify_lab_chain(document: dict[str, Any]) -> dict[str, Any]:
    """Classificacao estrutural; NAO verifica criptografia Sigstore sozinha."""
    if not isinstance(document, dict) or document.get("schema") != LAB_SCHEMA:
        raise ValueError("Apenas manifesto E3-C0 esperado nesta fase")
    if document.get("authorization") != LAB_AUTH:
        raise ValueError("Marcador de nao autorizacao LAB ausente")
    if (document.get("source_commit") != SOURCE_SHA
            or document.get("consumer_commit") != E3C0_SHA
            or document.get("tar_sha256") != TAR_SHA
            or document.get("image_id") != IMAGE_ID):
        raise ValueError("Identidade da cadeia LAB divergente")
    reports = document.get("reports")
    if not isinstance(reports, dict) or set(reports) != {"self", "pass", "fail"}:
        raise ValueError("Provas LAB incompletas")
    for name, status in (("self", "SELF_CHECK_OK"), ("pass", "TESTS_PASS"),
                         ("fail", "TESTS_FAILED")):
        item = reports[name]
        if (not isinstance(item, dict) or item.get("status") != status
                or not isinstance(item.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
            raise ValueError("Prova LAB divergente: " + name)
    if (type(document.get("consumer_run")) is not int
            or document["consumer_run"] != 43888441966):
        raise ValueError("Run consumidor nao corresponde a evidencia auditada")
    return {
        "schema": SCHEMA,
        "observed_manifest_sha256": hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode("ascii") + b"\n").hexdigest(),
        "source_commit": SOURCE_SHA,
        "consumer_commit": E3C0_SHA,
        "tar_sha256": TAR_SHA,
        "classification": "LAB_ONLY_NOT_V1",
        "state": "BLOCKED_V1_NOT_AUTHORIZED",
        "missing_gates": list(MISSING_GATES),
        "allowed_actions": ["READ_ONLY_INSPECTION", "OFFLINE_NEGATIVE_TESTS"],
        "v1_run_created": False,
        "remote_publication_enabled": False,
    }


def reject_v1_elevation(document: dict[str, Any]) -> None:
    """NUNCA promover o resultado E3-C0 ao produtor real de outbox."""
    if document.get("schema") == LAB_SCHEMA:
        raise PermissionError("Evidencia E3-C0 LAB nao e outbox V1")
    if document.get("schema") == V1_SCHEMA:
        raise PermissionError("Contrato V1 requer execucao protegida e autorizacao LIVE")
    raise PermissionError("Documento nao autorizado para publicacao F7")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = read_json_safely(args.manifest)
    report = classify_lab_chain(manifest)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0  # O CLI concluiu a INSPECAO; state continua BLOQUEADO.


if __name__ == "__main__":
    raise SystemExit(main())
