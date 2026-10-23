"""Interface de linha de comando principal do CHDevFlow (`ch`)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from chdevflow import __version__
from chdevflow.core.init import run_init
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
