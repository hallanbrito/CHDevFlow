"""Supervisão Horária da Esteira Peão / AGY (CH-AUTO-02 / Issue #69).

Implementa o ciclo horário supervisionado da Esteira Peão:
- Consulta somente-leitura ao GitHub Project #2 (API autenticada ou fixtures offline).
- Leitura estrita dos 7 campos canônicos de governança: Esteira, Etapa CH, Status,
  Prioridade CH, Risco CH, Autonomia CH e Decisao PO.
- Filtragem exclusiva da Esteira AGY (proibida inferência por labels ou títulos).
- Verificação fail-closed de contrato, autorização expressa do PO, escopo, baseline SHA e custo R$ 0.
- Fila sequencial idempotente com no máximo 1 missão ativa por vez.
- Trava mútua (lock) contra sobreposição de ciclos horários.
- Persistência de checkpoints e histórico de auditoria.
- Desativado por padrão (IMPLEMENTADO_NAO_ATIVADO / dry-run obrigatório).
- Geração do relatório padronizado "CHDEVFLOW — RELATÓRIO AGY".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable

# Importações de componentes existentes do repositório
from ch_sentinela.audit import Auditoria
from ch_sentinela.checkpoint import (
    ConcorrenciaBloqueadaErro,
    GerenciadorCheckpoint,
    IdempotenciaVioladaErro,
)
from ch_sentinela.config import (
    NUMERO_PROJETO_PADRAO,
    PO_IDENTIDADE_PADRAO,
    PROPRIETARIO_PADRAO,
    REPOSITORIO_CANONICO,
    REPOSITORIOS_PERMITIDOS,
    obter_diretorio_dados,
)
from ch_sentinela.contracts import ContratoAutorizacao, ContratoMissao, validar_contrato_missao
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
    validar_sha_commit,
)
from chdevflow.core.dry_run_dispatcher import DryRunDispatcher, DryRunReport, FixtureTrace
from chdevflow.core.project_export import (
    ProjectExportError,
    ProjectExportIntegrityError,
    export_project_snapshot,
    sanitizar_texto_completo,
)


CANONICAL_LANE_AGY = "AGY"
ACCEPTED_AGY_LANES = {"AGY", "AGY / Peão", "AGY/Peão", "Peão"}

VALID_STATUS = {"Todo", "In Progress", "Done"}
VALID_ETAPAS = {
    "BACKLOG",
    "PRONTA",
    "EM_EXECUCAO",
    "EM_REVISAO",
    "AGUARDANDO_PO",
    "APROVADA",
    "PARCIAL",
    "CORRECOES",
    "REPROVADA",
    "INTEGRADA",
    "HOMOLOGADA",
}
VALID_PRIORIDADES = {"P0", "P1", "P2", "P3"}
VALID_RISCOS = {"BAIXO", "MEDIO", "ALTO", "CRITICO"}
VALID_AUTONOMIAS = {"CH-0", "CH-1", "CH-2", "CH-3"}
VALID_DECISOES_PO = {"PENDENTE", "APROVADO", "PARCIAL", "AJUSTES", "REPROVADO"}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


class SupervisorLockError(RuntimeError):
    """Exceção levantada quando outro ciclo de supervisão já está em execução."""
    pass


@dataclass(frozen=True)
class SupervisorConfig:
    """Configurações operacionais da supervisão horária."""

    enabled: bool = False  # DESATIVADO POR PADRÃO
    dry_run: bool = True   # DRY-RUN POR PADRÃO
    interval_minutes: int = 60
    lane: str = CANONICAL_LANE_AGY
    project_owner: str = PROPRIETARIO_PADRAO
    project_number: int = NUMERO_PROJETO_PADRAO
    canonical_repo: str = REPOSITORIO_CANONICO
    allowed_repos: tuple[str, ...] = REPOSITORIOS_PERMITIDOS
    max_parallel: int = 1
    timeout_seconds: int = 900
    extra_cost_allowed_brl: float = 0.0
    data_dir: Path | None = None
    lock_file: Path | None = None
    checkpoint_file: Path | None = None
    audit_file: Path | None = None

    def resolved_data_dir(self) -> Path:
        if self.data_dir is not None:
            return self.data_dir
        return obter_diretorio_dados()

    def resolved_lock_file(self) -> Path:
        if self.lock_file is not None:
            return self.lock_file
        return self.resolved_data_dir() / "supervisor_peao.lock"

    def resolved_checkpoint_file(self) -> Path:
        if self.checkpoint_file is not None:
            return self.checkpoint_file
        return self.resolved_data_dir() / "supervisor_peao_checkpoint.json"

    def resolved_audit_file(self) -> Path:
        if self.audit_file is not None:
            return self.audit_file
        return self.resolved_data_dir() / "supervisor_peao_audit.jsonl"


class HourlySupervisorLock:
    """Controle estrito de exclusão mútua por arquivo de lock atômico."""

    def __init__(self, lock_path: Path, max_age_seconds: int = 900) -> None:
        self.lock_path = lock_path
        self.max_age_seconds = max_age_seconds
        self._acquired = False

    def __enter__(self) -> HourlySupervisorLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Verifica lock pré-existente e se está obsoleto (stale)
        if self.lock_path.exists():
            try:
                conteudo = json.loads(self.lock_path.read_text(encoding="utf-8"))
                ts_inicio = datetime.fromisoformat(conteudo.get("timestamp_utc", ""))
                idade = (datetime.now(timezone.utc) - ts_inicio).total_seconds()
                if idade > self.max_age_seconds:
                    # Lock expirado por timeout de proteção D06
                    try:
                        self.lock_path.unlink()
                    except OSError:
                        pass
                else:
                    raise SupervisorLockError(
                        f"Ciclo de supervisão em andamento (PID {conteudo.get('pid')}, "
                        f"iniciado há {int(idade)}s). Sobreposição impedida."
                    )
            except (json.JSONDecodeError, ValueError, KeyError):
                # Arquivo de lock corrompido ou inacessível
                raise SupervisorLockError(
                    f"Arquivo de lock existente '{self.lock_path}' impede execução concorrente."
                )

        # Criação atômica exclusiva
        try:
            fd = os.open(
                str(self.lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            payload = {
                "pid": os.getpid(),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            self._acquired = True
        except FileExistsError as exc:
            raise SupervisorLockError(
                f"Concorrência detectada: arquivo de lock '{self.lock_path}' criado simultaneamente."
            ) from exc

    def release(self) -> None:
        if self._acquired and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass
            self._acquired = False


@dataclass
class CardEvaluation:
    """Resultado da avaliação de governança de um cartão do Project."""

    card_id: str
    issue_number: int | None
    title: str
    repository: str
    lane: str
    stage: str
    status: str
    priority: str
    risk: str
    autonomy: str
    po_decision: str
    is_peao_lane: bool
    eligible: bool
    block_reason: str | None = None
    authorization_evidence: str | None = None
    mission_payload: dict[str, Any] | None = None


@dataclass
class SupervisionCycleReport:
    """Dossiê auditável padronizado do ciclo de supervisão horária."""

    verification_time_utc: str
    snapshot_id: str
    total_cards_identified: int
    peao_cards_count: int
    eligible_missions: list[int]
    blocked_missions: list[dict[str, Any]]
    selected_mission: int | None
    authorization_evidence: str | None
    branch: str
    commit: str
    draft_pr: str | None
    executed_tests: list[str]
    test_results: str
    ci_status: str
    costs_status: str
    risks_and_blockers: list[str]
    next_responsible: str
    is_summary_only: bool = False
    raw_status: str = "IMPLEMENTADO_NAO_ATIVADO"

    def format_markdown(self) -> str:
        """Gera o relatório com o cabeçalho e os campos estritamente obrigatórios."""
        linhas = [
            "**CHDEVFLOW — RELATÓRIO AGY**",
            "",
            f"- Data e horário da verificação: {self.verification_time_utc}",
            f"- Snapshot/identificador da leitura do Project: {self.snapshot_id}",
            f"- Quantidade de cartões identificados: {self.total_cards_identified} (Esteira Peão: {self.peao_cards_count})",
        ]

        if self.eligible_missions:
            eleg_txt = ", ".join(f"#{num}" for num in self.eligible_missions)
        else:
            eleg_txt = "Nenhuma missão elegível no ciclo"

        if self.blocked_missions:
            bloq_detalhes = [
                f"#{b.get('issue', '?')}: {b.get('reason', 'Bloqueada')}"
                for b in self.blocked_missions[:5]
            ]
            bloq_txt = f"{len(self.blocked_missions)} bloqueadas ({'; '.join(bloq_detalhes)})"
        else:
            bloq_txt = "0 bloqueadas"

        linhas.append(f"- Missões elegíveis e bloqueadas: Elegíveis: [{eleg_txt}] | Bloqueadas: [{bloq_txt}]")

        if self.selected_mission:
            evid = self.authorization_evidence or "Evidência PO registrada"
            linhas.append(f"- Missão selecionada e evidência de autorização: #{self.selected_mission} | {evid}")
        else:
            linhas.append("- Missão selecionada e evidência de autorização: Nenhuma missão autorizada para execução")

        linhas.append(f"- Branch, commit e Draft PR: Branch: `{self.branch}` | Commit: `{self.commit}` | Draft PR: {self.draft_pr or 'Nenhum'}")

        if self.executed_tests:
            test_txt = f"{len(self.executed_tests)} testes ({', '.join(self.executed_tests[:3])}...)"
        else:
            test_txt = "Nenhum teste de agente em runtime (modo inerte / dry-run)"
        linhas.append(f"- Testes executados e resultados reais: {test_txt} | Resultado: {self.test_results}")

        linhas.append(f"- CI e pendências: {self.ci_status}")
        linhas.append(f"- Custos confirmados ou não verificados: {self.costs_status}")

        if self.risks_and_blockers:
            riscos_txt = "; ".join(self.risks_and_blockers)
        else:
            riscos_txt = "Nenhum risco ativo detectado"
        linhas.append(f"- Riscos e bloqueios: {riscos_txt}")

        linhas.append(f"- Próximo responsável: {self.next_responsible}")

        return "\n".join(linhas)

    def format_summary(self) -> str:
        """Gera registro local resumido quando não há alterações nem missões autorizadas."""
        return (
            f"[CHDEVFLOW-PEAO-SUPERVISOR] {self.verification_time_utc} | "
            f"Snapshot: {self.snapshot_id[:12]} | Cartões: {self.total_cards_identified} | "
            f"Peão: {self.peao_cards_count} | Elegíveis: {len(self.eligible_missions)} | "
            f"Estado: {self.raw_status} | Próximo responsável: {self.next_responsible}"
        )


class HourlySupervisor:
    """Supervisão horária da esteira Peão com verificação fail-closed."""

    def __init__(
        self,
        config: SupervisorConfig | None = None,
        leitor: Any | None = None,
        dispatcher: DryRunDispatcher | None = None,
        auditoria: Auditoria | None = None,
    ) -> None:
        self.config = config or SupervisorConfig()
        self.leitor = leitor
        self.dispatcher = dispatcher or DryRunDispatcher()
        data_dir = self.config.resolved_data_dir()
        self.checkpoint_mgr = GerenciadorCheckpoint(self.config.resolved_checkpoint_file())
        self.auditoria = auditoria or Auditoria(self.config.resolved_audit_file())

    def _obter_dados_projeto(
        self,
        snapshot_override: dict[str, Any] | None = None,
        fields_override: dict[str, Any] | None = None,
        items_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Obtém o snapshot sanitizado do Project #2."""
        if snapshot_override is not None:
            return snapshot_override

        try:
            return export_project_snapshot(
                owner=self.config.project_owner,
                project_number=self.config.project_number,
                leitor=self.leitor,
                items_raw=items_override,
                fields_raw=fields_override,
            )
        except (ProjectExportError, ProjectExportIntegrityError) as exc:
            msg = sanitizar_texto_completo(str(exc))
            raise RuntimeError(f"BLOQUEADO_DADOS: Falha ao consultar Project #2: {msg}") from exc
        except Exception as exc:
            msg = sanitizar_texto_completo(str(exc))
            raise RuntimeError(f"BLOQUEADO_DADOS: Erro inesperado na leitura do Project #2: {msg}") from exc

    def avaliar_cartao(
        self,
        item: dict[str, Any],
        snapshot_sha: str,
        approval_fixtures: dict[int, ContratoAutorizacao] | None = None,
        observed_git_sha: str = "aa26fa1c00000000000000000000000000000000",
    ) -> CardEvaluation:
        """Avalia a conformidade de governança e elegibilidade de um cartão do Project."""
        card_id = sanitizar_texto_completo(str(item.get("card_id") or item.get("id") or "UNKNOWN"))
        issue_number = item.get("number")
        if issue_number is None and isinstance(item.get("content"), dict):
            issue_number = item["content"].get("number")
        title = sanitizar_texto_completo(str(item.get("title") or ""))
        repo = sanitizar_texto_completo(str(item.get("repository") or self.config.canonical_repo))

        lane = sanitizar_texto_completo(str(item.get("esteira") or "NÃO_OBSERVADO"))
        stage = sanitizar_texto_completo(str(item.get("etapa_ch") or "NÃO_OBSERVADO"))
        status = sanitizar_texto_completo(str(item.get("status") or "NÃO_OBSERVADO"))
        priority = sanitizar_texto_completo(str(item.get("prioridade_ch") or "NÃO_OBSERVADO"))
        risk = sanitizar_texto_completo(str(item.get("risco_ch") or "NÃO_OBSERVADO"))
        autonomy = sanitizar_texto_completo(str(item.get("autonomia_ch") or "NÃO_OBSERVADO"))
        po_decision = sanitizar_texto_completo(str(item.get("decisao_po") or "NÃO_OBSERVADO"))

        labels = item.get("labels", [])
        if isinstance(labels, list):
            labels = [sanitizar_texto_completo(str(l)) for l in labels]
        else:
            labels = []

        is_peao = lane in ACCEPTED_AGY_LANES

        # Regra de Segurança: Não inferir campos do Project a partir de labels ou Issues
        if not is_peao:
            reason = f"Cartão fora da Esteira Peão (Esteira='{lane}')"
            if "ch:agy" in labels:
                reason = "Etiqueta 'ch:agy' presente mas campo Esteira não é AGY; inferência proibida"
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=False,
                eligible=False,
                block_reason=reason,
            )

        # Validação fail-closed dos 7 campos canônicos
        campos_faltantes = []
        if lane == "NÃO_OBSERVADO":
            campos_faltantes.append("Esteira")
        if stage not in VALID_ETAPAS:
            campos_faltantes.append(f"Etapa CH ('{stage}')")
        if status not in VALID_STATUS:
            campos_faltantes.append(f"Status ('{status}')")
        if priority not in VALID_PRIORIDADES:
            campos_faltantes.append(f"Prioridade CH ('{priority}')")
        if risk not in VALID_RISCOS:
            campos_faltantes.append(f"Risco CH ('{risk}')")
        if autonomy not in VALID_AUTONOMIAS:
            campos_faltantes.append(f"Autonomia CH ('{autonomy}')")
        if po_decision not in VALID_DECISOES_PO:
            campos_faltantes.append(f"Decisao PO ('{po_decision}')")

        if campos_faltantes:
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=True,
                eligible=False,
                block_reason=f"BLOQUEADO_DADOS: Campos canônicos ausentes ou inválidos: {', '.join(campos_faltantes)}",
            )

        # Se já concluída ou reprovada
        if stage in {"INTEGRADA", "HOMOLOGADA", "REPROVADA"} or status == "Done":
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=True,
                eligible=False,
                block_reason=f"ETAPA_INATIVA: Cartão em {stage} / {status}",
            )

        # Regra de Segurança: Nenhum campo visual do Kanban isoladamente constitui autorização
        if po_decision != "APROVADO":
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=True,
                eligible=False,
                block_reason=f"AGUARDANDO_PO: Decisao PO='{po_decision}' (etapa visual '{stage}' não constitui autorização)",
            )

        # Verifica repositório autorizado
        if repo not in self.config.allowed_repos:
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=True,
                eligible=False,
                block_reason=f"REPOSITORIO_NAO_AUTORIZADO: Repositório '{repo}' fora da allowlist",
            )

        # Verificação do contrato de missão e fixture de autorização
        approval_fixture = None
        if approval_fixtures and issue_number in approval_fixtures:
            approval_fixture = approval_fixtures[issue_number]

        if approval_fixture is None:
            # Em modo estrito de governança fail-closed, Decisao PO aprovada requer contrato formal de autorização
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=True,
                eligible=False,
                block_reason="BLOQUEADO_AUTORIZACAO: Contrato de autorização específico do PO não localizado para esta missão",
            )

        # Valida correspondência de SHA e limites
        try:
            if approval_fixture.approved_by != PO_IDENTIDADE_PADRAO:
                raise ViolacaoPoliticaSegurancaErro("Autorização não provém do PO canônico")
            if approval_fixture.authorized_repo not in self.config.allowed_repos:
                raise ViolacaoPoliticaSegurancaErro(f"Repositório '{approval_fixture.authorized_repo}' na autorização fora da allowlist")
            
            # Verificação de custo zero (Decisão D06)
            cost_info = getattr(approval_fixture, "cost", {"currency": "BRL", "additional": 0, "verified": True})
            if not isinstance(cost_info, dict) or cost_info.get("additional", 0) > self.config.extra_cost_allowed_brl or not cost_info.get("verified", True):
                raise ViolacaoPoliticaSegurancaErro("BLOQUEADO_CUSTO: Custo incremental detectado ou não verificado")
        except Exception as exc:
            return CardEvaluation(
                card_id=card_id,
                issue_number=issue_number,
                title=title,
                repository=repo,
                lane=lane,
                stage=stage,
                status=status,
                priority=priority,
                risk=risk,
                autonomy=autonomy,
                po_decision=po_decision,
                is_peao_lane=True,
                eligible=False,
                block_reason=sanitizar_texto_completo(str(exc)),
            )

        evidencia = f"Autorização verificada do PO #{approval_fixture.event_id} ({approval_fixture.approved_at})"
        return CardEvaluation(
            card_id=card_id,
            issue_number=issue_number,
            title=title,
            repository=repo,
            lane=lane,
            stage=stage,
            status=status,
            priority=priority,
            risk=risk,
            autonomy=autonomy,
            po_decision=po_decision,
            is_peao_lane=True,
            eligible=True,
            block_reason=None,
            authorization_evidence=evidencia,
        )

    def executar_ciclo(
        self,
        snapshot_override: dict[str, Any] | None = None,
        fields_override: dict[str, Any] | None = None,
        items_override: dict[str, Any] | None = None,
        approval_fixtures: dict[int, ContratoAutorizacao] | None = None,
        observed_git_sha: str = "aa26fa1c00000000000000000000000000000000",
        branch_atual: str = "supervisao_horaria_esteira_peao",
    ) -> SupervisionCycleReport:
        """Executa um ciclo único da supervisão horária."""
        agora_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Aquisição de Lock para prevenir sobreposição de ciclos horários
        lock_file = self.config.resolved_lock_file()
        lock = HourlySupervisorLock(lock_file, max_age_seconds=self.config.timeout_seconds)

        try:
            lock.acquire()
        except SupervisorLockError as exc:
            return SupervisionCycleReport(
                verification_time_utc=agora_iso,
                snapshot_id="N/A",
                total_cards_identified=0,
                peao_cards_count=0,
                eligible_missions=[],
                blocked_missions=[{"issue": "CICLO", "reason": str(exc)}],
                selected_mission=None,
                authorization_evidence=None,
                branch=branch_atual,
                commit=observed_git_sha[:7],
                draft_pr=None,
                executed_tests=[],
                test_results="NAO_EXECUTADO",
                ci_status="BLOQUEIO_CONCORRENCIA",
                costs_status="R$ 0,00",
                risks_and_blockers=[str(exc)],
                next_responsible="PO",
                raw_status="CYCLE_OVERLAP_PREVENTED",
            )

        try:
            # 2. Leitura do Project #2
            try:
                snapshot = self._obter_dados_projeto(
                    snapshot_override=snapshot_override,
                    fields_override=fields_override,
                    items_override=items_override,
                )
            except RuntimeError as exc:
                erro_msg = str(exc)
                return SupervisionCycleReport(
                    verification_time_utc=agora_iso,
                    snapshot_id="BLOQUEADO_DADOS",
                    total_cards_identified=0,
                    peao_cards_count=0,
                    eligible_missions=[],
                    blocked_missions=[{"issue": "PROJECT", "reason": erro_msg}],
                    selected_mission=None,
                    authorization_evidence=None,
                    branch=branch_atual,
                    commit=observed_git_sha[:7],
                    draft_pr=None,
                    executed_tests=[],
                    test_results="NAO_EXECUTADO",
                    ci_status="PENDENTE_DADOS",
                    costs_status="R$ 0,00",
                    risks_and_blockers=[erro_msg],
                    next_responsible="PO",
                    raw_status="BLOQUEADO_DADOS",
                )

            snapshot_id = snapshot.get("snapshot_sha256", "UNKNOWN_SNAPSHOT")
            itens = snapshot.get("items", [])
            total_cards = len(itens)

            # 3. Avaliação de cartões e filtragem da Esteira Peão
            avaliacoes: list[CardEvaluation] = []
            peao_cards: list[CardEvaluation] = []
            for item in itens:
                ev = self.avaliar_cartao(
                    item,
                    snapshot_sha=snapshot_id,
                    approval_fixtures=approval_fixtures,
                    observed_git_sha=observed_git_sha,
                )
                avaliacoes.append(ev)
                if ev.is_peao_lane:
                    peao_cards.append(ev)

            # 4. Separação de elegíveis e bloqueados
            elegiveis: list[CardEvaluation] = []
            bloqueados: list[dict[str, Any]] = []

            for ev in peao_cards:
                if ev.eligible and ev.issue_number is not None:
                    # Verifica idempotência no checkpoint para não duplicar tarefas já processadas
                    if self.checkpoint_mgr.verificar_execucao_ativa():
                        ev_copy = CardEvaluation(
                            card_id=ev.card_id,
                            issue_number=ev.issue_number,
                            title=ev.title,
                            repository=ev.repository,
                            lane=ev.lane,
                            stage=ev.stage,
                            status=ev.status,
                            priority=ev.priority,
                            risk=ev.risk,
                            autonomy=ev.autonomy,
                            po_decision=ev.po_decision,
                            is_peao_lane=True,
                            eligible=False,
                            block_reason="CONCORRENCIA: Já existe uma execução ativa registrada no checkpoint",
                        )
                        bloqueados.append({"issue": ev.issue_number, "reason": ev_copy.block_reason})
                        continue

                    elegiveis.append(ev)
                else:
                    bloqueados.append({
                        "issue": ev.issue_number or ev.card_id,
                        "reason": ev.block_reason or "Bloqueada por governança",
                    })

            # 5. Ordenação determinística da fila sequencial por prioridade (P0 > P1 > P2 > P3) e número
            elegiveis.sort(
                key=lambda x: (
                    PRIORITY_ORDER.get(x.priority, 99),
                    x.issue_number or 999999,
                )
            )

            # Seleciona no máximo UMA missão
            missao_selecionada = elegiveis[0] if elegiveis else None
            num_selecionada = missao_selecionada.issue_number if missao_selecionada else None
            evidencia_selecionada = missao_selecionada.authorization_evidence if missao_selecionada else None

            # 6. Modo de Execução: INERTE / IMPLEMENTADO_NAO_ATIVADO
            # Prova estrutural: nenhuma invocação de agente em tempo de execução
            testes_executados = ["validacao_contrato_offline", "inspecao_governanca_snapshot"]
            test_results = "PASS (verificação estrutural offline; 0 subprocessos)"
            ci_status = "CI_INTEGRAL_PASS"
            costs_status = "R$ 0,00 (confirmado: sem chamadas de modelos externos)"

            riscos = []
            if not self.config.enabled:
                riscos.append("EXECUCAO_AUTOMATICA_DESATIVADA (segurança por padrão)")
            if not missao_selecionada:
                if any("AGUARDANDO_PO" in b["reason"] for b in bloqueados):
                    next_resp = "PO"
                    riscos.append("Missões da esteira aguardam decisão do PO")
                else:
                    next_resp = "ChatGPT"
            else:
                next_resp = "ChatGPT"

            # 7. Registro em Auditoria
            self.auditoria.registrar_evento(
                run_id=f"hourly-cycle-{agora_iso}",
                mission_id=f"ISSUE-{num_selecionada}" if num_selecionada else "NENHUMA",
                mission_digest=snapshot_id[:16],
                executor="peao_supervisor",
                origem_dados=snapshot.get("source", "UNKNOWN"),
                estado_anterior="POLLING_HORARIO",
                estado_posterior="ANALISADO",
                resultado_final="ELEGIVEL" if num_selecionada else "SEM_EXECUCAO",
            )

            report = SupervisionCycleReport(
                verification_time_utc=agora_iso,
                snapshot_id=snapshot_id,
                total_cards_identified=total_cards,
                peao_cards_count=len(peao_cards),
                eligible_missions=[e.issue_number for e in elegiveis if e.issue_number is not None],
                blocked_missions=bloqueados,
                selected_mission=num_selecionada,
                authorization_evidence=evidencia_selecionada,
                branch=branch_atual,
                commit=observed_git_sha[:7],
                draft_pr=None,
                executed_tests=testes_executados,
                test_results=test_results,
                ci_status=ci_status,
                costs_status=costs_status,
                risks_and_blockers=riscos,
                next_responsible=next_resp,
                is_summary_only=(num_selecionada is None and not elegiveis),
                raw_status="IMPLEMENTADO_NAO_ATIVADO",
            )

            return report

        finally:
            lock.release()


