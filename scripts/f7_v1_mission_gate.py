"""E3-C2: autorização GH LIVE de missão V1 (somente leitura).

NÃO executa AGY/Codex, não gera outbox nem habilita publicação. Uma
autorização de Issue não substitui custódia V1, isolamento e Gates 3-5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Callable

SCHEMA = "CHDEVFLOW-F7-V1-MISSION/1"
REPO = "hallanbrito/CHDevFlow"
REPO_ID = 1424359000
PO_LOGIN = "hallanbrito"
PO_ID = 113695320
HEXSHA = re.compile(r"[0-9a-f]{40}\Z")
HEXDIGEST = re.compile(r"[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
MISSION = re.compile(r"[A-Za-z0-9_.-]{3,80}\Z")
TARGET = re.compile(r"(?:[A-Za-z0-9_.-]+/){0,5}[A-Za-z0-9_.-]+\.py\Z")
APPROVAL_LIMIT = 10
REQUIRED_FIELDS = frozenset({
    "schema", "repository", "mission_id", "issue", "producer_sha",
    "baseline_sha", "executor_tar_sha256", "allowed_path",
    "prompt_path", "timeout_seconds", "cost_brl", "nonce",
})


class MissionAuthorizationError(ValueError):
    """Identidade, permissão ou declaração LIVE insuficiente."""


def canonical(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def validate_manifest(data: dict[str, Any]) -> str:
    if not isinstance(data, dict) or set(data) != REQUIRED_FIELDS:
        raise MissionAuthorizationError("Contrato V1 tem campos ausentes ou extras")
    if data["schema"] != SCHEMA or data["repository"] != REPO:
        raise MissionAuthorizationError("Schema ou repositório V1 divergente")
    if not isinstance(data["mission_id"], str) or not MISSION.fullmatch(data["mission_id"]):
        raise MissionAuthorizationError("Identidade da missão inválida")
    if type(data["issue"]) is not int or data["issue"] < 1:
        raise MissionAuthorizationError("Issue inválida")
    for key in ("producer_sha", "baseline_sha"):
        if not isinstance(data[key], str) or not HEXSHA.fullmatch(data[key]):
            raise MissionAuthorizationError("SHA V1 inválido: " + key)
    if (not isinstance(data["executor_tar_sha256"], str)
            or not HEXDIGEST.fullmatch(data["executor_tar_sha256"])
            or not isinstance(data["nonce"], str)
            or not NONCE.fullmatch(data["nonce"])):
        raise MissionAuthorizationError("Digest/nonce V1 inválido")
    for key in ("allowed_path", "prompt_path"):
        value = data[key]
        if (not isinstance(value, str) or not TARGET.fullmatch(value) and key == "allowed_path"
                or not isinstance(value, str) or not 0 < len(value) <= 200):
            raise MissionAuthorizationError("Caminho de missão inválido: " + key)
        p = PurePosixPath(value)
        if (p.is_absolute() or ".." in p.parts or "." in p.parts
                or "\\" in value or any(c in value for c in "*?[]")
                or value.startswith((".github/", "tests/", "scripts/f7_"))):
            raise MissionAuthorizationError("Escopo privilegiado ou fora do contrato")
    if data["allowed_path"] == data["prompt_path"]:
        raise MissionAuthorizationError("Prompt e arquivo gerado devem ser distintos")
    if type(data["timeout_seconds"]) is not int or not 120 <= data["timeout_seconds"] <= 900:
        raise MissionAuthorizationError("Timeout fora da política")
    if type(data["cost_brl"]) is not int or data["cost_brl"] != 0:
        raise MissionAuthorizationError("Custo incremental não é R$0")
    return hashlib.sha256(canonical(data)).hexdigest()


def expected_approval(data: dict[str, Any]) -> str:
    digest = validate_manifest(data)
    return (
        f"CH-F7-V1 AUTORIZAR ISSUE#{data['issue']} MISSION#{data['mission_id']} "
        f"PRODUCER_SHA={data['producer_sha']} BASE_SHA={data['baseline_sha']} "
        f"EXECUTOR_TAR_SHA256={data['executor_tar_sha256']} "
        f"MISSION_DIGEST={digest} COST_BRL=0 NONCE={data['nonce']} ACTION=RUN_ONLY"
    )


def po_identity(author: Any) -> bool:
    return (isinstance(author, dict)
            and author.get("login") == PO_LOGIN
            and type(author.get("id")) is int
            and author["id"] == PO_ID)


def validate_live(
    manifest: dict[str, Any], *, approval_id: int, actor: dict[str, Any],
    repository: dict[str, Any], issue: dict[str, Any],
    comments: list[dict[str, Any]], workflow_sha: str,
) -> dict[str, Any]:
    digest = validate_manifest(manifest)
    if (not isinstance(workflow_sha, str)
            or workflow_sha != manifest["producer_sha"]):
        raise MissionAuthorizationError("Commit do workflow não coincide com a autorização")
    if (not po_identity(actor)
            or not isinstance(repository, dict)
            or repository.get("full_name") != REPO
            or type(repository.get("id")) is not int
            or repository["id"] != REPO_ID):
        raise MissionAuthorizationError("Sessão e repositório GH LIVE não autenticados")
    if (not isinstance(issue, dict)
            or type(issue.get("number")) is not int
            or issue["number"] != manifest["issue"]
            or issue.get("state") != "open"
            or "pull_request" in issue
            or not isinstance(comments, list)
            or type(approval_id) is not int or approval_id < 1):
        raise MissionAuthorizationError("Issue/ID de aprovação inválidos")
    matching = [c for c in comments if isinstance(c, dict) and c.get("id") == approval_id]
    if len(matching) != 1:
        raise MissionAuthorizationError("Comentário da autorização não encontrado univocamente")
    approval = matching[0]
    if (not po_identity(approval.get("user"))
            or not isinstance(approval.get("body"), str)
            or approval["body"].strip() != expected_approval(manifest)
            or not isinstance(approval.get("created_at"), str)
            or approval.get("updated_at") != approval["created_at"]):
        raise MissionAuthorizationError("Aprovação PO ausente, editada ou inconsistente")
    for comment in comments:
        if (not isinstance(comment, dict)
                or type(comment.get("id")) is not int
                or comment["id"] < 1):
            raise MissionAuthorizationError("Histórico de aprovação incompleto")
        if comment["id"] <= approval_id:
            continue
        if not po_identity(comment.get("user")):
            if (isinstance(comment.get("user"), dict)
                    and comment["user"].get("login") == PO_LOGIN):
                raise MissionAuthorizationError("Identidade do PO suspeita no histórico")
            continue
        body = comment.get("body")
        if (isinstance(body, str) and
                body.strip().startswith(f"CH-F7-V1 REVOGAR ISSUE#{manifest['issue']} ")):
            raise MissionAuthorizationError("Aprovação V1 revogada pelo PO")
    return {
        "schema": "CHDEVFLOW-F7-V1-GATE-READONLY/1",
        "mission_id": manifest["mission_id"],
        "mission_digest": digest,
        "approval_comment_id": approval_id,
        "po_id": PO_ID,
        "producer_sha": workflow_sha,
        "state": "PO_APPROVAL_VERIFIED_ONLY",
        "agents_executed": False,
        "outbox_v1_created": False,
        "remote_publication_enabled": False,
    }


def _json_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MissionAuthorizationError("JSON com chaves duplicadas")
        result[key] = value
    return result


def read_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32_000:
        raise MissionAuthorizationError("Manifesto inseguro")
    try:
        obj = json.loads(path.read_bytes(), object_pairs_hook=_json_no_duplicates)
    except (OSError, ValueError, UnicodeError) as exc:
        raise MissionAuthorizationError("JSON de missão inválido") from exc
    validate_manifest(obj)
    return obj


def _gh(endpoint: str) -> Any:
    if not re.fullmatch(r"[A-Za-z0-9_./?=&-]+", endpoint):
        raise MissionAuthorizationError("Endpoint GH inválido")
    try:
        proc = subprocess.run(
            ["gh", "api", "--hostname", "github.com", endpoint],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MissionAuthorizationError("API GH LIVE indisponível") from exc
    if proc.returncode or len(proc.stdout) > 300_000:
        raise MissionAuthorizationError("API GH retornou erro ou resposta excessiva")
    try:
        return json.loads(proc.stdout, object_pairs_hook=_json_no_duplicates)
    except (ValueError, UnicodeError) as exc:
        raise MissionAuthorizationError("Resposta GH inválida") from exc


def fetch_live(manifest: dict[str, Any]) -> tuple[dict, dict, dict, list]:
    issue = manifest["issue"]
    actor = _gh("user")
    repo = _gh(f"repos/{REPO}")
    issue_state = _gh(f"repos/{REPO}/issues/{issue}")
    comments = []
    for page in range(1, APPROVAL_LIMIT + 1):
        batch = _gh(f"repos/{REPO}/issues/{issue}/comments?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise MissionAuthorizationError("Histórico não é lista")
        comments.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise MissionAuthorizationError("Histórico GH excedeu limite de páginas")
    return actor, repo, issue_state, comments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approval-comment-id", type=int, required=True)
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args(argv)
    manifest = read_manifest(args.manifest)
    actor, repo, issue, comments = fetch_live(manifest)
    result = validate_live(
        manifest, approval_id=args.approval_comment_id,
        actor=actor, repository=repo, issue=issue, comments=comments,
        workflow_sha=args.workflow_sha,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
