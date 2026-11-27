#!/usr/bin/env python3
"""Reproducible, credential-free Docker proof for the official Copilot CLI."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Mapping, Sequence
from uuid import uuid4


CLI_VERSION = "1.0.117"
IMAGE_DIGESTS = {
    "amd64": "sha256:6a816154086e00511cdc87563def1bb529dffef966288b0ce26677af7eb3ff1c",
    "arm64": "sha256:dcb3397e37c80f0a7edccd72d8af1ac78bf6086c37d1fe2772f1e5cbaebdb8e4",
}
IMAGE_REPOSITORY = "ghcr.io/github/copilot-cli"
WORKSPACE_TARGET = "/home/copilot/workspace"
CONTAINER_USER = "10001:10001"
MEMORY_BYTES = 2 * 1024 * 1024 * 1024
TMPFS_DEFAULT_SIZE_BYTES = 16 * 1024 * 1024
TMPFS_SIZE_BYTES = 1024 * 1024 * 1024
PID_LIMIT = 64
CPU_LIMIT = "1"
MAX_COMMAND_SECONDS = 60
_CONTAINER_ID = re.compile(r"^[0-9a-f]{12,64}$")
_CREDENTIAL_ENV_VARS = (
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_PROVIDER_API_KEY",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
)


class SandboxError(RuntimeError):
    """A required Docker security control or proof step failed."""


@dataclass(frozen=True)
class DockerCapabilities:
    server_version: str
    rootless: bool
    seccomp: bool
    compose_version: str | None
    image: str


@dataclass(frozen=True)
class ContainerResult:
    container_id: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    cancelled: bool
    removed: bool


def _platform_arch(machine: str | None = None) -> str:
    name = (machine or platform.machine()).lower()
    if name in ("x86_64", "amd64"):
        return "amd64"
    if name in ("aarch64", "arm64"):
        return "arm64"
    raise SandboxError(f"Arquitetura sem digest oficial fixado: {name}")


def image_reference(machine: str | None = None) -> tuple[str, str]:
    arch = _platform_arch(machine)
    return f"{IMAGE_REPOSITORY}@{IMAGE_DIGESTS[arch]}", f"linux/{arch}"


def _docker_environment(
    base: Mapping[str, str], docker_config: str
) -> dict[str, str]:
    environment = {
        name: base[name]
        for name in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "DOCKER_HOST")
        if name in base
    }
    docker_host = environment.get("DOCKER_HOST", "")
    if docker_host and not docker_host.startswith("unix://"):
        raise SandboxError("Somente daemon Docker local via socket Unix é permitido.")
    environment["DOCKER_CONFIG"] = docker_config
    return environment


def _workspace_path(workspace: Path) -> Path:
    absolute = workspace.expanduser().absolute()
    resolved = absolute.resolve(strict=True)
    if absolute != resolved or not resolved.is_dir():
        raise SandboxError("Workspace deve ser um diretório real, sem symlinks.")
    if "," in str(resolved):
        raise SandboxError("Workspace com vírgula no caminho não é suportado.")
    return resolved


def _validate_container(
    details: dict[str, object], image: str, workspace: Path
) -> None:
    config = details.get("Config")
    host = details.get("HostConfig")
    mounts = details.get("Mounts")
    if not isinstance(config, dict) or not isinstance(host, dict) or not isinstance(mounts, list):
        raise SandboxError("Docker inspect retornou configuração incompleta.")

    requirements = (
        (config.get("Image") == image, "imagem não corresponde ao digest fixado"),
        (config.get("User") == CONTAINER_USER, "usuário do container não é não-root"),
        (host.get("Privileged") is False, "container privilegiado"),
        (host.get("CapDrop") == ["ALL"], "capabilities não foram removidas"),
        (host.get("ReadonlyRootfs") is True, "root filesystem não é somente leitura"),
        (host.get("NetworkMode") == "none", "rede do container não está bloqueada"),
        (host.get("PidsLimit") == PID_LIMIT, "limite de PIDs ausente"),
        (host.get("Memory") == MEMORY_BYTES, "limite de memória ausente"),
        (host.get("NanoCpus") == 1_000_000_000, "limite de CPU ausente"),
    )
    for passed, reason in requirements:
        if not passed:
            raise SandboxError(f"Controle Docker obrigatório ausente: {reason}.")

    security_options = host.get("SecurityOpt")
    if not isinstance(security_options, list) or not all(
        isinstance(option, str) for option in security_options
    ):
        raise SandboxError("Docker retornou SecurityOpt inválido.")
    if not any(
        option.startswith("no-new-privileges") for option in security_options
    ):
        raise SandboxError("no-new-privileges não está ativo.")
    seccomp_profiles = [
        option.partition("=")[2]
        for option in security_options
        if option.startswith("seccomp=")
    ]
    if any(profile != "default" for profile in seccomp_profiles):
        raise SandboxError("Somente o perfil seccomp padrão é permitido.")

    bind_mounts = [
        mount
        for mount in mounts
        if isinstance(mount, dict) and mount.get("Type") == "bind"
    ]
    if len(bind_mounts) != 1 or len(mounts) != 1:
        summary = ", ".join(
            f"{mount.get('Type', '?')}:{mount.get('Destination', '?')}"
            for mount in mounts
            if isinstance(mount, dict)
        )
        raise SandboxError(
            "O container deve receber somente o bind do workspace. "
            f"Montagens observadas (tipo:destino): {summary or 'nenhuma'}."
        )
    mount = bind_mounts[0]
    if not (
        mount.get("Type") == "bind"
        and mount.get("Source") == str(workspace)
        and mount.get("Destination") == WORKSPACE_TARGET
        and mount.get("RW") is False
    ):
        raise SandboxError("Montagem do workspace não corresponde à política somente leitura.")

    tmpfs = host.get("Tmpfs")
    if not isinstance(tmpfs, dict) or set(tmpfs) != {"/tmp", "/var/tmp"}:
        raise SandboxError("Tmpfs permitido somente em /tmp e /var/tmp.")
    size_units = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    for destination, (expected_size, noexec) in {
        "/tmp": (TMPFS_DEFAULT_SIZE_BYTES, True),
        "/var/tmp": (TMPFS_SIZE_BYTES, False),
    }.items():
        tmpfs_options = tmpfs[destination]
        if not isinstance(tmpfs_options, str):
            raise SandboxError("Opções do tmpfs são inválidas.")
        options = dict(
            option.split("=", 1) if "=" in option else (option, "")
            for option in tmpfs_options.split(",")
        )
        expected_options = {"rw", "nosuid", "nodev", "size", "mode"}
        if noexec:
            expected_options.add("noexec")
        else:
            expected_options.add("exec")
        if set(options) != expected_options or any(
            options[name] for name in expected_options - {"size", "mode"}
        ):
            raise SandboxError(
                f"Opções do tmpfs em {destination} não correspondem à política."
            )
        size_match = re.fullmatch(r"(?i)([0-9]+)([kmgt]?)", options["size"])
        if not size_match:
            raise SandboxError("Tamanho do tmpfs inválido.")
        size = int(size_match.group(1)) * size_units[size_match.group(2).lower()]
        try:
            mode = int(options["mode"], 8)
        except ValueError as exc:
            raise SandboxError("Modo do tmpfs inválido.") from exc
        if size != expected_size or mode != 0o1777:
            raise SandboxError(f"Tamanho ou modo inválido em {destination}.")

    variables = config.get("Env", [])
    if not isinstance(variables, list):
        raise SandboxError("Ambiente do container inválido.")
    if any(
        variable.partition("=")[0] in _CREDENTIAL_ENV_VARS
        for variable in variables
        if isinstance(variable, str)
    ):
        raise SandboxError("Credencial de host foi encaminhada ao container.")
    environment = {
        variable.partition("=")[0]: variable.partition("=")[2]
        for variable in variables
        if isinstance(variable, str)
    }
    required_environment = {
        "HOME": "/tmp",
        "TMPDIR": "/var/tmp",
        "XDG_CACHE_HOME": "/var/tmp/.cache",
        "COPILOT_HOME": "/tmp/copilot-home",
        "COPILOT_AUTO_UPDATE": "false",
    }
    if any(environment.get(name) != value for name, value in required_environment.items()):
        raise SandboxError("Variáveis de ambiente do container não correspondem à política.")


class DockerSandbox:
    def __init__(self, extra_environment: Mapping[str, str] | None = None) -> None:
        self.image, self.platform = image_reference()
        self.binary = shutil.which("docker")
        self._docker_config: tempfile.TemporaryDirectory[str] | None = None
        self.environment: dict[str, str] = {}
        self._extra_environment = dict(extra_environment or {})

    def __enter__(self) -> "DockerSandbox":
        self._docker_config = tempfile.TemporaryDirectory(
            prefix="ch-factory001-docker-config-"
        )
        base_environment = {
            name: os.environ[name]
            for name in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "DOCKER_HOST")
            if name in os.environ
        }
        base_environment.update(self._extra_environment)
        try:
            self.environment = _docker_environment(
                base_environment, self._docker_config.name
            )
        except SandboxError:
            self._docker_config.cleanup()
            self._docker_config = None
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._docker_config is not None:
            self._docker_config.cleanup()

    def _docker(
        self, arguments: Sequence[str], timeout: float = 10
    ) -> subprocess.CompletedProcess[str]:
        if not self.binary:
            raise SandboxError("Docker CLI ausente; execução bloqueada sem fallback no host.")
        if self._docker_config is None:
            raise SandboxError("DockerSandbox deve ser usado dentro de um context manager.")
        try:
            return subprocess.run(
                [self.binary, *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.environment,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError("Comando Docker excedeu o timeout.") from exc
        except OSError as exc:
            raise SandboxError("Não foi possível iniciar o cliente Docker.") from exc

    def preflight(self, require_image: bool = True) -> DockerCapabilities:
        if not self.binary:
            raise SandboxError("Docker CLI ausente; execução bloqueada sem fallback no host.")

        server = self._docker(("version", "--format", "{{.Server.Version}}"))
        if server.returncode != 0 or not server.stdout.strip():
            raise SandboxError("Daemon Docker inacessível; execução bloqueada.")

        os_type = self._docker(("info", "--format", "{{.OSType}}"))
        if os_type.returncode != 0 or os_type.stdout.strip() != "linux":
            raise SandboxError("Docker Linux indisponível; execução bloqueada.")

        security = self._docker(("info", "--format", "{{json .SecurityOptions}}"))
        if security.returncode != 0:
            raise SandboxError("Não foi possível verificar as opções de segurança do Docker.")
        try:
            security_options = json.loads(security.stdout)
        except json.JSONDecodeError as exc:
            raise SandboxError("Docker retornou SecurityOptions inválido.") from exc
        if not isinstance(security_options, list):
            raise SandboxError("Docker retornou SecurityOptions inválido.")
        seccomp = any("seccomp" in str(option).lower() for option in security_options)
        if not seccomp:
            raise SandboxError("Seccomp padrão indisponível; execução bloqueada.")
        rootless = any("rootless" in str(option).lower() for option in security_options)

        image_id = self._docker(
            ("image", "inspect", self.image, "--format", "{{.Id}}")
        )
        if require_image and (image_id.returncode != 0 or not image_id.stdout.strip()):
            raise SandboxError(
                "Imagem oficial pinada não está local. Execute o subcomando pull."
            )

        compose = self._docker(("compose", "version", "--short"), timeout=5)
        compose_version = (
            compose.stdout.strip() if compose.returncode == 0 else None
        )
        return DockerCapabilities(
            server_version=server.stdout.strip(),
            rootless=rootless,
            seccomp=seccomp,
            compose_version=compose_version,
            image=self.image,
        )

    def pull(self) -> None:
        self.preflight(require_image=False)
        result = self._docker(("pull", "--platform", self.platform, self.image), timeout=180)
        if result.returncode != 0:
            raise SandboxError("Não foi possível obter a imagem pública pinada.")

    def _create(
        self,
        workspace: Path,
        command: Sequence[str],
        entrypoint: str,
    ) -> str:
        name = f"factory001-{uuid4().hex}"
        arguments = (
            "create",
            "--name",
            name,
            "--init",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            f"--pids-limit={PID_LIMIT}",
            f"--memory={MEMORY_BYTES}",
            f"--cpus={CPU_LIMIT}",
            f"--user={CONTAINER_USER}",
            "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777",
            "--tmpfs=/var/tmp:rw,exec,nosuid,nodev,size=1g,mode=1777",
            "--mount",
            f"type=bind,src={workspace},dst={WORKSPACE_TARGET},readonly",
            f"--workdir={WORKSPACE_TARGET}",
            "--env=HOME=/tmp",
            "--env=TMPDIR=/var/tmp",
            "--env=XDG_CACHE_HOME=/var/tmp/.cache",
            "--env=COPILOT_HOME=/tmp/copilot-home",
            "--env=COPILOT_AUTO_UPDATE=false",
            f"--entrypoint={entrypoint}",
            self.image,
            *command,
        )
        try:
            created = self._docker(arguments)
        except SandboxError:
            self._remove_by_name(name)
            raise
        container_id = created.stdout.strip()
        if created.returncode != 0 or not _CONTAINER_ID.fullmatch(container_id):
            self._remove_by_name(name)
            raise SandboxError("Docker não criou um container válido.")
        return container_id

    def _inspect(self, container_id: str) -> dict[str, object]:
        inspected = self._docker(("inspect", container_id))
        if inspected.returncode != 0:
            raise SandboxError("Não foi possível inspecionar o container.")
        try:
            data = json.loads(inspected.stdout)
        except json.JSONDecodeError as exc:
            raise SandboxError("Docker inspect retornou JSON inválido.") from exc
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise SandboxError("Docker inspect retornou resultado ambíguo.")
        return data[0]

    def _stop(self, container_id: str) -> None:
        stopped = self._docker(("stop", "--time=1", container_id), timeout=5)
        if stopped.returncode == 0:
            return
        state = self._docker(
            ("inspect", "--format", "{{.State.Running}}", container_id)
        )
        if state.returncode != 0:
            raise SandboxError("Não foi possível confirmar o estado do container.")
        if state.stdout.strip() == "true":
            killed = self._docker(("kill", container_id), timeout=5)
            if killed.returncode != 0:
                raise SandboxError("Container não parou após stop; kill também falhou.")

    def _remove(self, container_id: str) -> bool:
        removed = self._docker(("rm", "--force", container_id), timeout=10)
        if removed.returncode != 0:
            raise SandboxError("Não foi possível remover o container.")
        remaining = self._docker(
            ("ps", "--all", "--quiet", "--filter", f"id={container_id}")
        )
        if remaining.returncode != 0 or remaining.stdout.strip():
            raise SandboxError("Container residual detectado após cleanup.")
        return True

    def _remove_by_name(self, name: str) -> None:
        removed = self._docker(("rm", "--force", name), timeout=10)
        remaining = self._docker(
            ("ps", "--all", "--quiet", "--filter", f"name=/{name}")
        )
        if remaining.returncode != 0 or remaining.stdout.strip():
            raise SandboxError("Não foi possível confirmar cleanup após criação incompleta.")

    def execute(
        self,
        command: Sequence[str],
        workspace: Path,
        *,
        timeout: float,
        entrypoint: str = "/usr/local/bin/copilot",
        cancel_event: threading.Event | None = None,
    ) -> ContainerResult:
        if not command or timeout <= 0 or timeout > MAX_COMMAND_SECONDS:
            raise SandboxError("Comando ou timeout fora dos limites permitidos.")
        if entrypoint not in ("/usr/local/bin/copilot", "/bin/sh"):
            raise SandboxError("Entrypoint fora da allowlist da prova.")
        path = _workspace_path(workspace)
        container_id = self._create(path, command, entrypoint)
        process: subprocess.Popen[str] | None = None
        stdout = ""
        stderr = ""
        timed_out = False
        cancelled = False
        try:
            details = self._inspect(container_id)
            _validate_container(details, self.image, path)
            if cancel_event and cancel_event.is_set():
                cancelled = True
                self._stop(container_id)
            else:
                if not self.binary:
                    raise SandboxError("Docker CLI ausente; execução bloqueada.")
                process = subprocess.Popen(
                    [self.binary, "start", "--attach", container_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self.environment,
                )
                deadline = time.monotonic() + timeout
                while True:
                    if cancel_event and cancel_event.is_set():
                        cancelled = True
                        self._stop(container_id)
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        self._stop(container_id)
                        break
                    try:
                        stdout, stderr = process.communicate(
                            timeout=min(0.1, remaining)
                        )
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if process.poll() is None:
                    try:
                        stdout, stderr = process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                if stdout is None:
                    stdout = ""
                if stderr is None:
                    stderr = ""
        finally:
            if process is not None and process.poll() is None:
                self._stop(container_id)
                process.kill()
                process.communicate()
            removed = self._remove(container_id)

        return ContainerResult(
            container_id=container_id,
            returncode=process.returncode if process is not None else -1,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
            removed=removed,
        )


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise SandboxError(detail)


def _security_probe_script() -> str:
    return """\
