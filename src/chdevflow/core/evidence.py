"""Execução segura de verificações do projeto e persistência de evidências estruturadas.

Implementa modelo estrito de execução defensiva (shell=False), allowlist de executáveis
e subcomandos, higienização compulsória de ambiente, confinamento de PATH/PYTHONPATH,
resolução de origem física, leitura com limite de memória e política de confiança (Project Trust).
NÃO constitui sandbox de sistema operacional.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from chdevflow.adapters import get_adapter
from chdevflow.adapters.base import sanitize_output
from chdevflow.core.config import load_manifest, ManifestError, ManifestSecurityError
from chdevflow.core.status import check_git_status
from chdevflow.core.trust import check_trust, grant_trust

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

FORBIDDEN_SHELL_METACHUTE: tuple[str, ...] = (
    ";", "&&", "||", "|", "&", ">", ">>", "<", "$(", "`", "\n", "\r"
)

ALLOWED_VERIFICATION_BINARIES: frozenset[str] = frozenset({
    "ch", "python", "python3", "pytest", "npm", "pnpm", "yarn",
    "dotnet", "mvn", "gradle", "cargo", "go", "echo", "true", "false", "test", "exit"
})

ALLOWED_LIFECYCLE_SCRIPTS: frozenset[str] = frozenset({
    "test", "test:unit", "test:ci", "lint", "check", "typecheck", "build"
})

ALLOWED_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "ch": frozenset({"status", "tree"}),
    "npm": frozenset({"test", "run"}),
    "pnpm": frozenset({"test", "run"}),
    "yarn": frozenset({"test", "run"}),
    "dotnet": frozenset({"test", "build"}),
    "mvn": frozenset({"test", "verify", "check"}),
    "gradle": frozenset({"test", "verify", "check"}),
    "cargo": frozenset({"test", "check", "clippy"}),
    "go": frozenset({"test"}),
}

ALLOWED_PYTHON_MODULES: frozenset[str] = frozenset({"unittest", "pytest"})
FORBIDDEN_PYTHON_FLAGS: frozenset[str] = frozenset({"-c", "--command", "-i", "-e"})

ALLOWED_ENV_VARS: frozenset[str] = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "PYTHONPATH", "NODE_ENV", "TERM"
})

DISALLOWED_PATH_ANCESTORS: tuple[str, ...] = ("/tmp", "/var/tmp", "/dev/shm")
MAX_OUTPUT_BYTES = 5 * 1024 * 1024  # 5 MB por stream


class VerificationSecurityError(PermissionError):
    """Erro em caso de comando, argumento, executável ou manifesto não autorizado."""
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


def sanitize_subprocess_env(
    source_env: dict[str, str] | None,
    project_root: Path
) -> dict[str, str]:
    """
    Higieniza compulsoriamente qualquer ambiente (inclusive fornecido por chamador),
    expurgando credenciais e controlando PATH e PYTHONPATH.
    """
    raw = source_env if source_env is not None else os.environ.copy()
    clean = {k: v for k, v in raw.items() if k in ALLOWED_ENV_VARS}

    # 1. Higienização e confinamento do PATH antes de qualquer canonicalização
    raw_path = clean.get("PATH", os.environ.get("PATH", ""))
    safe_path_parts: list[str] = []
    root_resolved = project_root.resolve()

    for entry in raw_path.split(os.pathsep):
        entry_stripped = entry.strip()
        # Rejeita entradas vazias (que equivalem a . no POSIX)
        if not entry_stripped:
            continue
        p_raw = Path(entry_stripped)
        # Rejeita caminhos relativos ANTES de canonicalizar
        if not p_raw.is_absolute():
            continue
        # Rejeita traversals antes de canonicalizar
        if ".." in p_raw.parts:
            continue

        try:
            p_resolved = p_raw.resolve()
        except Exception:
            continue

        # Rejeita diretórios que apontem para a raiz do projeto ou subpastas
        if p_resolved == root_resolved or p_resolved.is_relative_to(root_resolved):
            continue

        # Rejeita pastas temporárias públicas mundiais
        if any(p_resolved == Path(bad) or p_resolved.is_relative_to(Path(bad)) for bad in DISALLOWED_PATH_ANCESTORS):
            continue

        # Rejeita diretórios graváveis por qualquer usuário (world-writable)
        try:
            st = p_resolved.stat()
            if st.st_mode & 0o002:
                continue
        except Exception:
            continue

        str_p = str(p_resolved)
        if str_p not in safe_path_parts and p_resolved.is_dir():
            safe_path_parts.append(str_p)

    # Assegura inclusão de diretórios canônicos do sistema e do virtualenv ativo
    sys_dirs = ["/usr/bin", "/bin", "/usr/local/bin"]
    if sys.prefix:
        venv_bin = str(Path(sys.prefix) / "bin")
        if venv_bin not in safe_path_parts and Path(venv_bin).is_dir():
            safe_path_parts.insert(0, venv_bin)
    for sd in sys_dirs:
        if sd not in safe_path_parts and Path(sd).is_dir():
            safe_path_parts.append(sd)

    clean["PATH"] = os.pathsep.join(safe_path_parts)

    # 2. Confinamento estrito de PYTHONPATH
    clean_pypaths: list[str] = []
    try:
        import chdevflow
        pkg_src = str(Path(chdevflow.__file__).resolve().parent.parent)
        clean_pypaths.append(pkg_src)
    except Exception:
        pass
    if (root_resolved / "src").is_dir():
        clean_pypaths.append(str(root_resolved / "src"))
    clean["PYTHONPATH"] = os.pathsep.join(clean_pypaths)

    return clean


def safe_resolve_executable(bin_name: str, sanitized_path: str, project_root: Path) -> str:
    """Resolve o executável no PATH seguro e valida sua origem física e permissões."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", bin_name):
        raise VerificationSecurityError(f"Nome de executável inválido: '{bin_name}'.")

    # Resolução do ch e exit via interpretador atual
    if bin_name in ("ch", "exit"):
        return sys.executable

    resolved_str = shutil.which(bin_name, path=sanitized_path)
    if not resolved_str:
        raise VerificationSecurityError(f"Executável '{bin_name}' não encontrado no PATH seguro.")

    resolved = Path(resolved_str).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise VerificationSecurityError(f"Executável '{bin_name}' sem permissão de execução: '{resolved}'.")

    root_resolved = project_root.resolve()
    if resolved == root_resolved or resolved.is_relative_to(root_resolved):
        raise VerificationSecurityError(
            f"Executável não autorizado situado dentro da raiz do projeto: '{resolved}'."
        )

    for bad in DISALLOWED_PATH_ANCESTORS:
        if resolved == Path(bad) or resolved.is_relative_to(Path(bad)):
            raise VerificationSecurityError(
                f"Executável não autorizado situado em pasta temporária: '{resolved}'."
            )

    return str(resolved)


