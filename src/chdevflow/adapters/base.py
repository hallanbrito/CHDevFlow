"""Interface base para adapters de tecnologia e diagnóstico de ferramentas."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable


@dataclass
class ToolDiagnostic:
    tool: str
    required: bool
    installed: bool
    version: str | None
    status: str  # OK, AUSENTE, ERRO, TIMEOUT
    details: str
    remediation: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def safe_run_command(
    cmd: list[str],
    timeout: float = 3.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Executa um comando local com timeout e captura segura de saída."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=run_env,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout expirado ao consultar ferramenta"
    except FileNotFoundError:
        return -2, "", "Executável não encontrado"
    except Exception as exc:
        return -3, "", str(exc)


def sanitize_output(text: str) -> str:
    """Remove potenciais tokens ou credenciais de saídas de texto."""
    sanitized = re.sub(r"(gho_|ghp_|github_pat_)[a-zA-Z0-9_]+", "[REDACTED_TOKEN]", text)
    sanitized = re.sub(r"(token:\s*)\S+", r"\1[REDACTED_TOKEN]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"(bearer\s+)[a-zA-Z0-9_\-\.]+", r"\1[REDACTED_BEARER]", sanitized, flags=re.IGNORECASE)
    return sanitized


class BaseAdapter:
    """Classe base para adapters de tecnologias suportadas."""
    name: str = "base"
    display_name: str = "Base"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        """Executa diagnóstico de ferramentas da stack."""
        return []

    def get_default_verification_commands(self) -> list[str]:
        """Retorna comandos padrão de compilação/teste da stack."""
        return []
