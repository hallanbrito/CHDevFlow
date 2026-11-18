"""Serviço de preparação guiada de missões locais e preflight (Issue #124 / Fatia A).

Responsabilidades:
- Validação estrita de escopo, permissões, repositório e caminho único Python (.py).
- Isolamento absoluto da pasta de laboratórios em relação ao clone principal (P1).
- Validação de que os critérios de aceite referenciam testes preexistentes rastreados no Git (P1).
- Criação segura de laboratório descartável Git `CH-Lab-*` em branch temporária,
  sem modificar ou escrever arquivos no clone principal.
- Bloqueio antecipado fail-closed se houver trava ativa no host, sem mutação de arquivos (P2).
- Geração de prompt versionado e commit temporário na branch do laboratório
  para garantir estado Git limpo exigido pelo contrato de F6.
- Geração de manifesto `manual/v1` em arquivo JSON externo à worktree.
- Pré-validação determinística via `_preflight` do motor F6 preexistente,
  rejeitando links simbólicos de manifesto com paridade ao despacho (P2).
- Verificação de travas ativas/crash e inventário de ferramentas locais no host.
- Distinção honesta entre APTO PARA DESPACHO e PREPARADO SEM CLI (P2).
- Retorno de status auditável com justificativas e alertas de segurança.
- Não aciona modelos (AGY/Codex), não executa merge, deploy ou escrita no Project #2.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from typing import Any
from uuid import uuid4

from chdevflow.core.generic_cycle import _preflight
from ch_control_center.config import obter_diretorio_dados_seguro
from ch_control_center.services.execution_service import sanitizar_log

# Repositórios permitidos para execução guiada nesta fatia
REPOSITORIOS_PERMITIDOS: frozenset[str] = frozenset({"hallanbrito/CHDevFlow"})

# Limites operacionais de segurança (F6 / D06)
TIMEOUT_MINIMO: int = 120
TIMEOUT_MAXIMO: int = 900
TAMANHO_MAXIMO_PROMPT: int = 12000
TAMANHO_MAXIMO_ALVO: int = 32000


class MissionPreparationError(Exception):
    """Exceção base para erros durante a preparação guiada de missões."""


class PreparationValidationError(MissionPreparationError):
    """Exceção levantada para parâmetros inválidos ou violações de política/segurança."""


class PreparationConflictError(MissionPreparationError):
    """Exceção levantada quando há colisão de diretório, branch ou trava ativa."""


@dataclass
class PreflightResult:
    apto: bool
    status: str  # "APTO" | "PREPARADO_SEM_CLI" | "BLOQUEADO"
    motivos_bloqueio: list[str] = field(default_factory=list)
    avisos_seguranca: list[str] = field(default_factory=list)
    mission_id: str | None = None
    issue: int | None = None
    manifest_path: str | None = None
    worktree: str | None = None
    branch: str | None = None
    base_sha: str | None = None
    repository: str | None = None
    target_file: str | None = None
    prompt_ref: str | None = None
    lock_ativo: bool = False
    testes_independentes_count: int = 0
    testes_referenciados: list[str] = field(default_factory=list)
    ferramentas_cli: dict[str, bool] = field(default_factory=dict)
    cost_verified: bool = False
    os_isolation_verified: bool = False
    test_execution: str = "host"
    sem_consumo_agentes: bool = True
    auto_merge: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _exec_git(cwd: Path, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Executa comando Git com timeout e sem stdin."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


class MissionPreparationService:
    """Serviço responsável por validar, montar laboratório CH-Lab-* e gerar manifesto F6."""

    def __init__(
        self,
        source_repo: Path | None = None,
        labs_root: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.source_repo = (
            Path(source_repo).resolve()
            if source_repo
            else self._localizar_repositorio_fonte()
        )
        self.labs_root = (
            Path(labs_root).resolve()
            if labs_root
            else Path(os.getenv("CH_CC_LABS_ROOT", str(Path.home() / "CHDevFlow-Labs"))).resolve()
        )
        # P1: Validação preventiva de isolamento estrito logo na inicialização
        self._validar_isolamento_labs_root(self.labs_root, self.source_repo)

        self.data_dir = (
            Path(data_dir).resolve()
            if data_dir
            else obter_diretorio_dados_seguro()
        )
        self.lock_file = self.data_dir / "active_execution.lock"
        self.safe_empty_hooks_dir = self.data_dir / "safe_empty_hooks"
        self._obter_diretorio_hooks_vazio()
        self._prep_lock = threading.Lock()

    def _obter_diretorio_hooks_vazio(self) -> Path:
        """Garante e retorna um diretório estritamente vazio e controlado para core.hooksPath."""
        self.safe_empty_hooks_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            for item in self.safe_empty_hooks_dir.iterdir():
                if item.is_file() or item.is_symlink():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
        except Exception:
            pass
        return self.safe_empty_hooks_dir

    def _executar_git_seguro(
        self, cwd: Path, *args: str, timeout: float = 30.0
    ) -> subprocess.CompletedProcess[str]:
        """Executa comando Git inibindo hooks, fsmonitor e executores externos configuráveis (P1-A)."""
        empty_hooks = self._obter_diretorio_hooks_vazio()
        safe_opts = [
            "-c",
            f"core.hooksPath={empty_hooks.as_posix()}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.clean=",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.required=false",
        ]
        env = os.environ.copy()
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        return subprocess.run(
            ["git", *safe_opts, *args],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )

    def _rollback_recursos_missao(
        self,
        m_id: str,
        worktree_dir: Path,
        branch_name: str,
        manifest_path: Path,
    ) -> None:
        """Executa rollback estrito de recursos pertencentes exclusivamente a esta missão (P1-A)."""
        nome_esperado_wt = f"CH-Lab-{m_id}"
        nome_esperado_manifest = f"CH-Manifest-{m_id}.json"
        nome_esperado_branch = f"ch-lab/{m_id.lower()}"

        # 1. Limpeza da worktree (apenas se corresponder ao nome esperado e estiver sob labs_root)
        if worktree_dir.name == nome_esperado_wt and worktree_dir.parent.resolve() == self.labs_root.resolve():
            try:
                res_list = self._executar_git_seguro(self.source_repo, "worktree", "list", "--porcelain")
                if res_list.returncode == 0 and str(worktree_dir) in res_list.stdout:
                    self._executar_git_seguro(self.source_repo, "worktree", "remove", "--force", str(worktree_dir))
            except Exception:
                pass
            if worktree_dir.exists():
                try:
                    if worktree_dir.is_dir() and not worktree_dir.is_symlink():
                        shutil.rmtree(worktree_dir, ignore_errors=True)
                    else:
                        worktree_dir.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                self._executar_git_seguro(self.source_repo, "worktree", "prune")
            except Exception:
                pass

        # 2. Limpeza da branch (apenas se for exatamente a branch temporária da missão)
        if branch_name == nome_esperado_branch:
            try:
                res_b = self._executar_git_seguro(
                    self.source_repo, "rev-parse", "--verify", f"refs/heads/{branch_name}"
                )
                if res_b.returncode == 0:
                    self._executar_git_seguro(self.source_repo, "branch", "-D", branch_name)
            except Exception:
                pass

        # 3. Limpeza do manifesto (apenas se for o manifesto desta missão sob labs_root)
        if manifest_path.name == nome_esperado_manifest and manifest_path.parent.resolve() == self.labs_root.resolve():
            try:
                manifest_path.unlink(missing_ok=True)
                manifest_path.with_suffix(".tmp").unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _localizar_repositorio_fonte() -> Path:
        """Localiza a raiz do repositório Git atual a partir do ambiente ou árvore de pastas."""
        env_repo = os.getenv("CH_CC_SOURCE_REPO")
        if env_repo:
            p = Path(env_repo).resolve()
            if p.is_dir():
                return p

        # Tenta git rev-parse a partir do diretório de trabalho atual
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                caminho = Path(proc.stdout.strip()).resolve()
                if caminho.is_dir():
                    return caminho
        except Exception:
            pass

        # Fallback subindo a partir do arquivo atual
        atual = Path(__file__).resolve().parent
        for _ in range(6):
            if (atual / ".git").exists():
                return atual
            atual = atual.parent

        return Path.cwd().resolve()

    @staticmethod
    def _validar_isolamento_labs_root(labs_root: Path, source_repo: Path) -> None:
        """Garante de forma estrita que a pasta de laboratórios não contamine o clone principal (P1)."""
        lr = labs_root.resolve()
        sr = source_repo.resolve()
        if lr == sr:
            raise PreparationValidationError(
                f"Configuração insegura de labs_root: '{lr}' não pode ser igual ao repositório principal ('{sr}')."
            )
        if lr in sr.parents or sr in lr.parents:
            raise PreparationValidationError(
                f"Configuração insegura de labs_root: '{lr}' não pode estar contido no repositório principal ('{sr}') nem contê-lo."
            )
        try:
            if lr.is_relative_to(sr) or sr.is_relative_to(lr):
                raise PreparationValidationError(
                    f"Configuração insegura de labs_root: '{lr}' não pode estar contido no repositório principal ('{sr}') nem contê-lo."
                )
        except AttributeError:
            pass

    def verificar_ferramentas_locais(self) -> dict[str, bool]:
        """Verifica a presença das ferramentas de linha de comando no host (somente leitura, sem execução)."""
        return {
            "agy": shutil.which("agy") is not None,
            "codex": shutil.which("codex") is not None,
            "git": shutil.which("git") is not None,
            "python": shutil.which("python") is not None,
        }

    def verificar_lock_ativo(self) -> bool:
        """Verifica de forma fail-closed se existe trava ativa ou de crash anterior em disco."""
        return self.lock_file.exists()

    def validar_caminho_alvo(self, target_file: str, root: Path | None = None) -> str:
        """Valida que o arquivo alvo é um caminho Python único, relativo e seguro."""
        if not isinstance(target_file, str) or not target_file.strip():
            raise PreparationValidationError("Arquivo Python-alvo é obrigatório.")

        alvo = target_file.strip()
        if len(alvo) > 200:
            raise PreparationValidationError("Caminho do arquivo-alvo excede limite de 200 caracteres.")

        if "\\" in alvo:
            raise PreparationValidationError("Use barras normais (/) para o caminho do arquivo-alvo, sem barras invertidas.")

        if alvo.startswith("/"):
            raise PreparationValidationError("Caminho do arquivo-alvo deve ser relativo, sem barra inicial.")

        partes = [p for p in alvo.split("/") if p]
        if ".." in partes or any(c in alvo for c in "*?[]"):
            raise PreparationValidationError("Caminho do arquivo-alvo contém sequências proibidas ('..' ou coringas).")

        if not alvo.endswith(".py"):
            raise PreparationValidationError("F6: o arquivo-alvo deve ser estritamente um arquivo Python (.py).")

        if alvo.startswith("tests/") or alvo == "tests" or "tests" in partes[:-1]:
            raise PreparationValidationError("F6: o arquivo-alvo precisa estar fora do diretório 'tests/'.")

        base_check = root or self.source_repo
        if base_check and base_check.is_dir():
            p = base_check / alvo
            if p.is_symlink():
                raise PreparationValidationError("Arquivo-alvo não pode ser um link simbólico.")
            if not p.parent.is_dir() or p.parent.is_symlink():
                raise PreparationValidationError(f"Diretório pai do arquivo-alvo ('{p.parent.name}') não existe ou é symlink.")
            if p.exists() and p.is_file() and p.stat().st_size > TAMANHO_MAXIMO_ALVO:
                raise PreparationValidationError(f"Arquivo-alvo existente excede tamanho máximo de {TAMANHO_MAXIMO_ALVO} bytes.")

        return alvo

    def _extrair_e_validar_referencia_testes(
        self, criterios_aceite: str, root: Path
    ) -> list[str]:
        """Valida que os critérios de aceite referenciam testes independentes presentes como blobs em HEAD (P1-B)."""
        # P1-B: Regex canônica reconhece estritamente referências tests/**/test_*.py
        padrao = re.compile(
            r"(?:^|[\s\"'`(])(tests[/\\](?:[a-zA-Z0-9_-]+[/\\])*test_[a-zA-Z0-9_]+\.py)(?:$|[\s\"'`),:;])"
        )
        encontrados = padrao.findall(criterios_aceite)

        testes_validos_rastreados: list[str] = []

        for ref in encontrados:
            ref_norm = ref.replace("\\", "/")
            partes = ref_norm.split("/")
            if ".." in partes or "." in partes or any(not p for p in partes):
                continue
            if not ref_norm.startswith("tests/") or not ref_norm.endswith(".py"):
                continue
            if not partes[-1].startswith("test_"):
                continue

            caminho_completo = root / ref_norm
            # O arquivo deve existir fisicamente e não pode ser link simbólico
            if not caminho_completo.is_file() or caminho_completo.is_symlink():
                continue

            # Confirma se o teste é estritamente um blob regular presente em HEAD (rejeita staged-only no index)
            proc = self._executar_git_seguro(root, "ls-tree", "HEAD", ref_norm)
            if proc.returncode == 0 and proc.stdout.strip():
                linhas = proc.stdout.strip().splitlines()
                for linha in linhas:
                    campos = linha.split()
                    if len(campos) >= 2:
                        modo, tipo = campos[0], campos[1]
                        if tipo == "blob" and modo in ("100644", "100755"):
                            if ref_norm not in testes_validos_rastreados:
                                testes_validos_rastreados.append(ref_norm)
                            break

        if not testes_validos_rastreados:
            raise PreparationValidationError(
                "Critérios de aceite devem referenciar explicitamente pelo menos um arquivo de teste "
                "independente preexistente e presente como blob regular em HEAD sob 'tests/**/test_*.py' "
                "(ex: tests/test_modulo.py). Arquivos staged-only no índice, helpers sem prefixo 'test_' "
                "ou ausentes em HEAD são rejeitados. "
                "Validação automatizada não atesta relevância ou cobertura; revisão humana mandatória."
            )

        return testes_validos_rastreados

    @staticmethod
    def _extrair_testes_do_prompt(prompt_txt: str) -> list[str]:
        """Extrai a lista de testes rastreados prometidos no corpo do prompt versionado."""
        achados = re.findall(r"-\s+`([^`]+)`", prompt_txt)
        return [
            a.strip().replace("\\", "/")
            for a in achados
            if a.strip().startswith("tests/") and a.strip().endswith(".py")
        ]

    def verificar_preflight(
        self,
        manifest_path: str | Path,
        testes_esperados: list[str] | None = None,
    ) -> PreflightResult:
        """Executa pré-validação completa (contrato documental F6, git, lock e ferramentas)."""
        # P2: Preserva caminho sem chamar .resolve(), para manter detecção de symlink coerente com F6 e ExecutionService
        caminho_manifesto = Path(manifest_path).expanduser().absolute()
        motivos: list[str] = []
        avisos: list[str] = [
            "⚠️ cost_verified=false: Custo não verificado pelo painel; operador deve comprovar ausência de custos antes de qualquer despacho.",
            "⚠️ os_isolation_verified=false: Isolamento de SO não comprovado; testes e alterações ocorrem no ambiente do host.",
            "⚠️ test_execution=host: Testes automatizados executam diretamente no host, sem sandbox de SO.",
            "⚠️ autenticacao_clis=nao_verificada: Detecção de 'agy' e 'codex' comprova apenas presença no PATH do host, NÃO comprova autenticação, login ativo, permissões nem saldo/cotas.",
            "ℹ️ testes_independentes: Validação F6 comprova presença física e imutabilidade dos testes na worktree, NÃO sua relevância, cobertura ou suficiência para o objetivo da missão. Aceite final exige revisão humana pelo PO.",
            "ℹ️ sem_consumo_agentes=true: Esta preparação e pré-validação não consumiram modelos, agentes ou cotas.",
            "ℹ️ auto_merge=false: Nenhum merge, deploy ou escrita no Project #2 é realizado.",
        ]

        if caminho_manifesto.is_symlink():
            motivos.append("Manifesto ausente ou link simbolico (symlinks rejeitados por segurança).")

        lock_ativo = self.verificar_lock_ativo()
        if lock_ativo:
            motivos.append("Trava de execução ativa em disco ('active_execution.lock') ou missão interrompida por crash.")

        # P2: Verificação de ferramentas locais no host
        ferramentas = self.verificar_ferramentas_locais()
        cli_pendente = False
        if not ferramentas.get("git"):
            motivos.append("Git não encontrado no PATH do sistema host.")
        if not ferramentas.get("agy"):
            cli_pendente = True
            motivos.append("CLI AGY ('agy') não encontrada no PATH do host (necessária para execução F6).")
        if not ferramentas.get("codex"):
            cli_pendente = True
            motivos.append("CLI Codex ('codex') não encontrada no PATH do host (necessária para auditoria F6).")

        mission_id: str | None = None
        issue: int | None = None
        repository: str | None = None
        target_file: str | None = None
        worktree: str | None = None
        branch: str | None = None
        base_sha: str | None = None
        prompt_ref: str | None = None
        testes_count: int = 0
        todos_testes_esperados = set(testes_esperados or [])

        # Validação mandatória pelo motor de preflight preexistente
        try:
            mission_obj, root_path, target, prompt_txt, snapshot = _preflight(caminho_manifesto)
            mission_id = mission_obj.mission_id
            issue = mission_obj.issue
            repository = mission_obj.repository
            target_file = target
            worktree = str(root_path)
            base_sha = mission_obj.base_sha
            prompt_ref = mission_obj.prompt_ref
            testes_count = len([k for k in snapshot if k != mission_obj.prompt_ref])

            # P1-B: Extrai também referências prometidas gravadas no prompt da missão
            todos_testes_esperados.update(self._extrair_testes_do_prompt(prompt_txt))

            # P1-B: Confirma que CADA teste referenciado está presente no laboratório e integra o snapshot F6
            for t in sorted(todos_testes_esperados):
                t_posix = t.replace("\\", "/")
                p_lab = root_path / t_posix
                if not p_lab.is_file() or p_lab.is_symlink():
                    motivos.append(f"Teste obrigatório '{t_posix}' ausente do laboratório ou é link simbólico.")
                elif t_posix not in snapshot:
                    motivos.append(
                        f"Teste obrigatório '{t_posix}' não integra o snapshot de testes preexistentes do F6."
                    )

            # Consulta branch atual do laboratório
            res_branch = self._executar_git_seguro(root_path, "branch", "--show-current")
            if res_branch.returncode == 0:
                branch = res_branch.stdout.strip()

        except Exception as exc:
            msg_erro = sanitizar_log(str(exc))
            if "link simbolico" in msg_erro.lower() and "Manifesto ausente ou link simbolico" not in motivos:
                motivos.append(f"Validação _preflight F6 reprovada: {msg_erro}")
            elif not caminho_manifesto.is_symlink():
                motivos.append(f"Validação _preflight F6 reprovada: {msg_erro}")

        # P2: Separa PREPARADO de APTO PARA DESPACHO
        if len(motivos) == 0:
            apto = True
            status = "APTO"
        elif cli_pendente and all(("CLI" in m or "não encontrada no PATH" in m) for m in motivos):
            # Apenas faltam CLIs no host, mas a worktree e o manifesto estão válidos
            apto = False
            status = "PREPARADO_SEM_CLI"
        else:
            apto = False
            status = "BLOQUEADO"

        return PreflightResult(
            apto=apto,
            status=status,
            motivos_bloqueio=motivos,
            avisos_seguranca=avisos,
            mission_id=mission_id,
            issue=issue,
            manifest_path=str(caminho_manifesto),
            worktree=worktree,
            branch=branch,
            base_sha=base_sha,
            repository=repository,
            target_file=target_file,
            prompt_ref=prompt_ref,
            lock_ativo=lock_ativo,
            testes_independentes_count=testes_count,
            ferramentas_cli=ferramentas,
            cost_verified=False,
            os_isolation_verified=False,
            test_execution="host",
            sem_consumo_agentes=True,
            auto_merge=False,
        )

    def preparar_missao(
        self,
        *,
        issue: int,
        repository: str,
        target_file: str,
        objetivo: str,
        criterios_aceite: str,
        confirmacao_po: bool,
        timeout_segundos: int = 480,
        mission_id: str | None = None,
    ) -> PreflightResult:
        """Prepara com segurança o laboratório CH-Lab-*, o prompt e o manifesto manual/v1."""
        # 1. Validação de Confirmação Explícita do PO
        if confirmacao_po is not True:
            raise PreparationValidationError("Confirmação explícita do PO é obrigatória para preparar o laboratório.")

        # 2. Validação da Issue
        if not isinstance(issue, int) or issue < 1:
            raise PreparationValidationError("Número de Issue inválido (deve ser um inteiro >= 1).")

        # 3. Validação do Repositório
        repo_limpo = (repository or "").strip()
        if repo_limpo not in REPOSITORIOS_PERMITIDOS:
            raise PreparationValidationError(
                f"Repositório '{repo_limpo}' não permitido. Repositórios autorizados: {sorted(REPOSITORIOS_PERMITIDOS)}"
            )

        # 4. Validação do Arquivo Python-Alvo
        alvo_validado = self.validar_caminho_alvo(target_file, root=self.source_repo)

        # 5. Validação do Objetivo
        obj_limpo = (objetivo or "").strip()
        if not obj_limpo:
            raise PreparationValidationError("Objetivo da missão é obrigatório.")
        if len(obj_limpo) > 4000:
            raise PreparationValidationError("Texto do objetivo excede 4000 caracteres.")

        # P1: Validação de Critérios de Aceite com referência explícita a testes rastreados
        crit_limpo = (criterios_aceite or "").strip()
        if not crit_limpo:
            raise PreparationValidationError("Critérios de aceite / testes independentes preexistentes são obrigatórios.")
        if len(crit_limpo) > 4000:
            raise PreparationValidationError("Texto dos critérios de aceite excede 4000 caracteres.")

        testes_referenciados = self._extrair_e_validar_referencia_testes(crit_limpo, self.source_repo)

        # 6. Validação do Timeout
        if not isinstance(timeout_segundos, int) or not (TIMEOUT_MINIMO <= timeout_segundos <= TIMEOUT_MAXIMO):
            raise PreparationValidationError(
                f"Timeout deve estar entre {TIMEOUT_MINIMO} e {TIMEOUT_MAXIMO} segundos."
            )

        # 7. Identificador da Missão
        if mission_id:
            m_id = mission_id.strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", m_id):
                raise PreparationValidationError("ID de missão personalizado inválido (3–80 caracteres alfanuméricos/.-_).")
        else:
            sufixo = uuid4().hex[:8].upper()
            m_id = f"MISSAO-ISSUE-{issue}-{sufixo}"

        # 8. Verificação do Repositório Fonte
        if not self.source_repo.is_dir() or not (self.source_repo / ".git").exists():
            raise PreparationValidationError(f"Repositório fonte Git não localizado em '{self.source_repo}'.")

        res_head = self._executar_git_seguro(self.source_repo, "rev-parse", "--verify", "HEAD")
        if res_head.returncode != 0:
            raise PreparationValidationError("Falha ao obter commit HEAD do repositório fonte.")
        head_commit = res_head.stdout.strip()

        # Valida origin do repositório fonte
        res_remote = self._executar_git_seguro(self.source_repo, "remote", "get-url", "origin")
        origin_url = res_remote.stdout.strip() if res_remote.returncode == 0 else ""
        allowed_remotes = {
            f"https://github.com/{repo_limpo}",
            f"https://github.com/{repo_limpo}.git",
            f"git@github.com:{repo_limpo}.git",
            f"ssh://git@github.com/{repo_limpo}.git",
        }
        if origin_url not in allowed_remotes:
            raise PreparationValidationError(
                f"Origin do repositório fonte ('{origin_url}') não coincide com o repositório da missão ('{repo_limpo}')."
            )

        # Valida existência de suite de testes independente
        tests_dir = self.source_repo / "tests"
        if not tests_dir.is_dir():
            raise PreparationValidationError("Diretório de testes independentes 'tests/' não encontrado no repositório.")
        test_files = list(tests_dir.rglob("test_*.py"))
        if not test_files:
            raise PreparationValidationError("Nenhum arquivo de teste 'test_*.py' encontrado em 'tests/'.")

        with self._prep_lock:
            # P2: Fail-closed antecipado: bloqueia ANTES de criar worktree, branch ou manifesto se houver lock
            if self.verificar_lock_ativo():
                raise PreparationConflictError(
                    "Trava de execução ativa em disco ('active_execution.lock') ou missão em andamento no host. "
                    "Preparação de novos laboratórios recusada para evitar acúmulo de worktrees concorrentes (fail-closed)."
                )

            # P1: Validação de isolamento do labs_root antes de qualquer mkdir ou mutação
            self._validar_isolamento_labs_root(self.labs_root, self.source_repo)

            # 9. Definição segura de pastas de destino
            self.labs_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            worktree_dir = self.labs_root / f"CH-Lab-{m_id}"
            branch_name = f"ch-lab/{m_id.lower()}"
            manifest_path = self.labs_root / f"CH-Manifest-{m_id}.json"

            if worktree_dir.exists():
                raise PreparationConflictError(f"Diretório de laboratório '{worktree_dir}' já existe.")
            if manifest_path.exists():
                raise PreparationConflictError(f"Manifesto '{manifest_path}' já existe.")

            try:
                # 10. Criação do Laboratório Git descartável via worktree
                # Usa HEAD como base; neutraliza hooks, fsmonitor e executores configuráveis (P1-A)
                res_wt = self._executar_git_seguro(
                    self.source_repo,
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    str(worktree_dir),
                    head_commit,
                )
                if res_wt.returncode != 0:
                    raise MissionPreparationError(
                        f"Falha ao criar worktree descartável '{worktree_dir.name}': {sanitizar_log(res_wt.stderr)}"
                    )

                # 11. Escrita do Prompt versionado dentro do laboratório
                prompt_filename = "prompt_missao.txt"
                prompt_path = worktree_dir / prompt_filename

                lista_testes_txt = "\n".join(f"- `{t}`" for t in testes_referenciados)
                conteudo_prompt = (
                    f"# Missão #{issue} — {m_id}\n"
                    f"Repositório: {repo_limpo}\n"
                    f"Arquivo alvo único: {alvo_validado}\n\n"
                    f"## Objetivo da Missão\n"
                    f"{obj_limpo}\n\n"
                    f"## Critérios de Aceite e Testes Independentes Preexistentes\n"
                    f"{crit_limpo}\n\n"
                    f"### Testes Rastreados Validados no Repositório:\n"
                    f"{lista_testes_txt}\n\n"
                    f"## Diretrizes Estritas de Execução\n"
                    f"- Altere estritamente o arquivo alvo '{alvo_validado}'.\n"
                    f"- Não altere nenhum arquivo de teste em 'tests/' nem este arquivo de prompt.\n"
                    f"- Não crie novos arquivos fora do escopo autorizado.\n"
                    f"- Todas as alterações devem satisfazer integralmente os testes preexistentes.\n"
                )

                if len(conteudo_prompt) > TAMANHO_MAXIMO_PROMPT:
                    raise PreparationValidationError("Conteúdo consolidado do prompt excede limite de 12.000 caracteres.")

                prompt_path.write_text(conteudo_prompt, encoding="utf-8")

                # 12. Commit temporário na branch descartável para garantir worktree limpa (requisito F6)
                res_add = self._executar_git_seguro(worktree_dir, "add", prompt_filename)
                if res_add.returncode != 0:
                    raise MissionPreparationError("Falha ao registrar prompt no Git do laboratório.")

                res_commit = self._executar_git_seguro(
                    worktree_dir,
                    "-c",
                    "user.name=CHDevFlow Preparer",
                    "-c",
                    "user.email=chdevflow@local",
                    "commit",
                    "-m",
                    f"prep: prompt da missão {m_id}",
                )
                if res_commit.returncode != 0:
                    raise MissionPreparationError("Falha ao versionar prompt na branch temporária.")

                # 13. Obtenção do SHA base com o prompt commitado e verificação de worktree limpa
                res_base = self._executar_git_seguro(worktree_dir, "rev-parse", "--verify", "HEAD")
                if res_base.returncode != 0:
                    raise MissionPreparationError("Falha ao verificar SHA da branch temporária.")
                base_sha_lab = res_base.stdout.strip()

                res_status = self._executar_git_seguro(worktree_dir, "status", "--porcelain", "--untracked-files=all")
                if res_status.stdout.strip() != "":
                    raise MissionPreparationError("Laboratório recém-criado não está em estado Git limpo.")

                # P1-B: Verifica que cada teste referenciado existe fisicamente no laboratório
                for t in testes_referenciados:
                    p_teste_lab = worktree_dir / t
                    if not p_teste_lab.is_file() or p_teste_lab.is_symlink():
                        raise MissionPreparationError(
                            f"Falha de integridade: teste referenciado '{t}' não existe no laboratório criado."
                        )

                # 14. Geração do Manifesto manual/v1 fora da worktree
                dados_manifesto = {
                    "schema": "chdevflow.pipeline.manual/v1",
                    "mission_id": m_id,
                    "repository": repo_limpo,
                    "issue": issue,
                    "base_sha": base_sha_lab,
                    "worktree": str(worktree_dir),
                    "allowed_paths": [alvo_validado],
                    "prompt_ref": prompt_filename,
                    "timeout_seconds": timeout_segundos,
                }

                temp_manifest = manifest_path.with_suffix(".tmp")
                temp_manifest.write_text(
                    json.dumps(dados_manifesto, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temp_manifest.replace(manifest_path)

            except Exception:
                # P1-A: Rollback estrito de worktree, branch e manifesto mesmo após falha parcial do git
                self._rollback_recursos_missao(m_id, worktree_dir, branch_name, manifest_path)
                raise

        # 15. Executa preflight determinístico real no manifesto recém-gerado
        resultado = self.verificar_preflight(manifest_path, testes_esperados=testes_referenciados)
        resultado.testes_referenciados = testes_referenciados
        return resultado
