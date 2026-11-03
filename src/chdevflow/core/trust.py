"""Gerenciamento de confiança explícita para execução de projetos C.H.

A concessão de confiança manifesta consentimento explícito do operador humano
para execução dos comandos de teste e build do projeto.
NÃO constitui sandbox de sistema operacional.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any

from chdevflow.core.config import load_manifest

TRUST_FILE_REL = Path(".ch") / "trust.json"

RELEVANT_CONFIG_FILES: tuple[str, ...] = (
    "chdevflow.yaml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "Pipfile.lock",
    "uv.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
)

EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    ".git",
    ".ch",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
})


class TrustIntegrityError(RuntimeError):
    """Erro em caso de falha de integridade, arquivos ilegíveis ou estado Git incerto (fail-closed)."""
    pass


def _hash_file(path: Path) -> str:
    """Calcula hash SHA-256 do conteúdo de um arquivo."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".sh", ".bash", ".zsh", ".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx",
    ".rb", ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".java", ".kt", ".cs",
    ".php", ".pl", ".lua", ".swift"
})

DOCUMENTATION_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".rst", ".adoc", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".pdf", ".drawio"
})


def _extract_explicit_targets(project_root: Path) -> set[str]:
    """
    Extrai alvos de arquivos explicitamente referenciados nos comandos de verificação do manifesto.
    Identifica scripts Python, scripts de shell e binários relativos, resolvendo symlinks internos
    para garantir que tanto o link quanto o arquivo canônico de destino sejam monitorados.
    """
    targets: set[str] = set()
    manifest_path = project_root / "chdevflow.yaml"
    if not manifest_path.is_file():
        return targets

    try:
        m_data = load_manifest(manifest_path)
        v_cmds = m_data.get("verification", {}).get("commands", [])
        for cmd in v_cmds:
            if not isinstance(cmd, str) or not cmd.strip():
                continue
            try:
                toks = shlex.split(cmd, posix=True)
            except Exception:
                continue
            if not toks:
                continue

            bin_name = toks[0].lower()
            script_candidate: str | None = None

            # 1. Invocação de interpretador Python (python / python3)
            if bin_name in ("python", "python3"):
                idx = 1
                while idx < len(toks):
                    arg = toks[idx]
                    if arg == "-m":
                        # Invocação de módulo (ex: unittest, pytest): não há script alvo
                        break
                    if arg in ("-W", "-X"):
                        idx += 2
                        continue
                    if arg.startswith(("-W", "-X")):
                        idx += 1
                        continue
                    if arg.startswith("-"):
                        idx += 1
                        continue
                    # Primeiro argumento posicional após opções do interpretador é o script alvo
                    script_candidate = arg
                    break

            # 2. Invocação de interpretador shell (sh, bash, zsh)
            elif bin_name in ("sh", "bash", "zsh"):
                idx = 1
                while idx < len(toks):
                    arg = toks[idx]
                    if arg.startswith("-"):
                        idx += 1
                        continue
                    script_candidate = arg
                    break

            # 3. Execução direta de script relativo (ex: ./scripts/run ou scripts/run.py)
            elif "/" in toks[0] and not toks[0].startswith("/"):
                script_candidate = toks[0].lstrip("./")

            if script_candidate:
                p_cand = Path(script_candidate)
                if not p_cand.is_absolute() and ".." not in p_cand.parts:
                    cand_str = str(p_cand)
                    targets.add(cand_str)
                    targets.add(script_candidate)

                    full_cand = project_root / p_cand
                    if full_cand.is_symlink():
                        try:
                            resolved_cand = full_cand.resolve()
                            if resolved_cand.is_relative_to(project_root.resolve()):
                                targets.add(str(resolved_cand.relative_to(project_root.resolve())))
                        except Exception:
                            pass
    except Exception:
        pass

    return targets


