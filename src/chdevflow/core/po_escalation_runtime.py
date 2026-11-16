"""Gate 3 F7: identidade observavel dos modulos Python carregados.

Defesa em profundidade para um checkout local; NAO e attestation de artefato
imutavel, nem substitui um runner isolado e um build reproduzivel auditado.
"""
from __future__ import annotations

import hashlib
import inspect
import marshal
from pathlib import Path
import re
import subprocess
import sys
import tokenize
from types import CodeType, FunctionType
from typing import Any

# Apenas arquivos que participam diretamente do gate de publicacao F7.
CORE_MODULES = (
    "chdevflow.core.po_escalation_publication",
    "chdevflow.core.po_escalation_attestation",
    "chdevflow.core.po_escalation_provenance",
    "chdevflow.core.po_escalation_reservation",
    "chdevflow.core.po_escalation",
    "chdevflow.core.po_escalation_runtime",
    "chdevflow.core.intake",
    "chdevflow.core.experimental_pilot",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class RuntimeIdentityError(ValueError):
    """Falha fechada no vinculo dos modulos executados ao Git."""


def _git_output(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL, capture_output=True,
            check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeIdentityError("Git indisponivel para identidade F7") from exc
    if proc.returncode or not isinstance(proc.stdout, bytes):
        raise RuntimeIdentityError("Objeto Git F7 nao verificavel")
    try:
        return proc.stdout.decode("ascii", errors="strict").strip()
    except UnicodeError as exc:
        raise RuntimeIdentityError("Resposta Git F7 nao e ASCII") from exc


def _nested_compiled(code: CodeType) -> dict[str, CodeType]:
    result: dict[str, CodeType] = {}
    for value in code.co_consts:
        if isinstance(value, CodeType):
            # co_qualname inclui nomes de classes/metodos e escopos locais.
            result[value.co_qualname] = value
            result.update(_nested_compiled(value))
    return result


def _runtime_functions(module: Any) -> dict[str, CodeType]:
    found: dict[str, CodeType] = {}
    for obj in vars(module).values():
        if inspect.isfunction(obj) and obj.__module__ == module.__name__:
            found[obj.__qualname__] = obj.__code__
        elif inspect.isclass(obj) and obj.__module__ == module.__name__:
            for member in vars(obj).values():
                if isinstance(member, (staticmethod, classmethod)):
                    member = member.__func__
                if (isinstance(member, FunctionType)
                        and member.__module__ == module.__name__):
                    found[member.__qualname__] = member.__code__
    return found


def _verify_module_code(module: Any, filename: Path) -> str:
    """Compara code objects reais aos produzidos pela origem versionada.

    Detecta carregamento de .pyc antigo e troca em memoria de funcoes/metodos
    Python diretamente definidos; nao previne monkeypatch dinamico posterior.
    """
    try:
        with tokenize.open(filename) as stream:
            source = stream.read()
        expected = _nested_compiled(compile(source, str(filename), "exec", dont_inherit=True))
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        raise RuntimeIdentityError("Fonte Python F7 nao recompilavel") from exc
    runtime = _runtime_functions(module)
    # Decorators podem manter o simbolo exportado como wrapper nao FunctionType.
    # A ausencia da exportacao falha fechado; o bytecode Python direto ainda
    # deve coincidir quando a funcao estiver acessivel como FunctionType.
    missing = [name for name in expected if name.isidentifier()
               and name not in vars(module)]
    if missing:
        raise RuntimeIdentityError("Funcao Python F7 ausente no runtime: " + missing[0])
    for name, code in runtime.items():
        baseline = expected.get(name)
        if baseline is None or marshal.dumps(code) != marshal.dumps(baseline):
            raise RuntimeIdentityError("Bytecode Python carregado difere da fonte F7")
    digest = hashlib.sha256()
    for name, code in sorted(runtime.items()):
        digest.update(name.encode("utf-8"))
        digest.update(marshal.dumps(code))
    return digest.hexdigest()


def verify_loaded_f7_modules(root: Path, commit_sha: str) -> str:
    """Cria comprovante dos blobs Git e code objects que estao em memoria.

    Fonte de referencia = commit Git fixado pelo PO; origem em memoria =
    modulos importados no interpretador atual. Falha na menor divergencia.
    """
    if not isinstance(commit_sha, str) or not HEX40.fullmatch(commit_sha):
        raise RuntimeIdentityError("Commit F7 invalido no verificador runtime")
    root = root.resolve(strict=True)
    digest = hashlib.sha256()
    for name in CORE_MODULES:
        module = sys.modules.get(name)
        relative = Path("src", *name.split(".")).with_suffix(".py")
        expected_path = root / relative
        if module is None or not isinstance(getattr(module, "__file__", None), str):
            raise RuntimeIdentityError("Modulo F7 nao carregado")
        # Não seguir symlinks ou junctions de ancestrais na origem do modulo.
        path = Path(module.__file__)
        for ancestor in (path, *path.parents):
            if ancestor == root.parent:
                break
            if (ancestor.is_symlink()
                    or (hasattr(ancestor, "is_junction") and ancestor.is_junction())):
                raise RuntimeIdentityError("Modulo F7 atravessa link simbolico")
        try:
            if path.resolve(strict=True) != expected_path.resolve(strict=True):
                raise RuntimeIdentityError("Modulo F7 carregado de origem inesperada")
            if not path.is_file():
                raise RuntimeIdentityError("Fonte F7 nao encontrada")
        except OSError as exc:
            raise RuntimeIdentityError("Arquivo de modulo F7 indisponivel") from exc
        rel = relative.as_posix()
        expected_blob = _git_output(root, "rev-parse", "--verify", f"{commit_sha}:{rel}")
        real_blob = _git_output(root, "hash-object", f"--path={rel}", str(path))
        if not HEX40.fullmatch(expected_blob) or real_blob != expected_blob:
            raise RuntimeIdentityError("Blob de modulo F7 difere do commit auditado")
        runtime_sha = _verify_module_code(module, path)
        digest.update(rel.encode("utf-8"))
        digest.update(expected_blob.encode("ascii"))
        digest.update(runtime_sha.encode("ascii"))
    return digest.hexdigest()
