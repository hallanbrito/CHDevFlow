"""Instalação da fundação documental do Método C.H."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
from typing import TextIO


def get_templates_dir() -> Path:
    """Localiza o diretório de templates com base no ambiente ou instalação."""
    env_dir = os.environ.get("CHDEVFLOW_TEMPLATES_DIR")
    if env_dir:
        p = Path(env_dir).resolve()
        if p.is_dir():
            return p

    # 1. Dentro do próprio pacote (caso empacotado)
    pkg_templates = Path(__file__).resolve().parent.parent / "templates"
    if pkg_templates.is_dir():
        return pkg_templates

    # 2. Na raiz do repositório CHDevFlow (modo de desenvolvimento / editable)
    repo_templates = Path(__file__).resolve().parents[3] / "templates"
    if repo_templates.is_dir():
        return repo_templates

    # 3. Diretório templates no diretório atual de execução
    cwd_templates = Path.cwd() / "templates"
    if cwd_templates.is_dir():
        return cwd_templates

    raise FileNotFoundError(
        "Diretório templates não encontrado. Defina CHDEVFLOW_TEMPLATES_DIR ou instale o pacote com templates."
    )


def run_init(
    destination: Path,
    profile: str = "generic",
    apply: bool = False,
    templates_dir: Path | None = None,
    out: TextIO | None = None,
) -> tuple[int, int]:
    """
    Instala a fundação C.H. no destino indicado.
    Não sobrescreve arquivos existentes.
    Retorna a tupla (arquivos_criados, arquivos_preservados).
    """
    if out is None:
        out = sys.stdout

    dest_resolved = destination.resolve()
    if not dest_resolved.is_dir():
        raise FileNotFoundError(
            f"Diretório não encontrado: {dest_resolved}. Crie o diretório primeiro."
        )

    templates = templates_dir if templates_dir is not None else get_templates_dir()
    if not templates.is_dir():
        raise FileNotFoundError(
            f"Diretório templates não encontrado: {templates}"
        )

    created = 0
    skipped = 0

    for src in sorted(templates.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(templates)
        if rel.as_posix() == "docs/CH/PILOTO_HALLANCRAFT.md" and profile != "hallancraft":
            continue
        dest = dest_resolved / rel
        if dest.exists():
            skipped += 1
            print(f"PRESERVAR {rel}", file=out)
        else:
            created += 1
            print(f"{'CRIAR' if apply else 'CRIARIA'} {rel}", file=out)
            if apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with src.open("rb") as source, dest.open("xb") as target:
                    shutil.copyfileobj(source, target)

    status_str = "aplicado" if apply else "simulado"
    print(f"\nResultado: {status_str}; {created} novos, {skipped} preservados.", file=out)
    if apply:
        print(f"Próximo passo: ch tree --path {dest_resolved}", file=out)

    return created, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Instala fundação C.H. só para caminhos ausentes; modo padrão = dry-run.")
    ap.add_argument("--path", type=Path, default=Path.cwd(), help="Diretório do projeto (padrão: atual)")
    ap.add_argument("--profile", choices=["generic", "hallancraft"], default="generic", help="Perfil do projeto")
    ap.add_argument("--apply", action="store_true", help="Efetua criação (padrão apenas prévia)")
    args = ap.parse_args(argv)

    try:
        run_init(destination=args.path, profile=args.profile, apply=args.apply)
        return 0
    except Exception as exc:
        print(f"Erro em ch init: {exc}", file=sys.stderr)
        return 1
