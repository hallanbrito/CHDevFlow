"""Busca evidencias do produtor autorizado e assina/verifica recibos da custodia."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from f7_custody_probe import seal
from chdevflow.core.po_escalation import REPO, _json_unique
from chdevflow.core.po_escalation_attestation import validate_trusted_key, verify_external_attestation
from chdevflow.core.po_escalation_publication import _eligible_outbox

REPOSITORY_ID = 1424359000
PRODUCER = ".github/workflows/f7-custody-producer.yml"
MAX_ARCHIVE = 2_000_000


def api(endpoint: str, *, binary: bool = False):
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", f"repos/{REPO}/{endpoint}"],
        capture_output=True, timeout=35, check=False)
    if result.returncode or len(result.stdout) > MAX_ARCHIVE:
        raise ValueError("GitHub API indisponivel ou resposta excessiva")
    return result.stdout if binary else _json_unique(result.stdout)


def configured(name: str, pattern: str) -> str:
    value = os.environ.get(name, "")
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Politica de custodia invalida: {name}")
    return value


def validate_run(run: dict, run_id: int, workflow_id: int, sha: str) -> int:
    attempt = run.get("run_attempt")
    if (run.get("id") != run_id or run.get("workflow_id") != workflow_id
            or run.get("path") not in (PRODUCER, PRODUCER + "@refs/heads/main")
            or run.get("event") != "workflow_dispatch" or run.get("head_branch") != "main"
            or run.get("head_sha") != sha or run.get("conclusion") != "success"
            or run.get("status") != "completed" or type(attempt) is not int or attempt < 1
            or any((run.get(key) or {}).get("id") != REPOSITORY_ID
                   for key in ("repository", "head_repository"))):
        raise ValueError("Origem, execucao ou SHA do produtor nao autorizado")
    return attempt


def validate_artifact(artifact: dict, name: str, run_id: int, sha: str) -> None:
    source = artifact.get("workflow_run") or {}
    size = artifact.get("size_in_bytes")
    digest = artifact.get("digest")
    if (artifact.get("name") != name or artifact.get("expired") is not False
            or type(artifact.get("id")) is not int or artifact["id"] < 1
            or type(size) is not int or not 0 < size <= MAX_ARCHIVE
            or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or source.get("id") != run_id or source.get("head_branch") != "main"
            or source.get("head_sha") != sha
            or source.get("repository_id") != REPOSITORY_ID
            or source.get("head_repository_id") != REPOSITORY_ID):
        raise ValueError("Artefato sem vinculo verificavel com o produtor")


def unpack(data: bytes, digest: str, destination: Path) -> None:
    if len(data) > MAX_ARCHIVE or "sha256:" + hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Digest GitHub do ZIP divergente")
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if (len(entries) > 40 or sum(e.file_size for e in entries) > MAX_ARCHIVE
                or len({e.filename for e in entries}) != len(entries)):
            raise ValueError("Arquivo de evidencias excessivo ou duplicado")
        for entry in entries:
            if (not re.fullmatch(
                    r"(?:escalonamento_po\.json|manifesto_missao\.json|execucao\.json|"
                    r"RELATORIO_COMPLETO_CH1\.md|attempt-0[1-3]/(?:"
                    r"agy\.log|codigo\.py|alteracoes\.patch|testes\.log|feedback_para_agy\.md))",
                    entry.filename)
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    or entry.file_size > 100_000):
                raise ValueError("Entrada de evidencia nao admitida")
            target = destination.joinpath(*PurePosixPath(entry.filename).parts)
            target.parent.mkdir(exist_ok=True)
            with target.open("xb") as out:
                out.write(archive.read(entry))


def get_evidence(run_id: int, destination: Path) -> tuple[Path, str, str]:
    sha = configured("CH_F7_TRUSTED_RUNNER_SHA", r"[0-9a-f]{40}")
    workflow_id = int(configured("CH_F7_PRODUCER_WORKFLOW_ID", r"[1-9][0-9]{0,19}"))
    attempt = validate_run(api(f"actions/runs/{run_id}"), run_id, workflow_id, sha)
    name = f"f7-custody-evidence-{run_id}-{attempt}"
    collection = api(f"actions/runs/{run_id}/artifacts?name={name}&per_page=2")
    rows = collection.get("artifacts")
    if collection.get("total_count") != 1 or not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("Artefato do produtor ausente ou ambiguo")
    if not isinstance(rows[0], dict) or type(rows[0].get("id")) is not int or rows[0]["id"] < 1:
        raise ValueError("ID GitHub do artefato invalido")
    artifact = api(f"actions/artifacts/{rows[0]['id']}")
    validate_artifact(artifact, name, run_id, sha)
    if artifact["id"] != rows[0]["id"] or artifact["digest"] != rows[0].get("digest"):
        raise ValueError("Metadados do artefato mudaram")
    unpack(api(f"actions/artifacts/{artifact['id']}/zip", binary=True),
           artifact["digest"], destination)
    # Nao aceitar reexecucao concorrente que substituiu a tentativa autorizada.
    if validate_run(api(f"actions/runs/{run_id}"), run_id, workflow_id, sha) != attempt:
        raise ValueError("Tentativa do produtor mudou durante a coleta")
    outbox = destination / "escalonamento_po.json"
    if _eligible_outbox(outbox)["mission_id"] != "F7-CUSTODY-PROBE":
        raise ValueError("Workflow de qualificacao recebeu uma missao fora do escopo")
    for index in range(1, 4):
        log = (destination / f"attempt-{index:02d}" / "testes.log").read_text(encoding="utf8")
        if (not log.startswith("exit=1 timeout=False\n")
                or len(re.findall(r"(?m)^Ran 1 test in ", log)) != 1
                or "FAIL: test_expected_value" not in log
                or "FAILED (failures=1)" not in log):
            raise ValueError("Reprovacao Docker independente sem evidencia semantica")
    origin = f"github-actions:custody:{run_id}:{attempt}:{artifact['id']}:{artifact['digest']}"
    return outbox, sha, origin


def trusted_key() -> str:
    key = configured("CH_F7_TRUSTED_RUNNER_PUBKEY", r"ssh-ed25519 [A-Za-z0-9+/]{68}")
    revoked = configured("CH_F7_REVOKED_RUNNER_FINGERPRINTS", r"NONE|SHA256:.+")
    validate_trusted_key(key, revoked)
    return key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("sign", "verify"))
    parser.add_argument("run_id", type=int)
    parser.add_argument("public_directory", type=Path)
    args = parser.parse_args()
    if args.run_id < 1:
        parser.error("Run ID invalido")
    private = os.environ.pop("CH_F7_SIGNING_KEY", "")
    key = trusted_key()
    with TemporaryDirectory(prefix="f7-evidence-") as folder:
        outbox, sha, origin = get_evidence(args.run_id, Path(folder))
        receipt = args.public_directory / "f7-attestation.json"
        if args.mode == "sign":
            if os.environ.get("GITHUB_SHA") != configured("CH_F7_ATTESTOR_SHA", r"[0-9a-f]{40}"):
                raise ValueError("Commit do atestador nao autorizado")
            if not private.startswith("-----BEGIN OPENSSH PRIVATE KEY-----"):
                raise ValueError("Credencial protegida do atestador indisponivel")
            args.public_directory.mkdir()
            with TemporaryDirectory(prefix="f7-custody-key-") as key_folder:
                key_path = Path(key_folder) / "key"
                fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write((private.rstrip() + "\n").encode("ascii"))
                del private
                proof = seal(outbox, key_path, key, sha, origin, receipt)
            (args.public_directory / "f7-custody.pub").write_text(key + "\n", encoding="ascii")
        else:
            proof = verify_external_attestation(
                receipt, _eligible_outbox(outbox), trusted_key=key, trusted_producer_sha=sha)
        if proof["producer_run"] != origin:
            raise ValueError("Recibo nao corresponde ao artefato verificado")
        print(json.dumps({"status": "CUSTODY_VERIFIED", **proof}, sort_keys=True))


if __name__ == "__main__":
    main()
