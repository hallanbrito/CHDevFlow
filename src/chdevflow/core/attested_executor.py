"""F7 E3-C3: vincula testes F6 ao TAR E3-B atestado (opt-in).

O TAR deve ser obtido de GitHub Actions em canal autenticado e ser verificado
por Sigstore, SHA-256 e identidade Docker ANTES de qualquer chamada AGY.
A prova atesta o build do executor, nao os CLIs AGY/Codex nem uma outbox V1.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

REPO = "hallanbrito/CHDevFlow"
SOURCE_SHA = "389bcc61342cbcdd3183e291a18eef42ad78f488"
SOURCE_REF = "refs/heads/feat/ch-pipe-01-f7-e3b-attested-executor-20261116"
SIGNER = "hallanbrito/CHDevFlow/.github/workflows/f7-e3b-executor-attest.yml"
TAR_SHA256 = "b7b912afad6422f134501fd997eb13cc1bf70de8aa88de43e0988841a84b0242"
IMAGE_ID = "sha256:e0c1bddedb8763803370d0a02b9d05371a30d9c4c82f0fe0b8813bb3b5b9f7ed"
SCHEMA = "CHDEVFLOW-F7-E3B-EXECUTOR/1"
MAX_TAR_BYTES = 180_000_000
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class AttestedExecutorError(ValueError):
    """O executor solicitado nao possui a proveniencia exigida."""


def _command(args: list[str], timeout: int) -> str:
    try:
        done = subprocess.run(
            args, capture_output=True, stdin=subprocess.DEVNULL,
            check=False, timeout=timeout, text=True, encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AttestedExecutorError("Falha na ferramenta do executor atestado") from exc
    if done.returncode != 0:
        raise AttestedExecutorError("Comando de verificacao do executor recusado")
    return done.stdout.strip()


def _no_symlinks(path: Path) -> None:
    absolute = path.absolute()
    if ".." in path.parts:
        raise AttestedExecutorError("Caminho com travessia proibido")
    while True:
        if absolute.is_symlink():
            raise AttestedExecutorError("Link simbolico no caminho do TAR")
        if absolute == absolute.parent:
            return
        absolute = absolute.parent


def verify_tar(tar: Path) -> str:
    _no_symlinks(tar)
    if (not tar.is_file() or not 0 < tar.stat().st_size <= MAX_TAR_BYTES):
        raise AttestedExecutorError("TAR ausente ou fora do limite")
    sha = hashlib.sha256()
    with tar.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    if sha.hexdigest() != TAR_SHA256:
        raise AttestedExecutorError("TAR nao corresponde ao SHA-256 E3-B")
    return sha.hexdigest()


def preflight(tar: Path) -> str:
    """Retorna o image ID pinado apenas apos validar TAR, Sigstore e Docker."""
    tar = tar.expanduser().absolute()
    if not shutil.which("gh") or not shutil.which("docker"):
        raise AttestedExecutorError("gh e Docker exigidos antes do AGY")
    verify_tar(tar)
    # O produtor da evidencia original nao pode trocar o TAR entre hash,
    # Sigstore e docker load. Copia verificada em diretorio privado (0700).
    with TemporaryDirectory(prefix="ch-f7-e3b-verify-") as temporary:
        frozen = Path(temporary) / "executor.tar"
        shutil.copyfile(tar, frozen)
        verify_tar(frozen)
        _command([
            "gh", "attestation", "verify", str(frozen),
            "-R", REPO, "--signer-workflow", SIGNER,
            "--source-digest", SOURCE_SHA,
            "--source-ref", SOURCE_REF, "--deny-self-hosted-runners",
        ], timeout=45)
        if _command(["docker", "info", "--format", "{{.OSType}}"], 15) != "linux":
            raise AttestedExecutorError("Docker Linux nao disponivel")
        # Exatamente os bytes autenticados, nao o caminho original mutavel.
        _command(["docker", "load", "-i", str(frozen)], 120)
    if _command(["docker", "image", "inspect", IMAGE_ID,
                 "--format", "{{.Id}}"], 15) != IMAGE_ID:
        raise AttestedExecutorError("Docker image ID nao e o build atestado")
    if _command(["docker", "image", "inspect", IMAGE_ID,
                 "--format", "{{.Config.User}}"], 15) != "65534:65534":
        raise AttestedExecutorError("Executor nao usa UID/GID protegidos")
    if _command(["docker", "image", "inspect", IMAGE_ID,
                 "--format", '{{index .Config.Labels "org.opencontainers.image.revision"}}'],
                15) != SOURCE_SHA:
        raise AttestedExecutorError("Revision OCI divergente do SHA atestado")
    return IMAGE_ID


def build_command(root: Path) -> list[str]:
    """Imagem referenciada pelo IMAGE ID imutavel, nunca por tag mutavel."""
    root = root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise AttestedExecutorError("Worktree insegura")
    return [
        "docker", "run", "--rm", "--pull=never",
        "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=256m", "--cpus=1",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=32m",
        "--mount", f"type=bind,source={root},target=/work,readonly",
        "--workdir=/work", IMAGE_ID, "--run-tests",
    ]


def checked_result(stdout: str, returncode: int, stderr: str = "") -> str:
    """Consome exclusivamente o protocolo JSON do executor E3-B real."""
    if returncode not in (0, 12) or not isinstance(stdout, str) or len(stdout) > 30000:
        raise AttestedExecutorError("Executor sem resultado conclusivo")
    if not isinstance(stderr, str) or len(stderr) > 16000:
        raise AttestedExecutorError("Erro excessivo do contêiner")
    try:
        payload = json.loads(stdout.strip())
    except (ValueError, TypeError) as exc:
        raise AttestedExecutorError("Executor nao retornou JSON E3-B") from exc
    required = {"schema", "status", "tests_exit_code", "log_sha256", "log_excerpt"}
    if not isinstance(payload, dict) or set(payload) != required or payload["schema"] != SCHEMA:
        raise AttestedExecutorError("Schema do resultado E3-B divergente")
    status = "TESTS_PASS" if returncode == 0 else "TESTS_FAILED"
    if (payload["status"] != status
            or type(payload["tests_exit_code"]) is not int
            or (payload["tests_exit_code"] != 0 if returncode == 0
                else payload["tests_exit_code"] == 0)
            or not isinstance(payload["log_sha256"], str)
            or not HEX64.fullmatch(payload["log_sha256"])
            or not isinstance(payload["log_excerpt"], str)
            or not 0 < len(payload["log_excerpt"]) <= 500
            or not re.search(r"Ran [1-9][0-9]* tests?", payload["log_excerpt"])):
        raise AttestedExecutorError("Sem prova de teste E3-B real e consistente")
    if returncode == 0 and not re.search(r"(?m)^OK\b", payload["log_excerpt"]):
        raise AttestedExecutorError("Executou mas nao comprovou unittest OK")
    if returncode == 12 and not re.search(r"FAILED\s*\(failures=[1-9]", payload["log_excerpt"]):
        raise AttestedExecutorError("Falha de teste nao e assertion independente")
    return payload["log_excerpt"]
