#!/usr/bin/env python3
"""Gera docs/ARVORE_PROJETO.md usando nomes de arquivos, nunca seus conteúdos."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Garante importação direta de src sem depender de instalação prévia
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from chdevflow.core.tree import (
    EXCLUDED_NAMES,
    EXCLUDED_PARTS,
    EXCLUDED_SUFFIXES,
    gather,
    generate,
    render_tree,
    safe,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="Raiz do projeto")
    args = parser.parse_args()
    out, changed = generate(args.path.resolve())
    print(f"{'Gerado' if changed else 'Sem alterações'}: {out}")


if __name__ == "__main__":
    main()