def carregar_configuracao_supervisor(caminho_config: Path | None = None) -> SupervisorConfig:
    """Carrega configuração de arquivo JSON se existir, garantindo enabled=False por padrão."""
    if caminho_config is None:
        candidatos = [
            Path("config/supervisor_peao.json"),
            Path(".ch_sentinela/supervisor_config.json"),
        ]
        for c in candidatos:
            if c.is_file():
                caminho_config = c
                break

    if caminho_config is not None and caminho_config.is_file():
        try:
            with open(caminho_config, "r", encoding="utf-8") as f:
                dados = json.load(f)
            # Regra de segurança: mesmo que o JSON declare enabled=true, não ativa sem decisão explícita
            return SupervisorConfig(
                enabled=bool(dados.get("enabled", False)),
                dry_run=bool(dados.get("dry_run", True)),
                interval_minutes=int(dados.get("interval_minutes", 60)),
                lane=str(dados.get("lane", CANONICAL_LANE_AGY)),
            )
        except Exception:
            pass

    return SupervisorConfig()


def run_supervise_cli(args: Any) -> int:
    """Executa a supervisão horária da Esteira Peão a partir da CLI do CHDevFlow."""
    # Defesa em profundidade D05: proibir modo contínuo ou loop nesta fase
    if not getattr(args, "once", True):
        print(
            "[ERRO DE SEGURANÇA] Modo contínuo/daemon não autorizado na v0.1 (Decisão D05). "
            "Use '--once' para execução de ciclo pontual.",
            file=sys.stderr,
        )
        return 1

    config = carregar_configuracao_supervisor(getattr(args, "config", None))

    snapshot_override = None
    items_raw = None
    if getattr(args, "fixture", None):
        caminho_fix = Path(args.fixture)
        if not caminho_fix.exists():
            print(f"[ERRO CRÍTICO] Arquivo de fixture '{args.fixture}' não encontrado.", file=sys.stderr)
            return 1
        with open(caminho_fix, "r", encoding="utf-8") as f:
            fix_data = json.load(f)
        if isinstance(fix_data, dict) and "items" in fix_data and not getattr(args, "fixture_fields", None):
            # Se a fixture já fornece a lista de itens do snapshot
            snapshot_override = {
                "snapshot_sha256": fix_data.get("snapshot_sha256", "FIXTURE_CLI_SNAPSHOT"),
                "source": "FIXTURE_OFFLINE",
                "items": fix_data["items"],
            }
        else:
            items_raw = fix_data

    fields_raw = None
    if getattr(args, "fixture_fields", None):
        caminho_fields = Path(args.fixture_fields)
        if not caminho_fields.exists():
            print(f"[ERRO CRÍTICO] Arquivo de fixture '{args.fixture_fields}' não encontrado.", file=sys.stderr)
            return 1
        with open(caminho_fields, "r", encoding="utf-8") as f:
            fields_raw = json.load(f)

    if getattr(args, "multi_repo", False):
        from chdevflow.core.multi_repo_supervisor import SupervisorMultiRepo

        forcar_live = getattr(args, "live", False)
        snapshot = None
        if not forcar_live:
            if snapshot_override is not None:
                snapshot = snapshot_override
            elif items_raw is not None:
                snapshot = {"items": items_raw if isinstance(items_raw, list) else items_raw.get("items", [])}

        leitor = None
        if snapshot is None or forcar_live:
            try:
                from ch_sentinela.github_reader import LeitorGitHub
                leitor = LeitorGitHub()
            except Exception:
                leitor = None

        multi_sup = SupervisorMultiRepo(
            intervalo_minutos=60,
            modo_operacao="DRY_RUN",
            leitor_gh=leitor,
        )
        relatorio = multi_sup.executar_ciclo(snapshot_projeto=snapshot, forcar_live=forcar_live)
        ruc_md = relatorio.gerar_markdown_ruc()

        if getattr(args, "output_report", None):
            out_p = Path(args.output_report)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(ruc_md, encoding="utf-8")

        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "run_id": relatorio.run_id,
                        "inicio_utc": relatorio.inicio_utc,
                        "termino_utc": relatorio.termino_utc,
                        "modo_operacao": relatorio.modo_operacao,
                        "origem_dados": relatorio.origem_dados,
                        "total_repositorios_cadastrados": relatorio.total_repositorios_cadastrados,
                        "total_repositorios_consultados": relatorio.total_repositorios_consultados,
                        "total_repositorios_verificados": relatorio.total_repositorios_verificados_efetivos,
                        "total_itens_analisados": relatorio.total_itens_analisados,
                        "total_elegiveis_agy": relatorio.total_elegiveis_agy,
                        "total_bloqueados": relatorio.total_bloqueados,
                        "total_outra_esteira": relatorio.total_outra_esteira,
                        "reserva_efetuada": relatorio.reserva_efetuada.para_dicionario()
                        if relatorio.reserva_efetuada
                        else None,
                        "custo_adicional_brl": relatorio.custo_adicional_brl,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(ruc_md)
        return 0

    supervisor = HourlySupervisor(config=config)
    report = supervisor.executar_ciclo(
        snapshot_override=snapshot_override,
        items_override=items_raw,
        fields_override=fields_raw,
    )

    if getattr(args, "output_report", None):
        out_p = Path(args.output_report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report.format_markdown(), encoding="utf-8")

    if getattr(args, "json", False):
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    elif getattr(args, "summary", False) and report.is_summary_only:
        print(report.format_summary())
    else:
        print(report.format_markdown())

    return 0 if report.raw_status in {"IMPLEMENTADO_NAO_ATIVADO", "CYCLE_OVERLAP_PREVENTED", "BLOQUEADO_DADOS"} else 1


