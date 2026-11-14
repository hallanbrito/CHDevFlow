"""CH-PIPE-01/F4: exame de custo e plano de sandbox para testes SEM agentes.

Nenhuma consulta a contas ou modelos; nenhuma chamada a Docker/Podman.
Um plano de container para fixtures não prova isolamento de SO nem aprova RUN.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
from typing import Any, Mapping

from chdevflow.core.manual_pipeline_runner import Mission, PipelinePlan

IMAGE = re.compile(r"^[a-z0-9][a-z0-9./_-]{0,140}@sha256:[0-9a-f]{64}$")
LAB_SCHEMA = "chdevflow.fake-lab/v1"
LAB_FILES = frozenset({
    ".chdevflow-fake-lab.json", "tests/test_fake_agent.py", "README.md",
})
FAKE_TEST = ("python", "-B", "-m", "unittest", "discover",
             "-s", "tests", "-p", "test_fake_agent.py", "-v")


@dataclass(frozen=True)
class CostAssessment:
    status: str
    codex: str
    agy: str
    reasons: tuple[str, ...]
    can_spend_brl: int = 0
    independently_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def assess_cost(
    *, env: Mapping[str, str] | None = None,
    claimed_evidence: Mapping[str, Any] | None = None,
) -> CostAssessment:
    """A assinatura ou o relatório local NÃO comprovam custo de uma conta.

    Futura integração deve consultar e autenticar direitos e limites ao vivo
    nos provedores. Não existe caminho para retornar PASS nesta F4.
    """
    env = os.environ if env is None else env
    reasons = [
        "Codex: autenticação ChatGPT, franquia e cobrança extra não verificadas pela conta",
        "AGY: modalidade individual, cotas/créditos e cobrança extra não verificados pela conta",
        "Prova independente autenticada do provedor ainda não implementada",
    ]
    if any(env.get(key) for key in (
        "OPENAI_API_KEY", "CODEX_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
    )):
        reasons.append(
            "Variáveis de chave API detectadas (nomes apenas); risco de cobrança por uso"
        )
    if claimed_evidence:
        reasons.append(
            "Comprovante fornecido localmente é não autenticado e não libera gasto"
        )
    return CostAssessment(
        status="BLOQUEADO_CUSTO",
        codex="NAO_VERIFICADO",
        agy="NAO_VERIFICADO",
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class FakeSandboxPlan:
    status: str
    reason: str
    runtime: str | None
    command: tuple[str, ...]
    network: str = "none"
    real_agents_allowed: bool = False
    isolation_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["command"] = list(self.command)
        return result


def _reparse(path: Path) -> bool:
    """Recusa symlink/junction/reparse point conhecido (Windows/POSIX)."""
    try:
        stat = path.lstat()
        flags = getattr(stat, "st_file_attributes", 0)
        return path.is_symlink() or bool(flags & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        return True


def _validate_fake_lab(root: Path) -> str | None:
    try:
        if not root.is_absolute() or not root.is_dir():
            return "Diretório absoluto de laboratório obrigatório"
        current = root
        while True:
            if _reparse(current):
                return "Junction/symlink/reparse point na cadeia de diretórios"
            if current == current.parent:
                break
            current = current.parent
        paths = list(root.rglob("*"))
        if len(paths) > 8:
            return "Laboratório com arquivos demais"
        file_names = set()
        for item in paths:
            if _reparse(item):
                return "Symlink/junction dentro do laboratório"
            if item.is_file():
                rel = item.relative_to(root).as_posix()
                file_names.add(rel)
                if rel not in LAB_FILES:
                    return "Arquivo fora da allowlist de fixtures"
                if item.stat().st_size > 16_384:
                    return "Fixture excede limite de 16KiB"
            elif item.is_dir():
                if item.relative_to(root).as_posix() != "tests":
                    return "Diretório extra proibido no laboratório"
            else:
                return "Objeto especial no laboratório"
        if not {".chdevflow-fake-lab.json", "tests/test_fake_agent.py"} <= file_names:
            return "Marcador ou teste fake ausente"
        marker = root / ".chdevflow-fake-lab.json"
        data = json.loads(marker.read_text(encoding="utf-8-sig"))
        if data != {"schema": LAB_SCHEMA, "kind": "fake-only"}:
            return "Marcador fake-lab inválido"
    except (OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError):
        return "Diretório/arquivos do laboratório não verificáveis"
    return None


def plan_fake_sandbox(
    lab_dir: Path, *, runtime: str, image: str,
    which: Any = None,
) -> FakeSandboxPlan:
    """Gera argv de Docker/Podman, mas NÃO o executa.

    Imagem precisa ser pinada por digest e estar já no host. A geração de
    comandos não confirma segurança do daemon/rootless ou autenticidade da
    imagem. Rede desativada: não serve para chamadas de modelos reais.
    """
    blocked = lambda reason: FakeSandboxPlan("BLOQUEADO_ISOLAMENTO", reason, None, ())
    if runtime not in ("docker", "podman"):
        return blocked("Runtime deve ser docker ou podman")
    if type(image) is not str or IMAGE.fullmatch(image) is None:
        return blocked("Imagem precisa de referência sha256 fixa")
    error = _validate_fake_lab(lab_dir)
    if error:
        return blocked(error)
    lookup = shutil.which if which is None else which
    if lookup(runtime) is None:
        return blocked("CLI do runtime não localizada; daemon não verificado")
    source_path = str(lab_dir.resolve())
    # Docker --mount interpreta vírgulas como separadores de opções.
    if any(c in source_path for c in (",", "\r", "\n", "\x00")):
        return blocked("Caminho do bind mount contém metacaracteres inseguros")
    args = (
        runtime, "run", "--rm", "--pull=never",
        "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
        "--pids-limit=32", "--memory=256m", "--cpus=1",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=32m",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--mount", f"type=bind,src={source_path},dst=/workspace,readonly",
        "--workdir=/workspace",
        "--entrypoint=python",
        image, *FAKE_TEST[1:],
    )
    return FakeSandboxPlan(
        status="PLANO_FAKE_APENAS",
        reason="Argv não executado; daemon, imagem e isolamento real não atestados",
        runtime=runtime,
        command=args,
    )


@dataclass(frozen=True)
class PilotReadiness:
    status: str
    mission_digest: str
    cost: CostAssessment
    plan_status: str
    host_os: str
    runtime_detected: tuple[str, ...]
    required_next: tuple[str, ...]
    can_execute_agents: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["runtime_detected"] = list(self.runtime_detected)
        data["required_next"] = list(self.required_next)
        data["cost"] = self.cost.to_dict()
        return data


def inspect_readiness(
    mission: Mission, plan: PipelinePlan, *,
    env: Mapping[str, str] | None = None,
    which: Any = None,
    os_name: str | None = None,
) -> PilotReadiness:
    """Readiness offline; NÃO autentica assinaturas, executa agentes ou containers."""
    lookup = shutil.which if which is None else which
    found = tuple(rt for rt in ("docker", "podman") if lookup(rt) is not None)
    cost = assess_cost(env=env)
    next_steps = (
        "Verificar live a autenticação e cota Codex (ChatGPT, não API key)",
        "Verificar live a conta AGY/Antigravity, limites e cobrança",
        "Executar teste fake em container isolado, sem rede nem credenciais",
        "Auditar engine/rootless, imagem pinada, mounts, processo e cancelamento",
        "Revalidar autorização PO específica e nonce na hora do piloto real",
    )
    status = "BLOQUEADO" if plan.state != "PLANEJADO_AGUARDANDO_GATE" else cost.status
    return PilotReadiness(status, mission.digest, cost, plan.state,
                          os_name or platform.system(), found, next_steps)
