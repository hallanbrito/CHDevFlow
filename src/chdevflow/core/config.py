"""Manipulação e validação do manifesto chdevflow.yaml."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

FORBIDDEN_SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "auth",
    "authorization",
    "connection_string",
    "db_password",
    "bearer",
}

FORBIDDEN_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 1. sk-* e chaves de provedores de IA
    (re.compile(r"\bsk-[a-zA-Z0-9_\-]{16,}\b"), "Chave de provedor de IA (sk-*)"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{25,}\b"), "Chave de API Google (AIza...)"),
    # 2. AWS keys
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "Chave de acesso AWS (AKIA/ASIA)"),
    (re.compile(r"(?i)(aws_secret_access_key|aws_secret_key)\s*[:=]\s*[A-Za-z0-9/+=]{20,}"), "Secret key AWS"),
    # 3. API_KEY=valor, TOKEN=valor, PASSWORD=valor, PASSWD=valor, SECRET=valor
    (re.compile(r"(?i)\b(api_key|token|password|passwd|secret)\s*[:=]\s*['\"]?[^\s'\"]{3,}"), "Atribuição de segredo/token"),
    # 4. Connection strings com usuário/senha
    (re.compile(r"(?i)\b[a-zA-Z0-9\+\-]+://[^/\s:@]+:[^/\s:@]+@[^/\s]+"), "Connection string com credenciais"),
    (re.compile(r"(?i)(Password|pwd)\s*=\s*[^;]+;"), "Connection string com Password/pwd"),
    # 5. Bearer tokens e chaves privadas
    (re.compile(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{10,}"), "Bearer token"),
    (re.compile(r"(?i)begin\s+(?:rsa\s+|dsa\s+|ec\s+|openssh\s+)?private\s+key"), "Chave privada PEM/SSH"),
    (re.compile(r"\b(ssh-rsa|ssh-ed25519)\s+[A-Za-z0-9+/]{40,}"), "Chave SSH"),
    # 6. Tokens GitHub
    (re.compile(r"\b(gho_|ghp_|ghu_|ghs_|ghr_|github_pat_)[a-zA-Z0-9_]{10,}\b"), "Token do GitHub"),
]


class ManifestError(ValueError):
    """Erro em caso de manifesto inválido."""
    pass


class ManifestSecurityError(PermissionError):
    """Erro em caso de detecção de segredo ou credencial no manifesto."""
    pass


def _check_no_secrets(data: Any, path: str = "") -> None:
    """Verifica recursivamente se há chaves ou valores suspeitos de serem credenciais."""
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower()
            current_path = f"{path}.{k}" if path else str(k)
            for forbidden in FORBIDDEN_SECRET_KEYS:
                if forbidden in k_lower:
                    raise ManifestSecurityError(
                        f"Segredo ou credencial não permitida no manifesto: '{current_path}'"
                    )
            _check_no_secrets(v, current_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _check_no_secrets(item, f"{path}[{i}]")
    elif isinstance(data, str):
        for pattern, desc in FORBIDDEN_SECRET_PATTERNS:
            if pattern.search(data):
                raise ManifestSecurityError(
                    f"Valor suspeito de segredo ou credencial ({desc}) no manifesto em '{path}'"
                )


def parse_yaml_text(content: str) -> dict[str, Any]:
    """
    Analisa texto YAML seguro.
    Utiliza PyYAML se disponível; caso contrário, utiliza parser determinístico embutido.
    """
    try:
        import yaml
        loaded = yaml.safe_load(content)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ManifestError("Manifesto deve ser um mapeamento YAML/dicionário.")
        return loaded
    except ImportError:
        pass

    # Parser minimalista embutido em caso de ausência do pyyaml
    result: dict[str, Any] = {}
    lines = content.splitlines()
    stack: list[tuple[int, Any]] = [(-1, result)]

    for line_num, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        current_parent = stack[-1][1]

        if stripped.startswith("- "):
            item_val = stripped[2:].strip()
            # Remove aspas se houver
            if (item_val.startswith('"') and item_val.endswith('"')) or (item_val.startswith("'") and item_val.endswith("'")):
                item_val = item_val[1:-1]
            if isinstance(current_parent, list):
                current_parent.append(item_val)
            elif isinstance(current_parent, dict):
                raise ManifestError(f"Erro de sintaxe YAML na linha {line_num}: item de lista inesperado")
        elif ":" in stripped:
            key, sep, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            if not val:
                next_is_list = False
                for future in lines[line_num:]:
                    s_fut = future.strip()
                    if not s_fut or s_fut.startswith("#"):
                        continue
                    fut_indent = len(future) - len(future.lstrip(" "))
                    if fut_indent > indent and s_fut.startswith("- "):
                        next_is_list = True
                    break

                sub_container: Any = [] if next_is_list else {}
                if isinstance(current_parent, dict):
                    current_parent[key] = sub_container
                stack.append((indent, sub_container))
            else:
                parsed_val: Any = val
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    parsed_val = val[1:-1]
                elif val.lower() == "true":
                    parsed_val = True
                elif val.lower() == "false":
                    parsed_val = False
                elif val.isdigit():
                    parsed_val = int(val)

                if isinstance(current_parent, dict):
                    current_parent[key] = parsed_val

    return result


def dump_yaml_text(data: dict[str, Any]) -> str:
    """Serializa dicionário estruturado para YAML limpo."""
    try:
        import yaml
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    except ImportError:
        pass

    lines: list[str] = []

    def _format_scalar(val: Any) -> str:
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (int, float)):
            return str(val)
        s = str(val)
        if any(c in s for c in [":", " ", "#", "-", "[", "]", "{", "}"]) or not s:
            return f'"{s}"'
        return s

    def _dump_dict(d: dict[str, Any], indent_lvl: int = 0) -> None:
        ind = "  " * indent_lvl
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{ind}{k}:")
                _dump_dict(v, indent_lvl + 1)
            elif isinstance(v, list):
                lines.append(f"{ind}{k}:")
                for item in v:
                    lines.append(f"{ind}  - {_format_scalar(item)}")
            else:
                lines.append(f"{ind}{k}: {_format_scalar(v)}")

    _dump_dict(data)
    return "\n".join(lines) + "\n"


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Valida o schema v1 do manifesto. Retorna lista de erros se houver."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["Manifesto deve ser um dicionário/objeto."]

    _check_no_secrets(manifest)

    if "version" not in manifest or str(manifest.get("version")) != "1":
        errors.append("Campo 'version' obrigatório e deve ser '1'.")

    project = manifest.get("project")
    if not isinstance(project, dict) or not project.get("name"):
        errors.append("Campo 'project' deve conter 'name'.")

    governance = manifest.get("governance")
    if not isinstance(governance, dict):
        errors.append("Campo 'governance' é obrigatório.")
    elif governance.get("method") != "CH":
        errors.append("Campo 'governance.method' deve ser 'CH'.")

    if "stack" not in manifest or not isinstance(manifest["stack"], dict):
        errors.append("Campo 'stack' deve ser um mapeamento.")

    if "verification" not in manifest or not isinstance(manifest["verification"], dict):
        errors.append("Campo 'verification' deve ser um mapeamento.")
    elif not isinstance(manifest["verification"].get("commands", []), list):
        errors.append("Campo 'verification.commands' deve ser uma lista.")

    if "workflow" not in manifest or not isinstance(manifest["workflow"], dict):
        errors.append("Campo 'workflow' deve ser um mapeamento.")

    return errors


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Carrega e valida o manifesto em chdevflow.yaml."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifesto não encontrado em: {manifest_path}")

    content = manifest_path.read_text(encoding="utf-8")
    data = parse_yaml_text(content)
    errors = validate_manifest(data)
    if errors:
        raise ManifestError(f"Manifesto inválido ({manifest_path.name}): " + "; ".join(errors))
    return data


def save_manifest(manifest_path: Path, data: dict[str, Any]) -> None:
    """Valida e grava o manifesto em chdevflow.yaml."""
    errors = validate_manifest(data)
    if errors:
        raise ManifestError("Não é possível salvar manifesto inválido: " + "; ".join(errors))
    content = dump_yaml_text(data)
    manifest_path.write_text(content, encoding="utf-8")


def create_manifest_data(
    project_name: str,
    backend: str = "none",
    frontend: str = "none",
    database: str = "none",
    project_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Gera estrutura padrão do manifesto v1 com intenção de stack registrada.
    Para projetos que registram apenas intenção sem arquivos de build reais (ex.: package.json),
    configura um check local executável (ch status), impedindo falhas falsas em ch verify.
    """
    backend_val = backend.strip().lower()
    frontend_val = frontend.strip().lower()
    database_val = database.strip().lower()

    verification_commands: list[str] = []

    # Verifica se existem arquivos reais de build no diretório do projeto
    has_package_json = bool(project_dir and (project_dir / "package.json").is_file())
    has_dotnet_proj = bool(project_dir and (list(project_dir.glob("*.csproj")) or list(project_dir.glob("*.sln"))))
    has_maven_pom = bool(project_dir and (project_dir / "pom.xml").is_file())

    stack_data: dict[str, Any] = {}
    if backend_val != "none":
        stack_data["backend"] = {"type": backend_val}
        if backend_val == "dotnet":
            stack_data["backend"]["version"] = "10"
            if has_dotnet_proj:
                verification_commands.extend(["dotnet build", "dotnet test"])
        elif backend_val == "python":
            stack_data["backend"]["version"] = "3.12"
            if project_dir and (project_dir / "tests").is_dir():
                verification_commands.append("python -m unittest")
        elif backend_val == "java":
            stack_data["backend"]["version"] = "21"
            if has_maven_pom:
                verification_commands.append("mvn test")

    if frontend_val != "none":
        stack_data["frontend"] = {"type": frontend_val}
        if frontend_val == "angular":
            stack_data["frontend"]["version"] = "22"
            if has_package_json:
                verification_commands.append("npm test")
        elif frontend_val == "react":
            stack_data["frontend"]["version"] = "19"
            if has_package_json:
                verification_commands.append("npm test")

    if database_val != "none":
        stack_data["database"] = {
            "type": "postgresql" if database_val in ("postgres", "postgresql") else database_val
        }

    # Se não houver arquivos de build reais, define verificação local executável com status estrito da governança C.H.
    if not verification_commands:
        verification_commands = ["ch status --strict"]

    manifest = {
        "version": "1",
        "project": {
            "name": project_name,
            "type": "web" if (backend_val != "none" or frontend_val != "none") else "core",
        },
        "governance": {
            "method": "CH",
            "require_po_approval": True,
        },
        "stack": stack_data,
        "verification": {
            "commands": verification_commands,
        },
        "workflow": {
            "branch_prefix": "ch/",
            "draft_pr": True,
            "require_ruc": True,
        },
    }

    _check_no_secrets(manifest)
    return manifest
