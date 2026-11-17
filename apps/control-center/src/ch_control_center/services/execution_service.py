"""Serviço de despacho e ciclo de vida de execuções locais (ExecutionService).

Implementa a ponte autorizada na Issue #121 (CC-DESPACHO-01):
- Conecta a interface do Control Center ao motor local `run_generic_cycle`.
- Trava de concorrência estrita: no máximo 1 missão ativa no host.
- Recuperação segura de lock após crash/reinício (fail-closed, sem replay).
- Validação mandatória de manifesto pré-preparado e confirmação explícita do PO.
- Cancelamento efetivo que encerra subprocessos e árvores filhas.
- Sanitização de logs e segredos antes de exibição ou persistência.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from chdevflow.core.generic_cycle import _preflight, run_generic_cycle, GenericResult
from chdevflow.core.local_executor import terminate_all_active_processes
from ch_control_center.config import DIRETORIO_DADOS_PADRAO, obter_diretorio_dados_seguro

_PADRAO_SEGREDO = re.compile(
    r"(?i)(?:gh[opsur]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}"
    r"|sk-[A-Za-z0-9_-]{18,}|(?:(?:api[_-]?key|token|password)\s*[:=]\s*)[^\s]+)"
)

MAX_TIMEOUT_TOTAL: int = 900
MIN_TIMEOUT_TOTAL: int = 120


class ExecutionConflictError(Exception):
    """Exceção levantada quando já existe uma missão em execução."""


class ManifestValidationError(Exception):
    """Exceção levantada quando o manifesto ou laboratório é inválido."""


class ExecutionNotFoundError(Exception):
    """Exceção levantada quando a execução solicitada não é encontrada."""


def sanitizar_log(texto: str) -> str:
    """Remove tokens e credenciais de saídas de log e diagnósticos."""
    if not isinstance(texto, str):
        return ""
    return _PADRAO_SEGREDO.sub("[REDACTED]", texto)


def _runner_accepts_param(fn: Any, param_name: str) -> bool:
    """Verifica antes da invocação se o callable aceita o parâmetro especificado ou **kwargs."""
    try:
        sig = inspect.signature(fn)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:  # **kwargs
                return True
            if param.name == param_name:
                return True
        return False
    except (ValueError, TypeError):
        return False


class ProcessStatus:
    VIVO = "VIVO"
    MORTO_COMPROVADO = "MORTO_COMPROVADO"
    INCONCLUSIVO = "INCONCLUSIVO"


def check_process_status(pid: Any) -> str:
    """Verifica de forma segura e fail-closed o status de um processo no host.

    Retorna:
    - VIVO: processo existe e está ativo no host.
    - MORTO_COMPROVADO: confirmação estrita de que o PID não existe mais no SO.
    - INCONCLUSIVO: falha de leitura, PID ausente/inválido ou impossibilidade de comprovar óbito.
    """
    if pid is None or not isinstance(pid, int) or pid <= 0:
        return ProcessStatus.INCONCLUSIVO

    # Se o PID for exatamente o do processo atual, ele está comprovadamente VIVO
    if pid == os.getpid():
        return ProcessStatus.VIVO

    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            err = kernel32.GetLastError()
            # ERROR_INVALID_PARAMETER (87): PID não existe mais no sistema
            if err == 87:
                return ProcessStatus.MORTO_COMPROVADO
            # ERROR_ACCESS_DENIED (5): processo existe, mas sem permissão de acesso -> está VIVO
            if err == 5:
                return ProcessStatus.VIVO
            # Qualquer outro erro é inconclusivo
            return ProcessStatus.INCONCLUSIVO

        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                if exit_code.value == 259:  # STILL_ACTIVE
                    return ProcessStatus.VIVO
                return ProcessStatus.MORTO_COMPROVADO
            return ProcessStatus.INCONCLUSIVO
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return ProcessStatus.VIVO
        except ProcessLookupError:
            return ProcessStatus.MORTO_COMPROVADO
        except PermissionError:
            # Processo existe no sistema, porém pertence a outro usuário -> VIVO
            return ProcessStatus.VIVO
        except OSError:
            return ProcessStatus.INCONCLUSIVO


def is_pid_alive(pid: Any) -> bool:
    """Verifica de forma segura se o PID está comprovadamente vivo no host."""
    return check_process_status(pid) == ProcessStatus.VIVO


@dataclass
class ExecutionRecord:
    execution_id: str
    mission_id: str
    issue: int
    status: str  # "INICIADO" | "EM_EXECUCAO" | "CANCELAMENTO_PENDENTE" | "APROVADO_AGUARDANDO_CH1" | "AGUARDANDO_PO" | "CANCELADO" | "BLOQUEADO_INFRA_OU_ESCOPO" | "ORCAMENTO_ESGOTADO" | "INTERROMPIDO_CRASH" | "ERRO"
    manifest_path: str
    worktree: str
    evidence_dir: str
    started_at: str
    timeout_seconds: int
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    returns_used: int = 0
    findings: list[str] = field(default_factory=list)
    codex_verdict: str | None = None
    patch: str | None = None
    report_markdown: str | None = None
    testes_log_tail: str | None = None
    decisao_po: dict[str, Any] | None = None

    def para_dicionario(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionService:
    """Gerencia execuções locais de missões CHDevFlow no host autorizado."""

    def __init__(
        self,
        data_dir: Path | None = None,
        labs_root: Path | None = None,
        cycle_runner: Callable[..., GenericResult] | None = None,
    ) -> None:
        self.data_dir = (data_dir or obter_diretorio_dados_seguro()).resolve()
        self.executions_dir = self.data_dir / "executions"
        self.executions_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock_file = self.data_dir / "active_execution.lock"
        self.labs_root = (labs_root or (Path.home() / "CHDevFlow-Labs")).resolve()
        self.cycle_runner = cycle_runner or run_generic_cycle

        self._lock = threading.RLock()
        self._active_execution_id: str | None = None
        self._cancel_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._memory_records: dict[str, ExecutionRecord] = {}

        # Recuperação segura no início: verifica se havia lock de crash anterior
        self._recover_stale_lock()

    def _recover_stale_lock(self) -> None:
        """Verifica e recupera de forma fail-closed um lock persistente deixado por crash/restart."""
        with self._lock:
            if not self.lock_file.exists():
                return
            try:
                raw_text = self.lock_file.read_text(encoding="utf-8")
                dados = json.loads(raw_text)
            except Exception:
                # Fail-closed estrito: se o lock estiver corrompido ou ilegível, não removemos cegamente
                return

            if not isinstance(dados, dict):
                return

            pid = dados.get("pid")
            exec_id = dados.get("execution_id")

            # Avalia status do processo dono do lock
            status_processo = check_process_status(pid)

            if status_processo == ProcessStatus.VIVO:
                # Processo comprovadamente vivo no host: preserva lock e assume ID ativo
                if exec_id:
                    self._active_execution_id = exec_id
                return

            if status_processo == ProcessStatus.INCONCLUSIVO:
                # Casos inconclusivos (ex: PID ausente, falha de acesso) permanecem bloqueados
                return

            # Apenas se status for estritamente MORTO_COMPROVADO podemos limpar o lock
            if status_processo == ProcessStatus.MORTO_COMPROVADO:
                if exec_id:
                    try:
                        registro_path = self.executions_dir / f"{exec_id}.json"
                        if registro_path.exists():
                            registro_dict = json.loads(registro_path.read_text(encoding="utf-8"))
                            if registro_dict.get("status") in ("INICIADO", "EM_EXECUCAO", "CANCELAMENTO_PENDENTE"):
                                registro_dict["status"] = "INTERROMPIDO_CRASH"
                                registro_dict["finished_at"] = datetime.now(timezone.utc).isoformat()
                                registro_dict["findings"] = registro_dict.get("findings", []) + [
                                    f"Servidor reiniciado ou processo comprovadamente morto (PID {pid} inativo)."
                                ]
                                registro_path.write_text(
                                    json.dumps(registro_dict, ensure_ascii=False, indent=2),
                                    encoding="utf-8",
                                )
                    except Exception:
                        pass

                try:
                    self.lock_file.unlink(missing_ok=True)
                except OSError:
                    pass

    def _clean_lock_file_if_owned(self, execution_id: str) -> None:
        """Remove o arquivo de lock apenas se ele pertencer à execução especificada."""
        if not self.lock_file.exists():
            return
        try:
            dados = json.loads(self.lock_file.read_text(encoding="utf-8"))
            if dados.get("execution_id") == execution_id:
                self.lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    def obter_execucao_ativa(self) -> dict[str, Any] | None:
        """Retorna os dados da execução atualmente ativa, se houver."""
        with self._lock:
            active_id = self._active_execution_id
        if not active_id:
            return None
        return self.obter_execucao(active_id)

    def obter_execucao(self, execution_id: str) -> dict[str, Any] | None:
        """Localiza e retorna os detalhes atualizados de uma execução."""
        with self._lock:
            # 1. Tenta recuperar da memória
            record = self._memory_records.get(execution_id)
            if record is None:
                # 2. Tenta carregar do disco
                registro_path = self.executions_dir / f"{execution_id}.json"
                if not registro_path.exists():
                    return None
                try:
                    dados = json.loads(registro_path.read_text(encoding="utf-8"))
                    record = ExecutionRecord(**dados)
                    self._memory_records[execution_id] = record
                except Exception:
                    return None

            if record.status == "CANCELAMENTO_PENDENTE":
                from chdevflow.core.local_executor import get_active_processes
                worker_thread = self._threads.get(execution_id)
                thread_viva = bool(worker_thread and worker_thread.is_alive())
                procs_restantes = get_active_processes(execution_id)
                if not thread_viva and not procs_restantes:
                    record.status = "CANCELADO"
                    if not record.finished_at:
                        record.finished_at = datetime.now(timezone.utc).isoformat()
                    aviso_concluido = "Encerramento de todos os subprocessos confirmado; exclusividade liberada."
                    if aviso_concluido not in record.findings:
                        record.findings.append(aviso_concluido)
                    if self._active_execution_id == execution_id:
                        self._active_execution_id = None
                    self._clean_lock_file_if_owned(execution_id)
                    self._persist_record(record)

        # 3. Enriquecimento a partir da pasta de dossiê, se disponível
        dados_retorno = record.para_dicionario()
        evidence_path = Path(record.evidence_dir)
        if evidence_path.is_dir():
            exec_json = evidence_path / "execucao.json"
            if exec_json.is_file():
                try:
                    detalhes = json.loads(exec_json.read_text(encoding="utf-8"))
                    # Atualiza status e tentativas se mais recentes
                    if record.status in ("INICIADO", "EM_EXECUCAO"):
                        dados_retorno["status"] = detalhes.get("status", record.status)
                    dados_retorno["attempts"] = detalhes.get("attempts", record.attempts)
                    dados_retorno["returns_used"] = detalhes.get("returns_used", record.returns_used)
                    dados_retorno["findings"] = [
                        sanitizar_log(f) for f in set(dados_retorno.get("findings", []) + detalhes.get("findings", []))
                    ]
                except Exception:
                    pass

            relatorio_md = evidence_path / "RELATORIO_COMPLETO_CH1.md"
            if relatorio_md.is_file():
                try:
                    dados_retorno["report_markdown"] = sanitizar_log(relatorio_md.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Procura o último patch e auditoria
            for num in range(3, 0, -1):
                attempt_dir = evidence_path / f"attempt-{num:02d}"
                if attempt_dir.is_dir():
                    patch_file = attempt_dir / "alteracoes.patch"
                    if patch_file.is_file() and not dados_retorno.get("patch"):
                        try:
                            dados_retorno["patch"] = sanitizar_log(patch_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    audit_file = attempt_dir / "auditoria_codex.md"
                    if audit_file.is_file() and not dados_retorno.get("codex_verdict"):
                        try:
                            texto_audit = audit_file.read_text(encoding="utf-8")
                            linhas = texto_audit.strip().splitlines()
                            if linhas:
                                dados_retorno["codex_verdict"] = linhas[0]
                        except Exception:
                            pass
                    test_log = attempt_dir / "testes.log"
                    if test_log.is_file() and not dados_retorno.get("testes_log_tail"):
                        try:
                            texto_testes = sanitizar_log(test_log.read_text(encoding="utf-8", errors="replace"))
                            dados_retorno["testes_log_tail"] = texto_testes[-4000:]
                        except Exception:
                            pass

        with self._lock:
            dados_retorno["is_active"] = (self._active_execution_id == execution_id)
        return dados_retorno

    def executar_missao(
        self,
        *,
        manifest_path: str | Path,
        confirmacao_po: bool,
        timeout_segundos: int = 480,
        isolated_tests: bool = False,
    ) -> dict[str, Any]:
        """Dispara uma nova execução local a partir de manifesto pré-preparado e validado."""
        # 1. Validação mandatória de confirmação explícita
        if confirmacao_po is not True:
            raise ManifestValidationError("Confirmação explícita de execução pelo PO é obrigatória e deve ser estritamente True.")

        # 2. Validação do timeout dentro dos limites do produto (120..900s)
        if not isinstance(timeout_segundos, int) or not MIN_TIMEOUT_TOTAL <= timeout_segundos <= MAX_TIMEOUT_TOTAL:
            raise ManifestValidationError(
                f"Timeout total deve estar entre {MIN_TIMEOUT_TOTAL} e {MAX_TIMEOUT_TOTAL} segundos."
            )

        # 3. Validação do arquivo de manifesto
        caminho_manifesto = Path(manifest_path).expanduser().absolute()
        if not caminho_manifesto.is_file() or caminho_manifesto.is_symlink():
            raise ManifestValidationError("Caminho do manifesto deve ser um arquivo regular existente.")
        if caminho_manifesto.suffix.lower() != ".json":
            raise ManifestValidationError("Manifesto deve ser um arquivo com extensão .json.")

        # 4. Executa preflight rigoroso de F6
        try:
            mission, root, target, prompt, snapshot = _preflight(caminho_manifesto)
        except Exception as exc:
            raise ManifestValidationError(f"Validação do manifesto/laboratório falhou: {sanitizar_log(str(exc))}") from exc

        # 5. Seção crítica de aquisição do lock de execução única (intra e inter-processos)
        with self._lock:
            if self._active_execution_id is not None:
                raise ExecutionConflictError(
                    f"Já existe uma missão ativa em execução (ID: {self._active_execution_id}). "
                    "Apenas uma execução é permitida simultaneamente."
                )

            execution_id = uuid4().hex

            # Prepara pasta de dossiê nova e isolada (fora da worktree)
            self.labs_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            evidence_dir = self.labs_root / f"CH-Dossie-{timestamp_str}-{execution_id[:8]}"

            # Aquisição atômica no sistema de arquivos via os.O_CREAT | os.O_EXCL
            # Garante exclusividade estrita mesmo entre múltiplos processos concorrentes
            lock_data = {
                "execution_id": execution_id,
                "mission_id": mission.mission_id,
                "pid": os.getpid(),
                "manifest_path": str(caminho_manifesto),
                "evidence_dir": str(evidence_dir),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "timeout_seconds": timeout_segundos,
            }
            lock_bytes = json.dumps(lock_data, ensure_ascii=False, indent=2).encode("utf-8")

            try:
                fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, lock_bytes)
                finally:
                    os.close(fd)
            except FileExistsError:
                raise ExecutionConflictError(
                    "Trava local detectada em disco. Aguarde ou recupere o estado antes de nova execução."
                )
            except OSError as exc:
                raise ExecutionConflictError(
                    f"Falha ao adquirir trava exclusiva em disco: {sanitizar_log(str(exc))}"
                )

            self._active_execution_id = execution_id
            cancel_event = threading.Event()
            self._cancel_events[execution_id] = cancel_event

            # Inicializa o registro de execução
            record = ExecutionRecord(
                execution_id=execution_id,
                mission_id=mission.mission_id,
                issue=mission.issue,
                status="INICIADO",
                manifest_path=str(caminho_manifesto),
                worktree=str(root),
                evidence_dir=str(evidence_dir),
                started_at=datetime.now(timezone.utc).isoformat(),
                timeout_seconds=timeout_segundos,
            )
            self._memory_records[execution_id] = record
            self._persist_record(record)

            # Inicia thread em segundo plano
            t = threading.Thread(
                target=self._run_thread,
                args=(record, caminho_manifesto, evidence_dir, timeout_segundos, isolated_tests, cancel_event),
                name=f"ch-exec-{execution_id[:8]}",
                daemon=True,
            )
            self._threads[execution_id] = t
            t.start()

            return record.para_dicionario()

    def _persist_record(self, record: ExecutionRecord) -> None:
        """Persiste o registro da execução atomicamente no disco."""
        path = self.executions_dir / f"{record.execution_id}.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(record.para_dicionario(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(path)

    def _run_thread(
        self,
        record: ExecutionRecord,
        manifest_path: Path,
        evidence_dir: Path,
        timeout: int,
        isolated_tests: bool,
        cancel_event: threading.Event,
    ) -> None:
        """Executa o ciclo em thread desacoplada respeitando timeout e cancelamento."""
        from chdevflow.core.local_executor import execution_context
        with execution_context(record.execution_id):
            start_mono = time.monotonic()
            record.status = "EM_EXECUCAO"
            self._persist_record(record)

            try:
                def cancel_check() -> bool:
                    return cancel_event.is_set()

                kwargs: dict[str, Any] = {
                    "manifest_path": manifest_path,
                    "evidence": evidence_dir,
                    "accepted": True,
                    "timeout": timeout,
                    "isolated_tests": isolated_tests,
                }
                if _runner_accepts_param(self.cycle_runner, "cancel_check"):
                    kwargs["cancel_check"] = cancel_check
                if _runner_accepts_param(self.cycle_runner, "execution_id"):
                    kwargs["execution_id"] = record.execution_id

                res = self.cycle_runner(**kwargs)
                record.elapsed_seconds = round(time.monotonic() - start_mono, 2)
                record.finished_at = datetime.now(timezone.utc).isoformat()
                if cancel_event.is_set():
                    record.status = "CANCELADO"
                    record.findings.append("Execução cancelada pelo operador.")
                else:
                    record.status = res.status
                    record.attempts = res.attempts
                    record.returns_used = res.returns_used
                    record.findings = [sanitizar_log(f) for f in res.findings]

            except Exception as exc:
                record.elapsed_seconds = round(time.monotonic() - start_mono, 2)
                record.finished_at = datetime.now(timezone.utc).isoformat()
                if cancel_event.is_set():
                    record.status = "CANCELADO"
                    record.findings.append("Execução cancelada pelo operador.")
                else:
                    record.status = "BLOQUEADO_INFRA_OU_ESCOPO"
                    record.findings.append(f"Falha de execução: {sanitizar_log(str(exc))}")
            finally:
                from chdevflow.core.local_executor import get_active_processes
                procs_restantes = get_active_processes(record.execution_id)
                with self._lock:
                    if procs_restantes:
                        # Incerteza / subprocessos ainda ativos: NÃO libera lock nem exclusividade!
                        record.status = "CANCELAMENTO_PENDENTE"
                        pids = [p.pid for p in procs_restantes]
                        aviso = (
                            f"Encerramento inconclusivo: {len(procs_restantes)} subprocesso(s) ainda ativo(s) "
                            f"no host (PID(s): {pids}). Exclusividade e lock mantidos."
                        )
                        if aviso not in record.findings:
                            record.findings.append(aviso)
                    else:
                        if cancel_event.is_set():
                            record.status = "CANCELADO"
                            if not record.finished_at:
                                record.finished_at = datetime.now(timezone.utc).isoformat()
                            if "Execução cancelada pelo operador." not in record.findings:
                                record.findings.append("Execução cancelada pelo operador.")

                        if self._active_execution_id == record.execution_id:
                            self._active_execution_id = None
                        self._clean_lock_file_if_owned(record.execution_id)
                    self._persist_record(record)

    def cancelar_execucao(self, execution_id: str, join_timeout: float = 5.0) -> dict[str, Any]:
        """Cancela uma execução em andamento e interrompe todos os seus subprocessos."""
        with self._lock:
            record = self._memory_records.get(execution_id)
            if not record:
                registro_path = self.executions_dir / f"{execution_id}.json"
                if not registro_path.exists():
                    raise ExecutionNotFoundError(f"Execução '{execution_id}' não encontrada.")
                record = ExecutionRecord(**json.loads(registro_path.read_text(encoding="utf-8")))

            # Se já estiver em estado terminal e sem processos ativos, não há o que cancelar
            if record.status in ("CONCLUIDO", "BLOQUEADO_INFRA_OU_ESCOPO", "REPROVADO_CH1"):
                return record.para_dicionario()
            if record.status == "CANCELADO":
                from chdevflow.core.local_executor import get_active_processes
                if not get_active_processes(execution_id):
                    return record.para_dicionario()

            cancel_event = self._cancel_events.get(execution_id)
            if cancel_event:
                cancel_event.set()

            worker_thread = self._threads.get(execution_id)

        # Interrompe efetivamente APENAS os subprocessos da execução solicitada
        terminate_all_active_processes(execution_id=execution_id)

        # Aguarda o término efetivo da thread do worker para evitar condição de corrida
        if worker_thread and worker_thread.is_alive() and worker_thread != threading.current_thread():
            worker_thread.join(timeout=join_timeout)

        from chdevflow.core.local_executor import get_active_processes
        procs_restantes = get_active_processes(execution_id)

        with self._lock:
            if (worker_thread and worker_thread.is_alive()) or procs_restantes:
                # A worker thread ainda está viva ou ainda há subprocessos vivos no host!
                # Mantém o lock e status não-terminal CANCELAMENTO_PENDENTE
                record.status = "CANCELAMENTO_PENDENTE"
                if procs_restantes:
                    pids = [p.pid for p in procs_restantes]
                    aviso = (
                        f"Cancelamento inconclusivo: {len(procs_restantes)} subprocesso(s) ainda ativo(s) "
                        f"no host (PID(s): {pids}). Exclusividade e lock mantidos."
                    )
                else:
                    aviso = "Cancelamento solicitado pelo operador; aguardando encerramento da worker thread."
                if aviso not in record.findings:
                    record.findings.append(aviso)
                self._persist_record(record)
                return record.para_dicionario()

            record.status = "CANCELADO"
            if not record.finished_at:
                record.finished_at = datetime.now(timezone.utc).isoformat()
            if "Execução cancelada a pedido do operador." not in record.findings:
                record.findings.append("Execução cancelada a pedido do operador.")

            if self._active_execution_id == execution_id:
                self._active_execution_id = None
            self._clean_lock_file_if_owned(execution_id)
            self._persist_record(record)
            return record.para_dicionario()

    def registrar_decisao_po(
        self,
        execution_id: str,
        decisao: str,
        justificativa: str | None = None,
    ) -> dict[str, Any]:
        """Registra formalmente a decisão do PO sobre uma execução concluída."""
        decisao_normalizada = decisao.strip().upper()
        if decisao_normalizada not in ("APROVADO", "REPROVADO", "AJUSTES"):
            raise ValueError(
                f"Decisão inválida: '{decisao}'. Opções permitidas: APROVADO, REPROVADO, AJUSTES."
            )

        with self._lock:
            record = self._memory_records.get(execution_id)
            if not record:
                registro_path = self.executions_dir / f"{execution_id}.json"
                if not registro_path.exists():
                    raise ExecutionNotFoundError(f"Execução '{execution_id}' não encontrada.")
                record = ExecutionRecord(**json.loads(registro_path.read_text(encoding="utf-8")))

            # Validação do status atual da execução
            if record.status in ("INICIADO", "EM_EXECUCAO", "CANCELAMENTO_PENDENTE"):
                raise ValueError(
                    f"Não é permitido registrar decisão em execução ainda em andamento (status: '{record.status}'). "
                    "Aguarde o término do ciclo ou a conclusão do cancelamento."
                )

            if decisao_normalizada == "APROVADO" and record.status not in ("APROVADO_AGUARDANDO_CH1", "AGUARDANDO_PO"):
                raise ValueError(
                    f"Não é permitido aprovar execução com status '{record.status}'. "
                    "Apenas execuções concluídas com sucesso (APROVADO_AGUARDANDO_CH1 ou AGUARDANDO_PO) são elegíveis para aprovação."
                )

            dados_decisao = {
                "tipo": "decisao_local_declarada",
                "decisao": decisao_normalizada,
                "justificativa": sanitizar_log(justificativa or "").strip(),
                "registrado_em": datetime.now(timezone.utc).isoformat(),
                "aviso": "Decisão local declarada pelo operador. Não substitui homologação formal do PO nem auditoria independente do Codex.",
            }
            record.decisao_po = dados_decisao
            self._persist_record(record)

        # Se houver pasta de dossiê, registra arquivo decisao_po.json e aponta no relatório
        evidence_path = Path(record.evidence_dir)
        if evidence_path.is_dir():
            decisao_file = evidence_path / "decisao_po.json"
            try:
                decisao_file.write_text(
                    json.dumps(dados_decisao, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
            relatorio_md = evidence_path / "RELATORIO_COMPLETO_CH1.md"
            if relatorio_md.is_file():
                try:
                    conteudo = relatorio_md.read_text(encoding="utf-8")
                    novo_bloco = (
                        f"\n## Decisão Local Declarada pelo PO\n- Tipo: **decisao_local_declarada**\n"
                        f"- Decisão: **{decisao_normalizada}**\n"
                        f"- Justificativa: {dados_decisao['justificativa'] or 'Nenhuma'}\n"
                        f"- Registrado em: {dados_decisao['registrado_em']}\n"
                        f"- Aviso: {dados_decisao['aviso']}\n"
                    )
                    relatorio_md.write_text(conteudo + novo_bloco, encoding="utf-8")
                except Exception:
                    pass

        return record.para_dicionario()
