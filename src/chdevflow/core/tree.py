"""Geração da árvore do projeto em docs/ARVORE_PROJETO.md."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

EXCLUDED_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "worlds",
    "world",
    "mundos",
    "saves",
    "backups",
    "backup",
    "logs",
    "secrets",
    "credentials",
    ".next",
    "dist",
    "build",
    "coverage",
    "tmp",
    "temp",
}
EXCLUDED_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "token",
    "secrets.json",
    "credentials.json",
}
EXCLUDED_SUFFIXES = {".pem", ".p12", ".pfx", ".key", ".kdbx"}


def safe(rel: Path) -> bool:
    """Verifica se um caminho relativo é seguro para inclusão na árvore."""
    parts = [p.lower() for p in rel.parts]
    if any(p in EXCLUDED_PARTS for p in parts):
        return False
    for name in parts:
        if name in EXCLUDED_NAMES or name.startswith(".env.") or name.endswith(".secret"):
            return False
    return rel.suffix.lower() not in EXCLUDED_SUFFIXES


def gather(root: Path) -> tuple[list[Path], str]:
    """Coleta caminhos seguros a partir do Git ou do sistema de arquivos local."""
    p = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if p.returncode == 0:
        raw_paths = [
            Path(x.decode("utf-8", errors="replace"))
            for x in p.stdout.split(b"\0")
            if x
        ]
        valid_paths = sorted({path for path in raw_paths if safe(path)})
        return (
            valid_paths,
            "Arquivos rastreados pelo Git (arquivos novos não commitados podem estar ausentes)",
        )

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
    """Renderiza árvore visual formatada a partir da lista de caminhos."""
    root: dict = {}
    for path in paths:
        node = root
        for part in path.parts:
            node = node.setdefault(part, {})
    lines: list[str] = []

    def walk(node: dict, prefix: str = "") -> None:
        items = sorted(
            node.items(),
            key=lambda pair: (not bool(pair[1]), pair[0].casefold()),
        )
        for i, (name, children) in enumerate(items):
            last = i == len(items) - 1
            lines.append(
                prefix + ("└── " if last else "├── ") + name + ("/" if children else "")
            )
            if children:
                walk(children, prefix + ("    " if last else "│   "))

    walk(root)
    return "\n".join(lines) if lines else "(sem arquivos selecionados)"


def generate(root: Path) -> tuple[Path, bool]:
    """Gera docs/ARVORE_PROJETO.md se necessário. Retorna (caminho_arquivo, se_houve_alteração)."""
    if not root.is_dir():
        raise FileNotFoundError(f"Diretório não existe: {root}")
    files, origin = gather(root)
    dest = root / "docs" / "ARVORE_PROJETO.md"
    target_rel = Path("docs/ARVORE_PROJETO.md")
    if target_rel not in files:
        files.append(target_rel)

    tree_content = render_tree(sorted(files))
    text = (
        "# Árvore do projeto\n\n"
        "> Gerado automaticamente. Não editar manualmente.\n"
        f"> Fonte: {origin}.\n"
        "> Conteúdo de arquivos, credenciais e áreas de produção não são lidos nem reproduzidos.\n\n"
        "```text\n"
        f"{tree_content}\n"
        "```\n"
    )

    if dest.exists() and dest.read_text(encoding="utf-8") == text:
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera docs/ARVORE_PROJETO.md usando nomes de arquivos, nunca seus conteúdos."
    )
    parser.add_argument(
        "--path", type=Path, default=Path.cwd(), help="Raiz do projeto (padrão: atual)"
    )
    args = parser.parse_args(argv)
    try:
        out, changed = generate(args.path.resolve())
        print(f"{'Gerado' if changed else 'Sem alterações'}: {out}")
        return 0
    except Exception as exc:
        print(f"Erro em ch tree: {exc}", file=sys.stderr)
        return 1