def _is_relevant_for_trust(
    file_path: str,
    project_root: Path | None = None,
    explicit_targets: set[str] | None = None,
) -> bool:
    """
    Determina se um caminho de arquivo é relevante para integridade e trust do projeto.
    Adota política defensiva fail-closed:
    1. Qualquer arquivo explicitamente referenciado nos comandos de verificação do runner é SEMPRE relevante
       (inclusive se situado sob .ch/, build/, etc.).
    2. Arquivos internos sob '.ch/' não referenciados em comandos são desconsiderados (evita auto-invalidação por relatórios/metadados).
    3. Manifestos e arquivos de build/configuração são SEMPRE relevantes.
    4. Qualquer arquivo de código/script (.py, .sh, etc.) ou sem extensão ou executável (+x) é SEMPRE relevante.
    5. Documentação puramente textual/visual (.md, imagens) não referenciada como alvo de execução é isenta.
    """
    clean = file_path.strip().strip('"').strip("'")
    if not clean:
        return False

    p = Path(clean)
    parts = p.parts

    # 1. Alvo explicitamente referenciado em comandos de verificação do runner é SEMPRE relevante
    if explicit_targets:
        if str(p) in explicit_targets or clean in explicit_targets:
            return True

    # 2. Pastas internas de governança e evidências do próprio chdevflow (quando não for alvo do runner)
    if parts and parts[0] == ".ch":
        return False

    name_lower = p.name.lower()
    # 3. Manifestos e arquivos de build críticos são SEMPRE relevantes
    if name_lower in {f.lower() for f in RELEVANT_CONFIG_FILES} or name_lower.startswith("requirements"):
        return True

    suffix_lower = p.suffix.lower()

    # 4. Extensões conhecidas de código e scripts executáveis (em qualquer pasta, inclusive docs/)
    if suffix_lower in CODE_EXTENSIONS:
        return True

    # 5. Arquivo sem extensão (scripts executáveis Unix): sempre relevante para prevenir bypass
    if suffix_lower == "" and name_lower not in EXCLUDED_DIR_NAMES:
        return True

    # 6. Se o arquivo físico tiver permissão de execução (+x), é sempre relevante
    if project_root:
        full_path = (project_root / p).resolve()
        if full_path.is_file() and os.access(full_path, os.X_OK):
            return True

    # 7. Extensões puramente documentais ou visuais não referenciadas em comandos
    if suffix_lower in DOCUMENTATION_EXTENSIONS:
        return False

    # 8. Se for arquivo .txt não referenciado em comandos, é tratado como documentação
    if suffix_lower == ".txt":
        return False

    # Qualquer outro arquivo (configuração .toml, .yaml, .json, etc.) é relevante
    return True


