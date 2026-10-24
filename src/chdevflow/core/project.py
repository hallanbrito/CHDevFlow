"""Criação e inicialização de novos projetos governados pelo CHDevFlow."""
from __future__ import annotations

from pathlib import Path
import re

from chdevflow.core.config import create_manifest_data, save_manifest
from chdevflow.core.init import run_init
from chdevflow.core.tree import generate as generate_tree

VALID_BACKENDS = {"dotnet", "python", "java", "none"}
VALID_FRONTENDS = {"angular", "react", "none"}
VALID_DATABASES = {"postgres", "postgresql", "none"}

PRESETS: dict[str, dict[str, str]] = {
    "dotnet-angular": {"backend": "dotnet", "frontend": "angular", "database": "postgres"},
    "python-react": {"backend": "python", "frontend": "react", "database": "postgres"},
    "fullstack-dotnet": {"backend": "dotnet", "frontend": "react", "database": "postgres"},
}

DEFAULT_GITIGNORE_CONTENT = """.ch/evidence/
__pycache__/
*.py[cod]
.venv/
"""


def validate_project_name(name: str) -> str:
    """Valida o nome do projeto contra injeções de path traversal, caminhos absolutos e caracteres inválidos."""
    clean = name.strip()
    if not clean:
        raise ValueError("O nome do projeto não pode ser vazio.")

    # Impede caminhos absolutos, navegação para diretório pai e separadores de path
    if Path(clean).is_absolute() or ".." in clean or "/" in clean or "\\" in clean:
        raise ValueError(
            f"Nome de projeto inválido: '{name}'. Não são permitidos caminhos absolutos, '..' ou separadores de diretório."
        )

    if not re.match(r"^[a-zA-Z0-9_\-]+$", clean):
        raise ValueError(
            f"Nome de projeto inválido: '{name}'. Utilize apenas caracteres alfanuméricos, hífen ou sublinhado."
        )

    return clean


def ensure_project_gitignore(project_dir: Path) -> None:
    """Garante que .gitignore exista e contenha a exclusão de .ch/evidence/."""
    gitignore_file = project_dir / ".gitignore"
    if not gitignore_file.exists():
        gitignore_file.write_text(DEFAULT_GITIGNORE_CONTENT, encoding="utf-8")
    else:
        content = gitignore_file.read_text(encoding="utf-8")
        if ".ch/evidence" not in content and ".ch/" not in content:
            new_content = content.rstrip() + "\n.ch/evidence/\n"
            gitignore_file.write_text(new_content, encoding="utf-8")


def create_project(
    name: str,
    base_dir: Path,
    backend: str = "none",
    frontend: str = "none",
    database: str = "none",
    preset: str | None = None,
    profile: str = "generic",
) -> Path:
    """
    Cria a estrutura de um novo projeto governado pelo CHDevFlow.
    Gera manifesto chdevflow.yaml, fundação documental C.H., .gitignore defensivo e árvore inicial.
    Falha fechado se o diretório já existir e não estiver vazio.
    """
    clean_name = validate_project_name(name)

    # Aplica preset se fornecido
    if preset:
        preset_clean = preset.strip().lower()
        if preset_clean in PRESETS:
            cfg = PRESETS[preset_clean]
            if backend == "none":
                backend = cfg["backend"]
            if frontend == "none":
                frontend = cfg["frontend"]
            if database == "none":
                database = cfg["database"]
        else:
            raise ValueError(
                f"Preset desconhecido: '{preset}'. Presets válidos: {', '.join(sorted(PRESETS.keys()))}"
            )

    b_val = backend.strip().lower()
    f_val = frontend.strip().lower()
    d_val = database.strip().lower()

    if b_val not in VALID_BACKENDS:
        raise ValueError(f"Backend inválido: '{backend}'. Opções: {', '.join(sorted(VALID_BACKENDS))}")
    if f_val not in VALID_FRONTENDS:
        raise ValueError(f"Frontend inválido: '{frontend}'. Opções: {', '.join(sorted(VALID_FRONTENDS))}")
    if d_val not in VALID_DATABASES:
        raise ValueError(f"Database inválido: '{database}'. Opções: {', '.join(sorted(VALID_DATABASES))}")

    target = (base_dir / clean_name).resolve()
    if target.exists():
        entries = list(target.iterdir())
        if entries:
            raise FileExistsError(
                f"Diretório já existe e não está vazio: {target}. Abortando para evitar sobrescrita acidental."
            )

    target.mkdir(parents=True, exist_ok=True)

    # 1. Fundação documental C.H.
    run_init(destination=target, profile=profile, apply=True)

    # 2. .gitignore com proteção de .ch/evidence/
    ensure_project_gitignore(target)

    # 3. Manifesto chdevflow.yaml
    manifest_data = create_manifest_data(
        project_name=clean_name,
        backend=b_val,
        frontend=f_val,
        database=d_val,
        project_dir=target,
    )
    manifest_path = target / "chdevflow.yaml"
    save_manifest(manifest_path, manifest_data)

    # 4. Árvore do projeto
    generate_tree(target)

    return target
