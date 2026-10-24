"""Execução de verificações do projeto e persistência de evidências estruturadas."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

from chdevflow.adapters import get_adapter
from chdevflow.adapters.base import sanitize_output
from chdevflow.core.config import load_manifest, ManifestError
from chdevflow.core.status import check_git_status

# Padrões bloqueados de mutação remota, tráfego de rede não autorizado e publicação indevida
FORBIDDEN_MUTABLE_PATTERNS = [
    # Git mutações remotas ou de branch (mesmo com flags como -C, --git-dir, etc.)
    r"\bgit\b.*?\b(push|merge|rebase)\b",
    # Bloqueio integral de clientes de rede/CLI externa em 'ch verify' (fail-closed)
    r"\bgh\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bhttpie\b",
    r"\bhttp\b\s+.*?https?://",
    # Publicação em registries de pacotes e imagens
    r"\bnpm\b.*?\b(publish|unpublish|deprecate)\b",
    r"\byarn\b.*?\bpublish\b",
    r"\bpnpm\b.*?\bpublish\b",
    r"\bmvn\b.*?\b(deploy|release:perform)\b",
    r"\bgradle\b.*?\b(publish|uploadArchives)\b",
    r"\bdocker\b.*?\bpush\b",
    r"\bpodman\b.*?\bpush\b",
    r"\bpip\b.*?\bupload\b",
    r"\btwine\b.*?\bupload\b",
]


class VerificationSecurityError(PermissionError):
    """Erro caso um comando tente mutação remota ou publicação não autorizada."""
    pass


@dataclass
class CommandResult:
    command: str
    state: str  # PASS, FAIL, SKIPPED, NOT_RUN, TIMEOUT
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationEvidence:
    evidence_id: str
    timestamp: str
    project_name: str
    project_path: str
    branch: str | None
    commit_sha: str | None
    overall_state: str  # PASS, FAIL, SKIPPED, NOT_RUN
    fail_fast: bool
    total_duration_seconds: float
    commands: list[CommandResult]
    evidence_file: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["commands"] = [c.to_dict() if isinstance(c, CommandResult) else c for c in self.commands]
        return d


def validate_command_safety(cmd_str: str) -> None:
    """Impede execução de comandos mutáveis remotos ou perigosos durante verificação."""
    for pattern in FORBIDDEN_MUTABLE_PATTERNS:
        if re.search(pattern, cmd_str, re.IGNORECASE):
            raise VerificationSecurityError(
                f"Comando remoto mutável proibido em 'ch verify': '{sanitize_output(cmd_str)}'"
            )


def execute_single_command(cmd_str: str, cwd: Path, timeout: float = 120.0) -> CommandResult:
    """Executa um único comando capturando stdout/stderr sanitizados e tempo de execução."""
    validate_command_safety(cmd_str)
    sanitized_cmd = sanitize_output(cmd_str)

    run_env = os.environ.copy()
    try:
        import chdevflow
        pkg_src = str(Path(chdevflow.__file__).resolve().parent.parent)
        cur_pypath = run_env.get("PYTHONPATH", "")
        if pkg_src not in cur_pypath.split(os.pathsep):
            run_env["PYTHONPATH"] = f"{pkg_src}{os.pathsep}{cur_pypath}" if cur_pypath else pkg_src
    except Exception:
        pass

    # Se o comando iniciar com 'ch ' ou for 'ch', e o executável não estiver no PATH,
    # resolve autossuficientemente via sys.executable -m chdevflow.cli
    run_cmd = cmd_str
    stripped = cmd_str.strip()
    if (stripped == "ch" or stripped.startswith("ch ")) and shutil.which("ch") is None:
        sub_arg = stripped[2:].strip()
        run_cmd = f'"{sys.executable}" -m chdevflow.cli {sub_arg}' if sub_arg else f'"{sys.executable}" -m chdevflow.cli'

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            run_cmd,
            shell=True,
            cwd=str(cwd),
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        duration = round(time.perf_counter() - start_time, 3)
        stdout_clean = sanitize_output(proc.stdout)
        stderr_clean = sanitize_output(proc.stderr)
        state = "PASS" if proc.returncode == 0 else "FAIL"

        return CommandResult(
            command=sanitized_cmd,
            state=state,
            exit_code=proc.returncode,
            duration_seconds=duration,
            stdout=stdout_clean,
            stderr=stderr_clean,
        )
    except subprocess.TimeoutExpired:
        duration = round(time.perf_counter() - start_time, 3)
        return CommandResult(
            command=sanitized_cmd,
            state="TIMEOUT",
            exit_code=-1,
            duration_seconds=duration,
            stdout="",
            stderr="Timeout excedido na execução do comando.",
        )
    except FileNotFoundError:
        duration = round(time.perf_counter() - start_time, 3)
        return CommandResult(
            command=sanitized_cmd,
            state="FAIL",
            exit_code=-2,
            duration_seconds=duration,
            stdout="",
            stderr="Comando ou executável não encontrado.",
        )
    except Exception as exc:
        duration = round(time.perf_counter() - start_time, 3)
        return CommandResult(
            command=sanitized_cmd,
            state="FAIL",
            exit_code=-3,
            duration_seconds=duration,
            stdout="",
            stderr=f"Erro de execução: {exc}",
        )


def run_verification(
    project_path: Path | None = None,
    fail_fast: bool = True,
    timeout_per_command: float = 120.0,
    persist: bool = True,
) -> VerificationEvidence:
    """
    Executa a suíte de verificação definida no manifesto ou pelos adapters.
    Persiste evidência estruturada em .ch/evidence/<timestamp>-<id>.json.
    """
    target = (project_path or Path.cwd()).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {target}")

    git_info = check_git_status(target)

    # 1. Obter comandos de verificação
    manifest_file = target / "chdevflow.yaml"
    commands_to_run: list[str] = []
    project_name = target.name

    if manifest_file.is_file():
        try:
            m = load_manifest(manifest_file)
            project_name = m.get("project", {}).get("name", target.name)
            commands_to_run = list(m.get("verification", {}).get("commands", []))
        except ManifestError:
            pass

    # Fallback para adapters caso manifesto não defina comandos
    if not commands_to_run and manifest_file.is_file():
        try:
            m = load_manifest(manifest_file)
            stack = m.get("stack", {})
            for key in ["backend", "frontend"]:
                t = stack.get(key, {}).get("type")
                if t and t != "none":
                    ad = get_adapter(t)
                    if ad:
                        commands_to_run.extend(ad.get_default_verification_commands())
        except ManifestError:
            pass

    # Deduplica preservando ordem
    seen_cmds: set[str] = set()
    dedup_cmds: list[str] = []
    for c in commands_to_run:
        c_strip = c.strip()
        if c_strip and c_strip not in seen_cmds:
            seen_cmds.add(c_strip)
            dedup_cmds.append(c_strip)
    commands_to_run = dedup_cmds

    # Inicia evidência
    evidence_id = str(uuid.uuid4())[:8]
    now_utc = datetime.now(timezone.utc)
    timestamp_iso = now_utc.isoformat()
    timestamp_slug = now_utc.strftime("%Y%m%d-%H%M%S")

    if not commands_to_run:
        empty_evidence = VerificationEvidence(
            evidence_id=evidence_id,
            timestamp=timestamp_iso,
            project_name=project_name,
            project_path=str(target),
            branch=git_info["branch"],
            commit_sha=git_info["commit_sha"],
            overall_state="NOT_RUN",
            fail_fast=fail_fast,
            total_duration_seconds=0.0,
            commands=[],
        )
        return empty_evidence

    results: list[CommandResult] = []
    has_failure = False
    total_start = time.perf_counter()

    for i, cmd in enumerate(commands_to_run):
        if has_failure and fail_fast:
            results.append(CommandResult(
                command=sanitize_output(cmd),
                state="SKIPPED",
                exit_code=None,
                duration_seconds=0.0,
                stdout="",
                stderr="Ignorado devido a falha anterior com fail-fast ativo.",
            ))
            continue

        res = execute_single_command(cmd, cwd=target, timeout=timeout_per_command)
        results.append(res)
        if res.state != "PASS":
            has_failure = True

    total_duration = round(time.perf_counter() - total_start, 3)
    overall_state = "FAIL" if has_failure else "PASS"

    evidence = VerificationEvidence(
        evidence_id=evidence_id,
        timestamp=timestamp_iso,
        project_name=project_name,
        project_path=str(target),
        branch=git_info["branch"],
        commit_sha=git_info["commit_sha"],
        overall_state=overall_state,
        fail_fast=fail_fast,
        total_duration_seconds=total_duration,
        commands=results,
    )

    if persist:
        evidence_dir = target / ".ch" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        file_path = evidence_dir / f"{timestamp_slug}-{evidence_id}.json"
        file_path.write_text(json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        evidence.evidence_file = str(file_path)

    return evidence


def render_evidence_human(ev: VerificationEvidence) -> str:
    """Renderiza tabela de verificação para visualização no terminal."""
    lines: list[str] = []
    lines.append("=" * 65)
    lines.append(f"CHDevFlow Verify — Resultado da Verificação: {ev.project_name}")
    lines.append(f"ID Evidência: {ev.evidence_id} | Data UTC: {ev.timestamp}")
    lines.append(f"Branch: {ev.branch or 'N/A'} | Commit: {ev.commit_sha or 'N/A'}")
    lines.append("=" * 65)

    if not ev.commands:
        lines.append("\n  [!] Nenhum check de verificação encontrado no manifesto.")
        lines.append("      Estado geral: NOT_RUN (não convertido em sucesso).")
    else:
        lines.append("\n[Execução dos Checks]")
        for c in ev.commands:
            if c.state == "PASS":
                sym = "✓"
            elif c.state in ("FAIL", "TIMEOUT"):
                sym = "✗"
            else:
                sym = "—"
            dur_str = f"({c.duration_seconds}s)"
            exit_str = f"code {c.exit_code}" if c.exit_code is not None else ""
            lines.append(f"  {sym} [{c.state:<7}] {dur_str:<9} {c.command:<35} {exit_str}")
            if c.state in ("FAIL", "TIMEOUT") and c.stderr:
                err_preview = c.stderr.strip().splitlines()[-1][:70]
                lines.append(f"      Erro: {err_preview}")

    lines.append("\n" + "-" * 65)
    lines.append(f"Estado Geral : {ev.overall_state}")
    lines.append(f"Duração Total: {ev.total_duration_seconds}s (fail-fast: {ev.fail_fast})")
    if ev.evidence_file:
        lines.append(f"Evidência salva em: {ev.evidence_file}")
    lines.append("=" * 65)

    return "\n".join(lines)
