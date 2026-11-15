"""Reserva create-only de publicacao F7 em um remoto Git compartilhado."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

from chdevflow.core.po_escalation import REPO, _json_unique

NAMESPACE = "refs/tags/chdevflow-f7-publication/"
SCHEMA = "CHDEVFLOW-F7-RESERVATION/1"


class ReservationError(ValueError):
    """Operacao recusada; nunca autoriza POST."""


class ReservationUnconfirmed(ReservationError):
    """Sem confirmacao de criacao nesta chamada; nunca autoriza POST."""


def _reservation_fields(plan: dict) -> tuple[str, dict]:
    execution, digest, issue = (plan.get(k) for k in ("execution_id", "digest", "issue"))
    if (plan.get("repo") != REPO or not isinstance(execution, str)
            or not re.fullmatch(r"[0-9a-f]{32}", execution)
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(issue) is not int or issue < 1):
        raise ReservationError("Plano sem identidade valida para reserva Git")
    return NAMESPACE + execution, {
        "schema": SCHEMA, "repository": REPO, "issue": issue,
        "execution_id": execution, "plan_digest": digest,
    }


class GitReservationStore:
    """Apenas o retorno positivo da criacao do ref concede a tentativa de POST.

    O remoto operacional precisa impedir atualizacao e exclusao das reservas.
    Consultar um recibo existente serve para reconciliar, jamais para publicar.
    """

    def __init__(self, remote: str, *, github_cli_credentials: bool = False):
        self.remote = remote
        self.github_cli_credentials = github_cli_credentials

    def _git(self, directory: Path, *args: str, data: bytes = b"") -> bytes:
        env = os.environ.copy()
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE"):
            env.pop(name, None)
        env["GIT_TERMINAL_PROMPT"] = "0"
        auth = []
        if self.github_cli_credentials:
            # Usa a mesma conta de gh api e descarta helpers de credencial anteriores.
            auth = ["-c", "credential.helper=", "-c",
                    "credential.https://github.com.helper=!gh auth git-credential"]
            env["GH_HOST"] = "github.com"
        try:
            completed = subprocess.run(
                ["git", "-c", "user.name=CHDevFlow F7",
                 "-c", "user.email=f7@users.noreply.github.com",
                 "-c", "commit.gpgSign=false", *auth, *args],
                cwd=directory, env=env, input=data, capture_output=True,
                check=False, timeout=25,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReservationError("Comando Git da reserva indisponivel") from exc
        if completed.returncode:
            raise ReservationError("Comando Git da reserva recusado")
        return completed.stdout

    def claim(self, plan: dict) -> str:
        ref, record = _reservation_fields(plan)
        # Objetos diferentes para cada tentativa: um push 'up to date' jamais
        # pode ser confundido com a criacao da reserva por este executor.
        record["claim_id"] = uuid4().hex
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
        with TemporaryDirectory(prefix="ch-f7-reserve-") as workspace:
            root = Path(workspace)
            self._git(root, "init", "--bare", "--template=", "--object-format=sha1")
            tree = self._git(root, "mktree").decode("ascii").strip()
            commit = self._git(root, "commit-tree", tree, data=payload).decode("ascii").strip()
            try:
                result = self._git(
                    root, "push", "--no-verify", "--porcelain", f"--force-with-lease={ref}:",
                    "--", self.remote, f"{commit}:{ref}")
            except ReservationError as exc:
                raise ReservationUnconfirmed(
                    "Reserva remota nao confirmada; reconciliar sem POST ou retry") from exc
        for line in result.splitlines():
            fields = line.split(b"\t")
            if fields == [b"*", f"{commit}:{ref}".encode("ascii"), b"[new tag]"]:
                return commit
        raise ReservationUnconfirmed("Git nao comprovou a criacao da reserva remota")

    def read(self, plan: dict) -> str:
        ref, expected = _reservation_fields(plan)
        with TemporaryDirectory(prefix="ch-f7-reconcile-") as workspace:
            root = Path(workspace)
            self._git(root, "init", "--bare", "--template=", "--object-format=sha1")
            self._git(root, "fetch", "--no-tags", "--", self.remote, ref)
            commit = self._git(root, "rev-parse", "--verify", "FETCH_HEAD^{commit}")
            sha = commit.decode("ascii").strip()
            payload = self._git(root, "show", "-s", "--format=%B", sha)
        if len(payload) > 2048:
            raise ReservationError("Recibo Git excessivo")
        try:
            record = _json_unique(payload)
        except ValueError as exc:
            raise ReservationError("Recibo Git invalido") from exc
        if not isinstance(record, dict):
            raise ReservationError("Recibo Git invalido")
        claim_id = record.pop("claim_id", None)
        if (record != expected or not isinstance(claim_id, str)
                or not re.fullmatch(r"[0-9a-f]{32}", claim_id)):
            raise ReservationError("Reserva remota pertence a outro plano")
        return sha
