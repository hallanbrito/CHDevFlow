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


def _executables() -> tuple[list[str], list[str]]:
    """Verificacao read-only das CLIs no PATH da sessao local."""
    agents = resolve_local_agents()
    return list(agents.agy), list(agents.codex)


def _doctor() -> dict:
    import getpass
    import platform as os_platform
    agy, codex = _executables()
    return {
        "status": "PRONTO_PARA_LAB" if agy and codex else "FALTAM_CLIS",
        "host_os": os_platform.system(),
        "current_user": getpass.getuser(),
        "agy_detected": bool(agy),
        "codex_detected": bool(codex),
        "authentication_verified": False,
        "credential_access_verified": False,
        "isolation_verified": False,
        "note": "CLI encontrada nao comprova login. Rodar na mesma conta autenticada.",
    }


def run_local_pilot(**kwargs):
    """Import tardio: experimental_pilot usa este modulo para subprocessos."""
    from chdevflow.core.experimental_pilot import run_local_pilot as pilot
    return pilot(**kwargs)


def run_controlled_pilot(**kwargs):
    """Import tardio: ciclo CCC-01 sem acoplamento ao executor de processos."""
    from chdevflow.core.controlled_cycle import run_controlled_pilot as cycle
    return cycle(**kwargs)


def main(argv: list[str] | None = None) -> int:
    """Entradas de CLI multiplataforma: doctor, run (F5) e cycle (CCC-01)."""
    import argparse
    import getpass
    import json
    import platform as os_platform
    from uuid import uuid4
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser(prog="ch-local")
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("doctor", help="Encontra CLIs sem chamadas de IA.")
    for command in ("run", "cycle"):
        sub = subs.add_parser(command, help=(
            "F5 - tentativa unica" if command == "run"
            else "CCC-01 - ate 3 AGY e 2 devolucoes, com tempo total limitado"
        ))
        sub.add_argument("--root", type=Path, default=Path.home() / "CHDevFlow-Labs")
        sub.add_argument("--timeout", type=int, default=480)
        sub.add_argument("--i-accept-local-risk", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "doctor":
        result = _doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PRONTO_PARA_LAB" else 2
    if not args.i_accept_local_risk:
        print("BLOQUEADO: use --i-accept-local-risk para chamar agentes reais", file=sys.stderr)
        return 2
    if type(args.timeout) is not int or not 120 <= args.timeout <= 900:
        print("BLOQUEADO: timeout TOTAL permitido 120..900 segundos", file=sys.stderr)
        return 2
    root = args.root.expanduser().absolute()
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        print("BLOQUEADO: raiz invalida", file=sys.stderr)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    ident = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:10]
    workspace = root / f"CH-Lab-{ident}"
    evidence = root / f"CH-Dossie-{ident}"
    print(json.dumps({
        "action": args.action, "host_os": os_platform.system(),
        "current_user": getpass.getuser(), "workspace": str(workspace),
        "evidence_dir": str(evidence),
        "timeout_total": args.timeout,
    }, ensure_ascii=False))
    try:
        runner = run_controlled_pilot if args.action == "cycle" else run_local_pilot
        result = runner(
            workspace=workspace, evidence=evidence, accepted=True,
            timeout=args.timeout)
    except (ValueError, PermissionError, OSError) as exc:
        print(f"LAB_BLOQUEADO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print(f"DOSSIE_CH1: {evidence / 'RELATORIO_COMPLETO_CH1.md'}")
    return 0 if result.status in (
        "LAB_APROVADO_AGUARDANDO_CH1", "APROVADO_AGUARDANDO_CH1"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
