"""Criação e inicialização de novos projetos governados pelo CHDevFlow."""
from __future__ import annotations

from pathlib import Path

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
    Gera manifesto chdevflow.yaml, fundação documental C.H. e árvore inicial.
    Falha fechado se o diretório já existir e não estiver vazio.
    """
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("O nome do projeto não pode ser vazio.")

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

    # 2. Manifesto chdevflow.yaml
    manifest_data = create_manifest_data(
        project_name=clean_name,
        backend=b_val,
        frontend=f_val,
        database=d_val,
    )
    manifest_path = target / "chdevflow.yaml"
    save_manifest(manifest_path, manifest_data)

    # 3. Árvore do projeto
    generate_tree(target)

    return target