def get_git_state(project_root: Path) -> str:
    """
    Captura o estado do Git local incluindo commit HEAD, modificações, renomeações e novos arquivos untracked.
    Utiliza formato inequívoco NUL-terminado ('git status --porcelain=v1 -z -uall') para suporte completo
    a nomes com caracteres Unicode/acentuação, espaços e caracteres especiais sem escape octal.
    Incorpora o hash de conteúdo de cada arquivo relevante para detectar alterações sucessivas
    mesmo quando o código de status do Git permanece idêntico.
    Falha fechado se houver erro ao ler arquivos ou executar git status.
    """
    root = project_root.resolve()
    git_dir = root / ".git"
    if not git_dir.exists():
        return ""

    explicit_targets = _extract_explicit_targets(root)

    try:
        proc_status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "-uall"],
            capture_output=True,
            check=False,
            timeout=10.0,
        )
        if proc_status.returncode != 0:
            err_msg = proc_status.stderr.decode("utf-8", errors="replace").strip()
            raise TrustIntegrityError(f"Falha ao executar 'git status': {err_msg}")

        raw_output = proc_status.stdout
        tokens = raw_output.split(b"\x00")
        if tokens and tokens[-1] == b"":
            tokens.pop()

        relevant_entries: list[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if not token:
                i += 1
                continue

            if len(token) < 3:
                raise TrustIntegrityError(f"Entrada malformada no git status: {token!r}")

            status_code = token[:2].decode("utf-8", errors="surrogateescape")
            target_path_str = token[3:].decode("utf-8", errors="surrogateescape")
            orig_path_str: str | None = None

            if "R" in status_code or "C" in status_code:
                i += 1
                if i >= len(tokens):
                    raise TrustIntegrityError(f"Caminho de origem ausente para renomeação/cópia com status '{status_code}'")
                orig_path_str = tokens[i].decode("utf-8", errors="surrogateescape")

            i += 1

            is_relevant = _is_relevant_for_trust(target_path_str, project_root=root, explicit_targets=explicit_targets)
            if orig_path_str and not is_relevant:
                is_relevant = _is_relevant_for_trust(orig_path_str, project_root=root, explicit_targets=explicit_targets)

            if not is_relevant:
                continue

            file_path = (root / target_path_str).resolve()
            if not file_path.is_relative_to(root):
                raise TrustIntegrityError(f"Arquivo relevante fora da raiz do projeto: {target_path_str}")

            if orig_path_str:
                orig_file_path = (root / orig_path_str).resolve()
                if not orig_file_path.is_relative_to(root):
                    raise TrustIntegrityError(f"Arquivo de origem fora da raiz do projeto: {orig_path_str}")

            if "D" in status_code:
                content_hash = "DELETED"
            elif file_path.is_file():
                content_hash = _hash_file(file_path)
                if not content_hash:
                    raise TrustIntegrityError(f"Arquivo relevante ilegível ou corrompido: {target_path_str}")
            else:
                content_hash = "NON_REGULAR"

            entry_path = f"{orig_path_str}->{target_path_str}" if orig_path_str else target_path_str
            relevant_entries.append(f"{status_code}:{entry_path}:{content_hash}")

        filtered_porcelain = "\n".join(sorted(relevant_entries))

        proc_rev = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        head_sha = proc_rev.stdout.strip() if proc_rev.returncode == 0 else "EMPTY_HEAD"

        combined = f"HEAD:{head_sha}\nPORCELAIN_WITH_CONTENT:\n{filtered_porcelain}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()
    except subprocess.TimeoutExpired:
        raise TrustIntegrityError("Timeout excedido ao verificar estado do Git.")
    except TrustIntegrityError:
        raise
    except Exception as exc:
        raise TrustIntegrityError(f"Erro inesperado ao capturar estado do Git: {exc}")


def compute_project_fingerprint(project_root: Path) -> tuple[str, dict[str, str]]:
    """
    Calcula uma impressão digital (fingerprint) composta do projeto com falha fechada.
    Considera chdevflow.yaml, arquivos de build/configuração e estado Git local com hashes de conteúdo.
    """
    root = project_root.resolve()

    # 1. Hash do manifesto chdevflow.yaml
    manifest_path = root / "chdevflow.yaml"
    if manifest_path.is_file():
        manifest_hash = _hash_file(manifest_path)
        if not manifest_hash:
            raise TrustIntegrityError("Manifesto chdevflow.yaml ilegível na verificação de integridade.")
    else:
        manifest_hash = "no-manifest"

    # 2. Hash de arquivos de build relevantes
    config_hashes: list[str] = []
    for cfg_name in sorted(RELEVANT_CONFIG_FILES):
        cfg_file = root / cfg_name
        if cfg_file.is_file():
            h = _hash_file(cfg_file)
            if not h:
                raise TrustIntegrityError(f"Arquivo de configuração ilegível: {cfg_name}")
            config_hashes.append(f"{cfg_name}:{h}")

    # Procura também em subpastas imediatas de apps/ se houver monorepo
    apps_dir = root / "apps"
    if apps_dir.is_dir():
        for sub in sorted(apps_dir.iterdir()):
            if sub.is_dir() and sub.name not in EXCLUDED_DIR_NAMES:
                for cfg_name in sorted(RELEVANT_CONFIG_FILES):
                    cfg_file = sub / cfg_name
                    if cfg_file.is_file():
                        rel = str(cfg_file.relative_to(root))
                        h = _hash_file(cfg_file)
                        if not h:
                            raise TrustIntegrityError(f"Arquivo de configuração em apps/ ilegível: {rel}")
                        config_hashes.append(f"{rel}:{h}")

    configs_combined = hashlib.sha256("\n".join(config_hashes).encode("utf-8")).hexdigest()

    # 3. Alvos explícitos de execução do runner (validação física e hash canônico de alvos e symlinks)
    explicit_targets = _extract_explicit_targets(root)
    targets_entries: list[str] = []
    for target_rel_str in sorted(explicit_targets):
        target_path = root / target_rel_str

        # Se for symlink
        if target_path.is_symlink():
            try:
                link_dest = os.readlink(target_path)
            except OSError as err:
                raise TrustIntegrityError(f"Falha ao ler symlink de alvo '{target_rel_str}': {err}")
            try:
                resolved = target_path.resolve(strict=True)
            except (OSError, RuntimeError) as err:
                raise TrustIntegrityError(f"Symlink de alvo quebrado ou inacessível '{target_rel_str}': {err}")
            if not resolved.is_relative_to(root):
                raise TrustIntegrityError(
                    f"Symlink de alvo aponta para fora da raiz do projeto: '{target_rel_str}' -> '{link_dest}'"
                )
            if not resolved.is_file():
                raise TrustIntegrityError(
                    f"Destino de symlink de alvo deve ser arquivo regular: '{target_rel_str}' -> '{link_dest}'"
                )
            h = _hash_file(resolved)
            if not h:
                raise TrustIntegrityError(f"Destino de symlink de alvo ilegível: '{target_rel_str}'")
            targets_entries.append(f"TARGET_SYMLINK:{target_rel_str}->{link_dest}:{h}")

        elif target_path.is_file():
            resolved = target_path.resolve()
            if not resolved.is_relative_to(root):
                raise TrustIntegrityError(f"Alvo de execução reside fora da raiz do projeto: '{target_rel_str}'")
            h = _hash_file(resolved)
            if not h:
                raise TrustIntegrityError(f"Alvo de execução ilegível: '{target_rel_str}'")
            targets_entries.append(f"TARGET_FILE:{target_rel_str}:{h}")

        elif target_path.is_dir():
            raise TrustIntegrityError(f"Alvo de execução não pode ser diretório: '{target_rel_str}'")
        else:
            raise TrustIntegrityError(f"Alvo de execução referenciado no manifesto não encontrado: '{target_rel_str}'")

    targets_combined = hashlib.sha256("\n".join(targets_entries).encode("utf-8")).hexdigest()

    # 4. Estado local Git (inclui arquivos modificados e untracked relevantes com hashes de conteúdo)
    git_hash = get_git_state(root)
    if not git_hash:
        # Se não for repositório Git, gera hash das árvores de código/configuração
        file_list: list[str] = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(root)
                rel_parts = rel.parts
                is_explicit = (str(rel) in explicit_targets)
                if is_explicit or not any(excluded in rel_parts for excluded in EXCLUDED_DIR_NAMES):
                    if _is_relevant_for_trust(str(rel), project_root=root, explicit_targets=explicit_targets):
                        h = _hash_file(p)
                        if not h:
                            raise TrustIntegrityError(f"Arquivo de código ilegível: {rel}")
                        file_list.append(f"{rel}:{h}")
        git_hash = hashlib.sha256("\n".join(file_list).encode("utf-8")).hexdigest()

    # 5. Impressão digital composta
    composite_raw = f"MANIFEST:{manifest_hash}|CONFIGS:{configs_combined}|TARGETS:{targets_combined}|STATE:{git_hash}"
    fingerprint = hashlib.sha256(composite_raw.encode("utf-8")).hexdigest()

    components = {
        "manifest_sha256": manifest_hash,
        "configs_sha256": configs_combined,
        "targets_sha256": targets_combined,
        "local_state_sha256": git_hash,
    }

    return fingerprint, components


def grant_trust(project_root: Path, declaration: str = "explicit_consent") -> dict[str, Any]:
    """
    Grava registro de confiança explícita em .ch/trust.json vinculado ao estado atual.
    Ajusta permissões para 0600 em sistemas POSIX.
    """
    root = project_root.resolve()
    fingerprint, components = compute_project_fingerprint(root)

    trust_dir = root / ".ch"
    trust_dir.mkdir(parents=True, exist_ok=True)

    trust_data: dict[str, Any] = {
        "trust_version": "1",
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "declaration": declaration,
        "notice": (
            "Manifestação explícita de consentimento para execução de código de projeto. "
            "Não constitui sandbox de sistema operacional."
        ),
        "fingerprint": fingerprint,
        "components": components,
    }

    trust_file = root / TRUST_FILE_REL
    content = json.dumps(trust_data, indent=2, ensure_ascii=False) + "\n"
    trust_file.write_text(content, encoding="utf-8")

    # Permissões restritas ao usuário atual (0600)
    try:
        os.chmod(trust_file, 0o600)
    except Exception:
        pass

    return trust_data


def check_trust(project_root: Path) -> tuple[bool, str]:
    """
    Verifica se o projeto possui registro de confiança válido e íntegro.
    Retorna (True, mensagem) se válido; (False, motivo) se ausente ou invalidado.
    """
    root = project_root.resolve()
    trust_file = root / TRUST_FILE_REL

    if not trust_file.is_file():
        return (
            False,
            "Registro de confiança ausente (.ch/trust.json). "
            "Execute 'ch verify --trust' para manifestar consentimento explícito."
        )

    try:
        content = trust_file.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception:
        return (False, "Registro de confiança corrompido ou ilegível em .ch/trust.json.")

    expected_fp = data.get("fingerprint")
    if not expected_fp or not isinstance(expected_fp, str):
        return (False, "Registro de confiança incompleto em .ch/trust.json.")

    try:
        current_fp, _ = compute_project_fingerprint(root)
    except TrustIntegrityError as tie:
        return (False, f"Falha de integridade ao verificar o projeto (fail-closed): {tie}")
    except Exception as exc:
        return (False, f"Falha inesperada ao inspecionar integridade do projeto (fail-closed): {exc}")

    if current_fp != expected_fp:
        return (
            False,
            "Confiança invalidada: arquivos de configuração ou código do projeto "
            "foram modificados desde a concessão anterior. "
            "Execute 'ch verify --trust' para revalidar conscientemente."
        )

    return (True, "Projeto com confiança válida.")


def invalidate_trust(project_root: Path) -> None:
    """Remove o registro de confiança local forçando nova autorização explícita."""
    trust_file = project_root.resolve() / TRUST_FILE_REL
    if trust_file.is_file():
        try:
            trust_file.unlink()
        except Exception:
            pass