def parse_and_validate_command(cmd_str: str, project_root: Path, sanitized_path: str) -> list[str]:
    """
    Valida operadores de shell, executáveis, subcomandos e argumentos estruturados.
    Retorna lista de tokens sanitizada para execução sem shell (shell=False).
    """
    if not isinstance(cmd_str, str) or not cmd_str.strip():
        raise VerificationSecurityError("Comando de verificação inválido ou vazio.")

    validate_command_safety(cmd_str)

    # Bloqueio de metacaracteres de shell
    for op in FORBIDDEN_SHELL_METACHUTE:
        if op in cmd_str:
            raise VerificationSecurityError(
                f"Metacaractere de shell proibido '{op}' detectado: '{sanitize_output(cmd_str)}'"
            )

    tokens = shlex.split(cmd_str, posix=True)
    if not tokens:
        raise VerificationSecurityError("Lista de argumentos vazia após tokenização.")

    bin_name = tokens[0].lower()
    if bin_name not in ALLOWED_VERIFICATION_BINARIES:
        raise VerificationSecurityError(
            f"Executável não autorizado em 'ch verify': '{bin_name}'. "
            f"Permitidos: {', '.join(sorted(ALLOWED_VERIFICATION_BINARIES))}"
        )

    # 1. Validação física do executável
    resolved_bin = safe_resolve_executable(bin_name, sanitized_path, project_root)

    # 2. Tratamento de simulação de exit
    if bin_name == "exit":
        args = tokens[1:]
        exit_code = 0
        if args:
            if not args[0].isdigit():
                raise VerificationSecurityError("Argumento para 'exit' deve ser um código numérico.")
            exit_code = int(args[0])
        return [sys.executable, "-c", f"import sys; sys.exit({exit_code})"]

    # 2. Validação profunda de Python
    if bin_name in ("python", "python3"):
        args = tokens[1:]
        if not args:
            raise VerificationSecurityError("Invocação de Python sem argumentos ou módulo.")
        for f in FORBIDDEN_PYTHON_FLAGS:
            if f in args:
                raise VerificationSecurityError(f"Flag proibida em comando Python: '{f}'.")
        if "-m" in args:
            m_idx = args.index("-m")
            if m_idx + 1 >= len(args):
                raise VerificationSecurityError("Flag '-m' sem especificação de módulo.")
            mod = args[m_idx + 1]
            if mod not in ALLOWED_PYTHON_MODULES:
                raise VerificationSecurityError(f"Módulo Python não autorizado: '{mod}'.")
        else:
            # Script alvo: deve ser caminho relativo interno ao projeto
            script_path_str = args[0]
            if Path(script_path_str).is_absolute():
                raise VerificationSecurityError("Caminho absoluto de script não permitido em 'ch verify'.")
            if ".." in Path(script_path_str).parts:
                raise VerificationSecurityError("Path traversal detectado em script Python.")
            resolved_script = (project_root / script_path_str).resolve()
            if not resolved_script.is_relative_to(project_root.resolve()):
                raise VerificationSecurityError("Script reside fora da raiz do projeto.")

    # 3. Validação de npm / pnpm / yarn (incluindo fechamento de npm run <script>)
    elif bin_name in ("npm", "pnpm", "yarn"):
        if len(tokens) < 2:
            raise VerificationSecurityError(f"Subcomando obrigatório para '{bin_name}'.")
        sub = tokens[1].lower()
        if sub not in ALLOWED_SUBCOMMANDS[bin_name]:
            raise VerificationSecurityError(f"Subcomando '{sub}' não autorizado para '{bin_name}'.")
        if sub == "run":
            if len(tokens) < 3:
                raise VerificationSecurityError(f"Script obrigatório após '{bin_name} run'.")
            target_script = tokens[2].lower()
            if target_script not in ALLOWED_LIFECYCLE_SCRIPTS:
                raise VerificationSecurityError(
                    f"Script de ciclo de vida '{target_script}' não autorizado em '{bin_name} run'. "
                    f"Permitidos: {', '.join(sorted(ALLOWED_LIFECYCLE_SCRIPTS))}"
                )

    # 4. Outros subcomandos (dotnet, mvn, cargo, go)
    elif bin_name in ALLOWED_SUBCOMMANDS:
        sub = tokens[1].lower() if len(tokens) > 1 else ""
        if sub not in ALLOWED_SUBCOMMANDS[bin_name]:
            raise VerificationSecurityError(
                f"Subcomando '{sub}' não autorizado para '{bin_name}'. "
                f"Permitidos: {', '.join(sorted(ALLOWED_SUBCOMMANDS[bin_name]))}"
            )

    # 5. Tratamento de resolução do ch
    if bin_name == "ch":
        tokens = [sys.executable, "-m", "chdevflow.cli"] + tokens[1:]
    else:
        tokens[0] = resolved_bin

    return tokens


