"""Executor local de CLIs AGY/Codex, sem daemon ou sandbox obrigatório.

Os processos herdam o contexto da sessão do usuário que inicia o CHDevFlow.
Não transfere tokens, não tenta login silencioso e não executa agentes ao importar.
Compatível com Windows e Linux; a autenticação só é comprovada por turno real.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from typing import Mapping, Callable

_DROP_API_KEYS = (
    "OPENAI_API_KEY", "CODEX_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
)


@dataclass(frozen=True)
class LocalAgents:
    platform: str
    agy: tuple[str, ...]
    codex: tuple[str, ...]
    auth_verified: bool = False
    isolated_by_os: bool = False

    @property
    def ready(self) -> bool:
        return bool(self.agy and self.codex)

    def public_report(self) -> dict:
        return {
            "status": "CLIS_ENCONTRADAS_LOGIN_NAO_VERIFICADO" if self.ready else "CLIS_AUSENTES",
            "platform": self.platform,
            "agy_available": bool(self.agy),
            "codex_available": bool(self.codex),
            "auth_verified": self.auth_verified,
            "os_isolation_verified": self.isolated_by_os,
            "execution_context": "usuario_local_do_processo",
            "next_action": "lab-pilot com aceite explicito" if self.ready else "instalar CLIs no PATH local",
        }


def resolve_local_agents(*, platform: str | None = None,
                         which: Callable[[str], str | None] | None = None,
                         is_file: Callable[[Path], bool] | None = None) -> LocalAgents:
    """Resolve wrappers sem executar ou consultar autenticadores do usuário."""
    system = platform or sys.platform
    lookup = which or shutil.which
    exists = is_file or (lambda p: p.is_file())
    if system not in ("win32", "linux"):
        return LocalAgents(system, (), ())
    agy = (lookup("agy.exe") or lookup("agy")) if system == "win32" else lookup("agy")
    codex: list[str] = []
    if system == "win32":
        native = lookup("codex.exe")
        if native:
            codex = [native]
        else:
            wrapper = lookup("codex.cmd")
            if wrapper:
                npm_root = Path(wrapper).parent
                entry = npm_root / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
                node_local = npm_root / "node.exe"
                node = str(node_local) if exists(node_local) else lookup("node.exe")
                if node and exists(entry):
                    codex = [node, str(entry)]
                else:
                    # Wrapper .cmd é executável pelo Windows; não usar shell=True.
                    codex = [wrapper]
            else:
                ps1 = lookup("codex.ps1")
                powershell = lookup("powershell.exe") or lookup("pwsh.exe")
                if ps1 and powershell:
                    codex = [powershell, "-NoProfile", "-NonInteractive", "-File", ps1]
    else:
        found = lookup("codex")
        if found:
            codex = [found]
    return LocalAgents(system, (agy,) if agy else (), tuple(codex))


def local_agent_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Herdar HOME, APPDATA, USERPROFILE etc preserva o login do mesmo usuário.

    Só retira chaves API conhecidas para evitar fallback faturável não intencional;
    nunca imprime valores ou transfere credenciais de outro usuário.
    """
    env = dict(os.environ if base is None else base)
    for name in _DROP_API_KEYS:
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    return env


@dataclass(frozen=True)
class LocalProcessResult:
    code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _kill_tree(process: subprocess.Popen, *, platform: str) -> None:
    if process.poll() is not None:
        return
    if platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            if process.poll() is None:
                process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def run_local_command(command: list[str], *, cwd: Path, stdin: str | None,
                      timeout: int, platform: str | None = None,
                      env: Mapping[str, str] | None = None) -> LocalProcessResult:
    """Popen real sob o usuário atual, com limite de tempo e limpeza da árvore.

    Não afirma que há sandbox: não executar código de terceiros fora de
    diretório descartável sem avaliar os riscos da máquina.
    """
    system = platform or sys.platform
    if system not in ("win32", "linux"):
        raise ValueError("Windows/Linux são os sistemas suportados")
    if not command or not isinstance(timeout, int) or timeout < 1:
        raise ValueError("Comando/timeout inválidos")
    if not cwd.is_dir():
        raise ValueError("Workspace local inexistente")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if system == "win32" else 0
    process = subprocess.Popen(
        command, cwd=cwd, env=local_agent_environment(env),
        text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=flags, start_new_session=(system != "win32"),
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout)
        return LocalProcessResult(process.returncode, stdout or "", stderr or "")
    except subprocess.TimeoutExpired as exc:
        _kill_tree(process, platform=system)
        def decode(value: bytes | str | None) -> str:
            return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
        return LocalProcessResult(-1, decode(exc.stdout),
                                  decode(exc.stderr) + "\nTIMEOUT: processo interrompido", True)
    except BaseException:
        _kill_tree(process, platform=system)
        raise