set -eu
test "$(id -u)" = "10001"
test -x /usr/bin/timeout
test -x /usr/bin/openssl
grep -Eq '^Seccomp:[[:space:]]*2$' /proc/self/status
grep -Eq '^NoNewPrivs:[[:space:]]*1$' /proc/self/status
grep -Eq '^CapEff:[[:space:]]*0+$' /proc/self/status
test "$(cat /sys/fs/cgroup/memory.max)" = "2147483648"
test "$(cat /sys/fs/cgroup/pids.max)" = "64"
test "$(cat /sys/fs/cgroup/cpu.max)" = "100000 100000"
test ! -e "$1"
test ! -S /var/run/docker.sock
test ! -S /run/docker.sock
test -z "${COPILOT_GITHUB_TOKEN+x}"
test -z "${GH_TOKEN+x}"
test -z "${GITHUB_TOKEN+x}"
if /bin/sh -c ': > /home/copilot/.factory001-write-test' 2>/dev/null; then
  exit 31
fi
if /usr/bin/timeout 3 /usr/bin/openssl s_client -connect 1.1.1.1:443 -brief </dev/null >/dev/null 2>&1; then
  exit 32
fi
printf '%s\\n' FACTORY001_NEGATIVE_CONTROLS_PASS
"""


def run_acceptance(sandbox: DockerSandbox) -> dict[str, object]:
    capabilities = sandbox.preflight()
    with tempfile.TemporaryDirectory(prefix="ch-factory001-proof-") as root:
        root_path = Path(root)
        workspace = root_path / "workspace"
        outside = root_path / "host-canary"
        workspace.mkdir(mode=0o700)
        outside.write_text("factory-001-host-only-canary", encoding="utf-8")

        version = sandbox.execute(("--version",), workspace, timeout=15)
        version_output = version.stdout + version.stderr
        _require(
            version.returncode == 0 and CLI_VERSION in version_output,
            "Copilot CLI --version falhou ou a versão divergiu "
            f"(exit={version.returncode}, output={version_output.strip()[:400]!r}).",
        )
        help_result = sandbox.execute(("--help",), workspace, timeout=15)
        help_output = help_result.stdout + help_result.stderr
        _require(
            help_result.returncode == 0
            and ("Usage" in help_output or "usage" in help_output),
            "Copilot CLI --help falhou dentro do container "
            f"(exit={help_result.returncode}, output={help_output.strip()[:800]!r}).",
        )

        probe = sandbox.execute(
            ("-c", _security_probe_script(), "--", str(outside)),
            workspace,
            timeout=10,
            entrypoint="/bin/sh",
        )
        _require(
            probe.returncode == 0
            and "FACTORY001_NEGATIVE_CONTROLS_PASS" in probe.stdout,
            "Um teste negativo de isolamento falhou "
            f"(exit={probe.returncode}, stdout={probe.stdout.strip()[:500]!r}, "
            f"stderr={probe.stderr.strip()[:800]!r}).",
        )

        timed_out = sandbox.execute(
            ("-c", "exec sleep 30"),
            workspace,
            timeout=0.5,
            entrypoint="/bin/sh",
        )
        _require(
            timed_out.timed_out and timed_out.removed,
            "Timeout não removeu o container.",
        )

        cancel_event = threading.Event()
        timer = threading.Timer(0.5, cancel_event.set)
        timer.start()
        try:
            cancelled = sandbox.execute(
                ("-c", "exec sleep 30"),
                workspace,
                timeout=10,
                entrypoint="/bin/sh",
                cancel_event=cancel_event,
            )
        finally:
            timer.cancel()
            timer.join()
        _require(
            cancelled.cancelled and cancelled.removed,
            "Cancelamento não removeu o container.",
        )

    _require(
        not any(name in sandbox.environment for name in _CREDENTIAL_ENV_VARS),
        "Variável de credencial fictícia alcançou o cliente Docker.",
    )
    return {
        "status": "PASS",
        "cli_version": CLI_VERSION,
        "image": capabilities.image,
        "docker_server": capabilities.server_version,
        "docker_compose": capabilities.compose_version or "indisponível (não requerido)",
        "rootless": capabilities.rootless,
        "seccomp_default": capabilities.seccomp,
        "credentials_used": False,
        "model_calls": 0,
        "negative_controls": [
            "non-root",
            "seccomp",
            "no-new-privileges",
            "cap-drop-all",
            "read-only-rootfs",
            "host-file-unavailable",
            "no-host-credentials",
            "no-docker-socket",
            "network-none",
        ],
        "timeout_container_removed": timed_out.removed,
        "cancelled_container_removed": cancelled.removed,
    }


def _fake_credentials() -> dict[str, str]:
    fake = "FACTORY001-FAKE-CREDENTIAL-NOT-VALID"
    return {name: fake for name in _CREDENTIAL_ENV_VARS}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pull", "verify"))
    args = parser.parse_args(argv)

    try:
        if args.action == "pull":
            with DockerSandbox() as sandbox:
                sandbox.pull()
                print(f"IMAGE_PINNED={sandbox.image}")
            return 0

        with DockerSandbox(extra_environment=_fake_credentials()) as sandbox:
            evidence = run_acceptance(sandbox)
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0
    except SandboxError as exc:
        print(f"BLOQUEADO: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