def _read_pipe_bounded(pipe, chunks: list[bytes], max_bytes: int, truncated_flag: list[bool]) -> None:
    """Lê pipe em chunks aplicando limite de memória em tempo real durante a leitura."""
    bytes_read = 0
    try:
        while True:
            chunk = pipe.read(65536)
            if not chunk:
                break
            if bytes_read < max_bytes:
                to_take = min(len(chunk), max_bytes - bytes_read)
                chunks.append(chunk[:to_take])
                bytes_read += to_take
                if len(chunk) > to_take:
                    truncated_flag[0] = True
            else:
                truncated_flag[0] = True
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def execute_single_command(
    cmd_str: str,
    cwd: Path,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """
    Executa um único comando sem shell interpretativo (shell=False),
    com higienização universal de ambiente, limite de memória e timeout em 2 estágios.
    """
    project_root = cwd.resolve()
    sanitized_env = sanitize_subprocess_env(env, project_root)
    sanitized_path = sanitized_env.get("PATH", "")

    try:
        tokens = parse_and_validate_command(cmd_str, project_root, sanitized_path)
    except VerificationSecurityError:
        raise
    except Exception as exc:
        raise VerificationSecurityError(f"Erro de validação de comando: {exc}")

    sanitized_cmd = sanitize_output(cmd_str)
    start_time = time.perf_counter()
    is_posix = (os.name != "nt")

    try:
        proc = subprocess.Popen(
            tokens,
            cwd=str(project_root),
            env=sanitized_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=is_posix,  # Novo grupo de processos em POSIX
        )

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        stdout_trunc = [False]
        stderr_trunc = [False]

        t_out = threading.Thread(
            target=_read_pipe_bounded,
            args=(proc.stdout, stdout_chunks, MAX_OUTPUT_BYTES, stdout_trunc),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_read_pipe_bounded,
            args=(proc.stderr, stderr_chunks, MAX_OUTPUT_BYTES, stderr_trunc),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Encerramento em 2 estágios do grupo de processos (POSIX) ou kill de processo (Windows)
            if is_posix:
                pgid = proc.pid
                # 1. Envia SIGTERM para todo o grupo de processos
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

                # 2. Aguarda até a carência (2.0s) verificando se TODO o grupo encerrou
                # Garante que mesmo se o líder terminar imediatamente, descendentes continuem sendo monitorados
                grace_deadline = time.time() + 2.0
                while time.time() < grace_deadline:
                    try:
                        # os.killpg(pgid, 0) verifica se ainda há qualquer processo vivo no grupo
                        os.killpg(pgid, 0)
                        time.sleep(0.05)
                    except ProcessLookupError:
                        break
                    except PermissionError:
                        break

                # 3. Se ainda houver qualquer processo remanescente no grupo após a carência, envia SIGKILL
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
            else:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
                except Exception:
                    proc.kill()
                proc.wait()

        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)

        duration = round(time.perf_counter() - start_time, 3)
        raw_stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        raw_stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        if stdout_trunc[0]:
            raw_stdout += "\n[AVISO DE SEGURANÇA: Saída stdout truncada ao atingir o teto de 5 MB]"
        if stderr_trunc[0]:
            raw_stderr += "\n[AVISO DE SEGURANÇA: Saída stderr truncada ao atingir o teto de 5 MB]"

        stdout_clean = sanitize_output(raw_stdout)
        stderr_clean = sanitize_output(raw_stderr)

        if timed_out:
            return CommandResult(
                command=sanitized_cmd,
                state="TIMEOUT",
                exit_code=-1,
                duration_seconds=duration,
                stdout=stdout_clean,
                stderr=stderr_clean or "Timeout excedido na execução do comando. Grupo de processos encerrado.",
            )

        state = "PASS" if proc.returncode == 0 else "FAIL"
        return CommandResult(
            command=sanitized_cmd,
            state=state,
            exit_code=proc.returncode,
            duration_seconds=duration,
            stdout=stdout_clean,
            stderr=stderr_clean,
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
    except VerificationSecurityError:
        raise
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
    trust: bool = False,
    dry_run: bool = False,
) -> VerificationEvidence:
    """
    Executa a suíte de verificação do projeto com validação fail-closed,
    controle de trust e isolamento de processos.
    """
    target = (project_path or Path.cwd()).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {target}")

    git_info = check_git_status(target)

    # Inicia IDs e datas
    evidence_id = str(uuid.uuid4())[:8]
    now_utc = datetime.now(timezone.utc)
    timestamp_iso = now_utc.isoformat()
    timestamp_slug = now_utc.strftime("%Y%m%d-%H%M%S")

    # 1. Carregamento estrito do manifesto (FAIL-CLOSED)
    manifest_file = target / "chdevflow.yaml"
    commands_to_run: list[str] = []
    project_name = target.name
    manifest_load_error: str | None = None

    if manifest_file.is_file():
        try:
            m = load_manifest(manifest_file)
            project_name = m.get("project", {}).get("name", target.name)
            raw_cmds = m.get("verification", {}).get("commands", [])
            commands_to_run = list(raw_cmds)
        except (ManifestError, ManifestSecurityError) as exc:
            manifest_load_error = str(exc)
        except Exception as exc:
            manifest_load_error = f"Erro inesperado no manifesto: {exc}"

    # Falha imediata em caso de erro no manifesto
    if manifest_load_error is not None:
        failed_res = CommandResult(
            command="load_manifest(chdevflow.yaml)",
            state="FAIL",
            exit_code=-3,
            duration_seconds=0.0,
            stdout="",
            stderr=f"Falha de validação do manifesto (fail-closed): {manifest_load_error}",
        )
        failed_evidence = VerificationEvidence(
            evidence_id=evidence_id,
            timestamp=timestamp_iso,
            project_name=target.name,
            project_path=str(target),
            branch=git_info["branch"],
            commit_sha=git_info["commit_sha"],
            overall_state="FAIL",
            fail_fast=fail_fast,
            total_duration_seconds=0.0,
            commands=[failed_res],
        )
        if persist:
            evidence_dir = target / ".ch" / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            file_path = evidence_dir / f"{timestamp_slug}-{evidence_id}.json"
            file_path.write_text(json.dumps(failed_evidence.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            failed_evidence.evidence_file = str(file_path)
        return failed_evidence

    # Fallback para adapters caso manifesto não defina comandos mas seja válido
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
        except Exception:
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

    # Gate estrutural obrigatório: todo manifesto com verificações deve executar ch status --strict primeiro
    if commands_to_run:
        strict_gate = "ch status --strict"
        cleaned_cmds = [c for c in commands_to_run if c not in (strict_gate, "ch status")]
        commands_to_run = [strict_gate] + cleaned_cmds

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

    # 2. Modo Dry-Run (inspeção segura sem execução de subprocessos)
    if dry_run:
        dry_results: list[CommandResult] = []
        has_val_err = False
        sanitized_path = sanitize_subprocess_env(None, target).get("PATH", "")
        for cmd in commands_to_run:
            try:
                parse_and_validate_command(cmd, target, sanitized_path)
                dry_results.append(CommandResult(
                    command=sanitize_output(cmd),
                    state="NOT_RUN",
                    exit_code=0,
                    duration_seconds=0.0,
                    stdout="",
                    stderr="Modo dry-run: comando validado estruturalmente mas não executado.",
                ))
            except VerificationSecurityError as sec_err:
                has_val_err = True
                dry_results.append(CommandResult(
                    command=sanitize_output(cmd),
                    state="FAIL",
                    exit_code=-3,
                    duration_seconds=0.0,
                    stdout="",
                    stderr=f"Rejeitado na validação de dry-run: {sec_err}",
                ))

        dry_evidence = VerificationEvidence(
            evidence_id=evidence_id,
            timestamp=timestamp_iso,
            project_name=project_name,
            project_path=str(target),
            branch=git_info["branch"],
            commit_sha=git_info["commit_sha"],
            overall_state="FAIL" if has_val_err else "PASS",
            fail_fast=fail_fast,
            total_duration_seconds=0.0,
            commands=dry_results,
        )
        return dry_evidence

    # 3. Política de Confiança (Project Trust)
    # Comandos de projeto (além do ch status --strict interno) requerem registro de confiança válido
    project_commands = [c for c in commands_to_run if c not in ("ch status --strict", "ch status")]
    is_trusted = True
    trust_reason = ""
    if project_commands:
        if trust:
            grant_trust(target, declaration="Consentimento explícito concedido via argumento --trust.")
            is_trusted = True
        else:
            is_trusted, trust_reason = check_trust(target)

    # 4. Execução sequencial dos comandos
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

        # Se for comando de projeto e o projeto não for confiável, bloqueia a execução
        if cmd not in ("ch status --strict", "ch status") and not is_trusted:
            results.append(CommandResult(
                command=sanitize_output(cmd),
                state="FAIL",
                exit_code=-4,
                duration_seconds=0.0,
                stdout="",
                stderr=f"Verificação bloqueada pela política de confiança: {trust_reason}",
            ))
            has_failure = True
            continue

        try:
            res = execute_single_command(cmd, cwd=target, timeout=timeout_per_command)
        except VerificationSecurityError as sec_exc:
            res = CommandResult(
                command=sanitize_output(cmd),
                state="FAIL",
                exit_code=-3,
                duration_seconds=0.0,
                stdout="",
                stderr=f"Bloqueado por violação de segurança: {sec_exc}",
            )

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
