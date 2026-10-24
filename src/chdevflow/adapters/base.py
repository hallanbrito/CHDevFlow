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
    status: str  # OK, AUSENTE, INCOMPATIVEL, ERRO, TIMEOUT
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
    """
    Remove potenciais tokens, chaves e credenciais de textos (stdout, stderr e comandos).
    Mascarar: GitHub tokens, OpenAI/AI keys, AWS keys, senhas, tokens genéricos e connection strings.
    """
    if not text:
        return ""

    # 1. GitHub tokens
    sanitized = re.sub(r"\b(gho_|ghp_|ghu_|ghs_|ghr_|github_pat_)[a-zA-Z0-9_]+\b", "[REDACTED_TOKEN]", text)

    # 2. OpenAI / Anthropic / AI API keys
    sanitized = re.sub(r"\bsk-[a-zA-Z0-9_\-]{20,}\b", "[REDACTED_AI_KEY]", sanitized)
    sanitized = re.sub(r"\bsk-ant-[a-zA-Z0-9_\-]{20,}\b", "[REDACTED_AI_KEY]", sanitized)

    # 3. AWS keys
    sanitized = re.sub(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]", sanitized)
    sanitized = re.sub(
        r"(?i)(aws_secret_access_key|aws_secret_key)\s*[:=]\s*[A-Za-z0-9/+=]{40}",
        r"\1=[REDACTED_AWS_SECRET]",
        sanitized,
    )

    # 4. Connection strings (PostgreSQL, MySQL, MongoDB, etc.)
    sanitized = re.sub(
        r"(?i)\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://([^:\s]+):([^@\s]+)@([^\s/]+)",
        r"\1://\2:[REDACTED_PASSWORD]@\4",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(Password|pwd)\s*=\s*[^;]+;",
        r"\1=[REDACTED_PASSWORD];",
        sanitized,
    )

    # 5. Bearer tokens
    sanitized = re.sub(r"(?i)\b(bearer)\s+[a-zA-Z0-9_\-\.]+", r"\1 [REDACTED_BEARER]", sanitized)

    # 6. Atribuições genéricas de senhas, secrets e tokens (chave=valor / chave: valor)
    # Ignora valores que já foram mascarados por regras mais específicas (ex.: [REDACTED_...)
    sanitized = re.sub(
        r"(?i)\b(password|passwd|secret|api[_\-]?key|apikey|token|auth_token)\s*([:=])\s*(?!\[REDACTED_)(?:\"[^\"]+\"|'[^']+'|[^\s,;]+)",
        r"\1\2[REDACTED_SECRET]",
        sanitized,
    )

    # 7. Chaves privadas PEM
    sanitized = re.sub(
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        sanitized,
    )

    return sanitized


class BaseAdapter:
    """Classe base para adapters de tecnologias suportadas."""
    name: str = "base"
    display_name: str = "Base"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False, required_version: str | None = None) -> list[ToolDiagnostic]:
        """Executa diagnóstico de ferramentas da stack."""
        return []

    def get_default_verification_commands(self) -> list[str]:
        """Retorna comandos padrão de compilação/teste da stack."""
        return []
