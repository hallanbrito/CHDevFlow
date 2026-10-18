#!/usr/bin/env python3
"""Gera docs/ARVORE_PROJETO.md usando nomes de arquivos, nunca seus conteúdos."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", "worlds", "world", "mundos", "saves", "backups", "backup", "logs", "secrets", "credentials", ".next", "dist", "build", "coverage", "tmp", "temp"}
EXCLUDED_NAMES = {".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "token", "secrets.json", "credentials.json"}
EXCLUDED_SUFFIXES = {".pem", ".p12", ".pfx", ".key", ".kdbx"}


def safe(rel: Path) -> bool:
    parts = [p.lower() for p in rel.parts]
    if any(p in EXCLUDED_PARTS for p in parts):
        return False
    for name in parts:
        if name in EXCLUDED_NAMES or name.startswith(".env.") or name.endswith(".secret"):
            return False
    return rel.suffix.lower() not in EXCLUDED_SUFFIXES


def gather(root: Path) -> tuple[list[Path], str]:
    p = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if p.returncode == 0:
        return (sorted({Path(x.decode("utf-8", errors="replace")) for x in p.stdout.split(b"\0") if x and safe(Path(x.decode("utf-8", errors="replace")))}), "Arquivos rastreados pelo Git (arquivos novos não commitados podem estar ausentes)")
    # Modo projeto novo: varrer diretório sem entrar em diretórios excluídos.
    paths: list[Path] = []
    for item in root.rglob("*"):
        if not item.is_file() or item.is_symlink():
            continue
        rel = item.relative_to(root)
        if safe(rel):
            paths.append(rel)
    return sorted(set(paths)), "Arquivos locais (repositório Git ainda não inicializado)"


def render_tree(paths: list[Path]) -> str:
    root: dict = {}
    for path in paths:
        node = root
        for part in path.parts:
            node = node.setdefault(part, {})
    lines: list[str] = []
    def walk(node: dict, prefix: str = "") -> None:
        items = sorted(node.items(), key=lambda pair: (not bool(pair[1]), pair[0].casefold()))
        for i, (name, children) in enumerate(items):
            last = i == len(items) - 1
            lines.append(prefix + ("└── " if last else "├── ") + name + ("/" if children else ""))
            if children:
                walk(children, prefix + ("    " if last else "│   "))
    walk(root)
    return "\n".join(lines) if lines else "(sem arquivos selecionados)"


def generate(root: Path) -> tuple[Path, bool]:
    if not root.is_dir():
        raise FileNotFoundError(f"Diretório não existe: {root}")
    files, origin = gather(root)
    dest = root / "docs" / "ARVORE_PROJETO.md"
    # Mostra a própria árvore de diretórios mesmo antes de versionar este arquivo.
    if Path("docs/ARVORE_PROJETO.md") not in files:
        files.append(Path("docs/ARVORE_PROJETO.md"))
    text = "# Árvore do projeto\n\n> Gerado automaticamente. Não editar manualmente.\n> Fonte: " + origin + ".\n> Conteúdo de arquivos, credenciais e áreas de produção não são lidos nem reproduzidos.\n\n```text\n" + render_tree(sorted(files)) + "\n```\n"
    if dest.exists() and dest.read_text(encoding="utf-8") == text:
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest, True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="Raiz do projeto")
    args = parser.parse_args()
    out, changed = generate(args.path.resolve())
    print(f"{'Gerado' if changed else 'Sem alterações'}: {out}")

if __name__ == "__main__":
    main()
