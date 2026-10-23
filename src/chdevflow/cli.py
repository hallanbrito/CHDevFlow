"""Interface de linha de comando principal do CHDevFlow (`ch`)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from chdevflow import __version__
from chdevflow.core.init import run_init
from chdevflow.core.project import PRESETS, VALID_BACKENDS, VALID_DATABASES, VALID_FRONTENDS, create_project
from chdevflow.core.status import get_project_status, render_status_human
from chdevflow.core.tree import generate as generate_tree


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ch",
        description="CHDevFlow CLI — governança universal, execução especializada (Método C.H.)",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"chdevflow {__version__}",
        help="Exibe a versão instalada do CHDevFlow.",
    )

    subparsers = parser.add_subparsers(
        title="comandos",
        dest="command",
        metavar="<comando>",
    )

    # Subcomando: init
    parser_init = subparsers.add_parser(
        "init",
        help="Instala a fundação documental C.H. em um diretório de projeto.",
    )
    parser_init.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Caminho do diretório do projeto (padrão: diretório atual).",
    )
    parser_init.add_argument(
        "--profile",
        choices=["generic", "hallancraft"],
        default="generic",
        help="Perfil da fundação documental (padrão: generic).",
    )
    parser_init.add_argument(
        "--apply",
        action="store_true",
        help="Aplica as alterações no disco (o padrão é apenas simulação / dry-run).",
    )

    # Subcomando: new
    parser_new = subparsers.add_parser(
        "new",
        help="Cria um novo projeto governado pelo CHDevFlow com manifesto chdevflow.yaml.",
    )
    parser_new.add_argument(
        "name",
        type=str,
        help="Nome do projeto.",
    )
    parser_new.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório pai onde o projeto será criado (padrão: diretório atual).",
    )
    parser_new.add_argument(
        "--backend",
        choices=sorted(list(VALID_BACKENDS)),
        default="none",
        help="Tecnologia de backend.",
    )
    parser_new.add_argument(
        "--frontend",
        choices=sorted(list(VALID_FRONTENDS)),
        default="none",
        help="Tecnologia de frontend.",
    )
    parser_new.add_argument(
        "--database",
        choices=["postgres", "none"],
        default="none",
        help="Banco de dados planejado.",
    )
    parser_new.add_argument(
        "--preset",
        choices=sorted(list(PRESETS.keys())),
        default=None,
        help="Preset de combinação arquitetural (ex.: dotnet-angular).",
    )
    parser_new.add_argument(
        "--profile",
        choices=["generic", "hallancraft"],
        default="generic",
        help="Perfil da fundação documental.",
    )

    # Subcomando: status
    parser_status = subparsers.add_parser(
        "status",
        help="Verifica o estado local do projeto, Git, manifesto e governança C.H.",
    )
    parser_status.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_status.add_argument(
        "--json",
        action="store_true",
        help="Exporta o status em formato JSON estruturado.",
    )

    # Subcomando: tree
    parser_tree = subparsers.add_parser(
        "tree",
        help="Gera ou atualiza docs/ARVORE_PROJETO.md sem expor conteúdos ou segredos.",
    )
    parser_tree.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Caminho da raiz do projeto (padrão: diretório atual).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "init":
        try:
            run_init(destination=args.path, profile=args.profile, apply=args.apply)
            return 0
        except Exception as exc:
            print(f"Erro em 'ch init': {exc}", file=sys.stderr)
            return 1

    if args.command == "new":
        try:
            target = create_project(
                name=args.name,
                base_dir=args.path,
                backend=args.backend,
                frontend=args.frontend,
                database=args.database,
                preset=args.preset,
                profile=args.profile,
            )
            print(f"Projeto '{args.name}' criado com sucesso em: {target}")
            print("Próximos passos:")
            print(f"  cd {target.name}")
            print("  git init")
            print("  ch status")
            return 0
        except Exception as exc:
            print(f"Erro em 'ch new': {exc}", file=sys.stderr)
            return 1

    if args.command == "status":
        try:
            status_data = get_project_status(args.path)
            if args.json:
                print(json.dumps(status_data, indent=2, ensure_ascii=False))
            else:
                print(render_status_human(status_data))
            return 0
        except Exception as exc:
            print(f"Erro em 'ch status': {exc}", file=sys.stderr)
            return 1

    if args.command == "tree":
        try:
            dest, changed = generate_tree(args.path.resolve())
            print(f"{'Gerado' if changed else 'Sem alterações'}: {dest}")
            return 0
        except Exception as exc:
            print(f"Erro em 'ch tree': {exc}", file=sys.stderr)
            return 1

    print(f"Comando desconhecido: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
