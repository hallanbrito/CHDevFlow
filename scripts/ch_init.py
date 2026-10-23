#!/usr/bin/env python3
"""Instala fundação C.H. só para caminhos ausentes; modo padrão = dry-run."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Garante importação direta de src sem depender de instalação prévia
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from chdevflow.core.init import run_init


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", required=True, type=Path, help="Diretório do projeto existente")
    ap.add_argument("--profile", choices=["generic", "hallancraft"], default="generic")
    ap.add_argument("--apply", action="store_true", help="Efetua criação (padrão apenas prévia)")
    args = ap.parse_args()

    destination = args.path.resolve()
    templates = Path(__file__).resolve().parent.parent / "templates"
    try:
        run_init(
            destination=destination,
            profile=args.profile,
            apply=args.apply,
            templates_dir=templates,
        )
    except FileNotFoundError as err:
        ap.error(str(err))


if __name__ == "__main__":
    main()
