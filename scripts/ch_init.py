#!/usr/bin/env python3
"""Instala fundação C.H. só para caminhos ausentes; modo padrão = dry-run."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", required=True, type=Path, help="Diretório do projeto existente")
    ap.add_argument("--profile", choices=["generic", "hallancraft"], default="generic")
    ap.add_argument("--apply", action="store_true", help="Efetua criação (padrão apenas prévia)")
    args = ap.parse_args()
    destination = args.path.resolve()
    if not destination.is_dir():
        ap.error(f"Diretório não encontrado: {destination}. Crie o diretório primeiro.")
    templates = Path(__file__).resolve().parent.parent / "templates"
    if not templates.is_dir():
        ap.error("Diretório templates não encontrado; mantenha scripts e templates juntos.")
    created = skipped = 0
    for src in sorted(templates.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(templates)
        if rel.as_posix() == "docs/CH/PILOTO_HALLANCRAFT.md" and args.profile != "hallancraft":
            continue
        dest = destination / rel
        if dest.exists():
            skipped += 1
            print("PRESERVAR", rel)
        else:
            created += 1
            print("CRIAR" if args.apply else "CRIARIA", rel)
            if args.apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # 'x' garante ausência de sobrescrita em eventual corrida concorrente.
                with src.open("rb") as source, dest.open("xb") as target:
                    shutil.copyfileobj(source, target)
    print(f"\nResultado: {'aplicado' if args.apply else 'simulado'}; {created} novos, {skipped} preservados.")
    if args.apply:
        print("Próximo passo: python scripts/ch_tree.py --path", destination)

if __name__ == "__main__":
    main()
