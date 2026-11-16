"""Executor de testes F6 em Docker, sem rede e sem escrita no host.

O sandbox reduz a exposição do código AGY; não atesta impossibilidade de
escape de container nem isola AGY/Codex (que ficam em modo textual no host).
A imagem python:3.12-slim deve estar localmente disponível antes de iniciar.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

IMAGE = "python:3.12-slim"


def preflight() -> str:
    """Verificação local fail-closed ANTES de consumir chamadas de IA."""
    if not shutil.which("docker"):
        raise ValueError("Docker CLI ausente; nao iniciar AGY/Codex")
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True, text=True, timeout=12, check=False)
        if info.returncode or info.stdout.strip() != "linux":
            raise ValueError("Docker Linux indisponivel (exige Linux containers)")
        inspected = subprocess.run(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
            capture_output=True, text=True, timeout=12, check=False)
        if (inspected.returncode or not inspected.stdout.strip().startswith("sha256:")):
            raise ValueError("Imagem Docker nao instalada: docker pull " + IMAGE)
        return inspected.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Falha ao verificar Docker; AGY nao foi chamado") from exc


def build_command(root: Path) -> list[str]:
    """Montagem vetorizada, sem shell, rede, privilégios ou escrita no host."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Diretorio Git invalido")
    return [
        "docker", "run", "--rm", "--pull=never",
        "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=256m", "--cpus=1",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=32m",
        "--mount", "type=bind,source=" + str(root) + ",target=/work,readonly",
        "--workdir=/work",
        "--env=PYTHONDONTWRITEBYTECODE=1", "--env=HOME=/tmp",
        IMAGE, "python", "-I", "-B", "-m", "unittest", "discover",
        "-s", "tests", "-p", "test_*.py", "-v",
    ]
