"""E3-B: executor de testes de codigo Python, sem agentes nem publicacao.

A politica de isolamento pertence ao docker run do workflow, NAO a este
processo. Este executavel suporta self-check e unittest numa worktree
descartavel montada read-only em /work; nao produz outbox V1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

SCHEMA = "CHDEVFLOW-F7-E3B-EXECUTOR/1"
MAX_TESTS = 40
MAX_FILE_SIZE = 100_000
MAX_OUTPUT = 16_000
TEST_ROOT = Path("/work")
TIMEOUT = 60


def report(**fields: object) -> None:
    print(json.dumps({"schema": SCHEMA, **fields}, sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True), flush=True)


def safety_preflight() -> None:
    if sys.platform != "linux" or os.geteuid() != 65534 or os.getegid() != 65534:
        raise ValueError("Executor fora do usuario de sandbox 65534:65534")
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        raise ValueError("Executor recebeu credencial GitHub inesperada")


def validate_test_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Worktree de testes ausente ou simbolica")
    target = root / "tests"
    if not target.is_dir() or target.is_symlink():
        raise ValueError("Pasta tests ausente ou simbolica")
    total = 0
    for parent, folders, files in os.walk(target, followlinks=False):
        for name in folders + files:
            child = Path(parent) / name
            if child.is_symlink():
                raise ValueError("Link nao permitido na arvore de testes")
            if child.is_file():
                if not child.name.endswith(".py") or child.stat().st_size > MAX_FILE_SIZE:
                    raise ValueError("Arquivo de teste fora do contrato")
                total += 1
                if total > MAX_TESTS:
                    raise ValueError("Testes excedem limite")
    if total < 1:
        raise ValueError("Nenhum teste Python encontrado")


def run_tests() -> int:
    validate_test_tree(TEST_ROOT)
    sanitized = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = [sys.executable, "-I", "-B", "-m", "unittest", "discover",
               "-s", "tests", "-p", "test_*.py", "-v"]
    try:
        completed = subprocess.run(
            command, cwd=TEST_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
            env=sanitized, timeout=TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report(status="INFRA_BLOCKED", error=type(exc).__name__)
        return 20
    result = (completed.stdout + completed.stderr)[:MAX_OUTPUT]
    report(status="TESTS_PASS" if completed.returncode == 0 else "TESTS_FAILED",
           tests_exit_code=completed.returncode,
           log_sha256=hashlib.sha256(result.encode("utf-8")).hexdigest(),
           log_excerpt=result[-500:])
    return 0 if completed.returncode == 0 else 12


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-check", action="store_true")
    group.add_argument("--run-tests", action="store_true")
    args = parser.parse_args(argv)
    try:
        safety_preflight()
        if args.self_check:
            file_bytes = Path(__file__).read_bytes()
            report(status="SELF_CHECK_OK", uid=os.geteuid(), gid=os.getegid(),
                   python=platform.python_version(),
                   executable_sha256=hashlib.sha256(file_bytes).hexdigest())
            return 0
        return run_tests()
    except (OSError, ValueError) as exc:
        report(status="PREFLIGHT_BLOCKED", reason=str(exc))
        return 30


if __name__ == "__main__":
    raise SystemExit(main())
