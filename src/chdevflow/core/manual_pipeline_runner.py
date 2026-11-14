"""CH-PIPE-01/F2: planejamento e contrato para agentes CLI, DESATIVADOS.

O código oferece um pipeline inerte de planejamento, um executor de fixtures
e um adapter de subprocessos reais que NUNCA é conectado à CLI nesta fatia.
O gate de execução real por missão está pendente na Issue #69.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from threading import Lock
from typing import Any

SCHEMA = "chdevflow.pipeline.manual/v1"
MAX_TIMEOUT = 900
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_SECRET = re.compile(
    r"(?i)(?:gh[opsur]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}"
    r"|sk-[A-Za-z0-9_-]{18,}|(?:(?:api[_-]?key|token|password)\s*[:=]\s*)[^\s]+)"
)
_AGENTS = ("agy", "codex")
_RUNTIME_GATE_NOT_ISSUED = object()  # #69: nenhum construtor público em F2


@dataclass(frozen=True)
class Mission:
    schema: str
    mission_id: str
    repository: str
    issue: int
    base_sha: str
    worktree: str
    allowed_paths: tuple[str, ...]
    prompt_ref: str
    timeout_seconds: int = MAX_TIMEOUT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mission":
        if not isinstance(data, dict) or set(data) != {
            "schema", "mission_id", "repository", "issue", "base_sha",
            "worktree", "allowed_paths", "prompt_ref", "timeout_seconds",
        }:
            raise ValueError("Contrato de missão inválido ou campos faltantes")
        if not isinstance(data["allowed_paths"], list):
            raise ValueError("allowed_paths deve ser uma lista")
        return cls(
            data["schema"], data["mission_id"], data["repository"],
            data["issue"], data["base_sha"], data["worktree"],
            tuple(data["allowed_paths"]), data["prompt_ref"],
            data["timeout_seconds"],
        )

    def canonical(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical()).hexdigest()


@dataclass(frozen=True)
class PipelinePlan:
    state: str
    reason: str
    mission_id: str
    mission_digest: str
    stages: tuple[str, ...]
    may_execute_agents: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["stages"] = list(self.stages)
        return result


@dataclass(frozen=True)
class ProcessResult:
    agent: str
    status: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed_s: float


class ProcessAdapter:
    """Adaptador de processos reais; não é registrado pelo comando ch."""

    @staticmethod
    def command(agent: str) -> tuple[str, ...]:
        if agent == "agy":
            return ("agy", "--print", "--mode", "accept-edits")
        if agent == "codex":
            return ("codex", "exec", "--sandbox", "read-only",
                    "--skip-git-repo-check", "-")
        raise ValueError("Executor desconhecido")

    @staticmethod
    def sanitize(value: str) -> str:
        return _SECRET.sub("[REDACTED]", value)[:100_000]

    def _invoke_inactive(self, agent: str, prompt: str, cwd: Path,
                         timeout_seconds: int, *, execution_gate: object | None = None) -> ProcessResult:
        """Implementação interna NÃO conectada a nenhum comando público.

        Só pode ser ativada por futura revisão de gates GitHub+custo em #69.
        Não representa uma sandbox de segurança nem permite execução hoje.
        """
        # Sem provedor de gate externo em F2, este método deve permanecer
        # inacessível ao produto: invocar diretamente sem gate não executa.
        if execution_gate is not _RUNTIME_GATE_NOT_ISSUED:
            raise PermissionError("BLOQUEADO_ATIVACAO: gate GH/custo não implementado")
        if agent not in _AGENTS or not cwd.is_dir() or cwd.is_symlink():
            raise ValueError("Agente ou worktree inválida")
        if type(timeout_seconds) is not int or not 0 < timeout_seconds <= MAX_TIMEOUT:
            raise ValueError("Timeout inválido")
        # Detalhes de execução só são alcançáveis por código que explicitamente
        # chamar este método interno. Nenhum CLI ou teste invoca este método.
        import time
        began = time.monotonic()
        try:
            proc = subprocess.run(
                self.command(agent), cwd=cwd, input=prompt, text=True,
                encoding="utf-8", errors="replace", capture_output=True,
                timeout=timeout_seconds, check=False,
            )
            out = self.sanitize(proc.stdout or "")
            err = self.sanitize(proc.stderr or "")
            denied = bool(re.search(r"(?i)permission denied|access denied|not authorized", out+"\n"+err))
            status = "SUCESSO" if proc.returncode == 0 and not denied and not err.strip() and out.strip() else "BLOQUEADO"
            return ProcessResult(agent, status, proc.returncode, out, err,
                                 time.monotonic()-began)
        except subprocess.TimeoutExpired:
            return ProcessResult(agent, "TIMEOUT", -1, "", "Timeout interrompeu processo", time.monotonic()-began)
        except (OSError, UnicodeError):
            return ProcessResult(agent, "BLOQUEADO", -1, "", "Falha ao iniciar CLI", time.monotonic()-began)


def _safe_relative(path: str, root: Path) -> bool:
    if not isinstance(path, str) or not path or len(path) > 200 or "\\" in path:
        return False
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts or any(c in path for c in "*?[]"):
        return False
    # não permite usar caminhos onde symlink/reparse point já existe
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    return current.resolve().is_relative_to(root.resolve())


def plan_manual_mission(mission: Mission, *, observed_sha: str | None = None) -> PipelinePlan:
    """Planejamento fail-closed. Não acessa rede, não executa agentes."""
    stages = ("PREFLIGHT", "AGY", "TESTES", "CODEX", "DOSSIER", "CH1")
    reason = ""
    if mission.schema != SCHEMA:
        reason = "Schema desconhecido"
    elif not isinstance(mission.mission_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", mission.mission_id):
        reason = "ID de missão inválido"
    elif not isinstance(mission.repository, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", mission.repository):
        reason = "Repositório inválido"
    elif type(mission.issue) is not int or mission.issue < 1:
        reason = "Issue inválida"
    elif not isinstance(mission.base_sha, str) or not _SHA.fullmatch(mission.base_sha):
        reason = "Baseline inválido"
    elif type(mission.timeout_seconds) is not int or not 0 < mission.timeout_seconds <= MAX_TIMEOUT:
        reason = "Timeout excede política D06"
    elif not isinstance(mission.worktree, str) or not Path(mission.worktree).is_absolute():
        reason = "Worktree absoluta obrigatória"
    elif (not isinstance(mission.prompt_ref, str) or
          not re.fullmatch(r"[A-Za-z0-9_.\-/]{3,200}", mission.prompt_ref)):
        reason = "Referência de prompt inválida"
    elif not mission.allowed_paths or len(mission.allowed_paths) > 20:
        reason = "Escopo ausente ou amplo demais"
    else:
        root = Path(mission.worktree)
        if not root.is_dir() or root.is_symlink():
            reason = "Worktree ausente ou symlink"
        elif not all(_safe_relative(p, root) for p in mission.allowed_paths):
            reason = "Caminho fora do escopo ou simbólico"
        elif not _safe_relative(mission.prompt_ref, root):
            reason = "Prompt fora da worktree"
        elif not (root / mission.prompt_ref).is_file():
            reason = "Prompt da missão ausente"
        elif observed_sha is None:
            reason = "Baseline live Git não verificado"
        elif observed_sha.lower() != mission.base_sha.lower():
            reason = "Baseline SHA divergente"
        else:
            # O comando plan verifica o contrato; não autentica aprovação PO
            # nem confirma custo adicional R$0.
            reason = "Elegibilidade documental apenas; aprovação PO/custo/lock não verificados"
    return PipelinePlan("BLOQUEADO" if reason !=
                        "Elegibilidade documental apenas; aprovação PO/custo/lock não verificados"
                        else "PLANEJADO_AGUARDANDO_GATE", reason, mission.mission_id,
                        mission.digest, stages)


class SimulatedPipeline:
    """Motor in-memory para provar sequência/erros sem subprocessos ou rede."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._busy = False
        self._done: dict[str, dict[str, Any]] = {}

    def run_fixture(self, mission: Mission, workers: dict[str, str],
                    *, tests_ok: bool) -> dict[str, Any]:
        """Consome respostas PRÉ-GRAVADAS; não aceita callbacks nem executores."""
        digest = mission.digest
        with self._lock:
            if digest in self._done:
                return dict(self._done[digest])
            if self._busy:
                return {"status": "BLOQUEADO_CONCORRENCIA", "digest": digest}
            self._busy = True
        stages: dict[str, str] = {}
        try:
            if set(workers) != {"agy", "codex"}:
                raise ValueError("Fakes de AGY e Codex obrigatórios")
            agy = workers["agy"]
            stages["agy"] = "PASS" if isinstance(agy, str) and agy.strip() else "BLOCKED"
            if stages["agy"] != "PASS":
                raise ValueError("AGY sem entrega")
            stages["testes"] = "PASS" if tests_ok is True else "BLOCKED"
            if stages["testes"] != "PASS":
                raise ValueError("Testes falharam")
            codex = workers["codex"]
            stages["codex"] = "PASS" if isinstance(codex, str) and codex.startswith("APROVAR_LAB") else "BLOCKED"
            if stages["codex"] != "PASS":
                raise ValueError("Codex vetou")
            result = {"status": "FIXTURE_CONCLUIDA_SEM_EXECUCAO", "digest": digest,
                      "stages": stages, "agent_processes": 0}
        except (ValueError, OSError, TypeError) as exc:
            result = {"status": "FIXTURE_BLOQUEADA", "digest": digest, "stages": stages,
                      "reason": str(exc), "agent_processes": 0}
        finally:
            with self._lock:
                self._busy = False
                self._done[digest] = result
        return dict(result)


def load_manifest(path: Path) -> Mission:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
        raise ValueError("Manifesto ausente, symlink ou grande demais")
    return Mission.from_dict(json.loads(path.read_text(encoding="utf-8-sig")))
