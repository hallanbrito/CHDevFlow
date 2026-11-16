"""Motor de Gestão de Turnos e Produção Contínua — CH-FACTORY (CHDevFlow).

Implementa os contratos e funcionalidades da Issue #72 (CH-FACTORY-01):
1. Histórico persistente de produção por turno com controle de concorrência.
2. Timeline de eventos e entregas com filtros multi-critério (data, projeto, executor, resultado).
3. Planejamento das tarefas dos próximos turnos.
4. Identificação e verificação de dependências e pré-requisitos técnicos/humanos.
5. Relatório automático de passagem de turno (Handover).
6. Integração bidirecional com o Supervisor Multi-Repositório e Control Center.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any, Sequence
import uuid

from ch_sentinela.config import PO_IDENTIDADE_PADRAO, obter_diretorio_dados
from chdevflow.core.multi_repo_queue import InterprocessFileLock, SupervisorLockError
from chdevflow.core.multi_repo_reports import RelatorioCicloSupervisao


NOME_ARQUIVO_FACTORY_PADRAO = "ch_factory_estado.json"
EXECUTORES_VALIDOS = ("AGY", "ChatGPT", "Codex", "Hallan", "Humano", "Sistema")
RESULTADOS_VALIDOS = (
    "SUCESSO",
    "BLOQUEADO",
    "SEM_TRABALHO_LIBERADO",
    "EM_ANDAMENTO",
    "FALHA",
    "CYCLE_OVERLAP_PREVENTED",
)
STATUS_TAREFA_VALIDOS = (
    "PLANEJADA",
    "PRONTA",
    "BLOQUEADA",
    "EM_EXECUCAO",
    "CONCLUIDA",
    "CANCELADA",
)
PESO_PRIORIDADE: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass(frozen=True)
class TurnoProducao:
    """Registro imutável de execução de um turno de produção na fábrica CHDevFlow."""

    turno_id: str
    executor: str
    repositorio: str
    missao_ref: str
    inicio_utc: str
    fim_utc: str
    resultado: str
    commits: tuple[str, ...] = ()
    pr_numero: int | None = None
    pr_url: str | None = None
    testes_executados: int = 0
    testes_status: str = "PASS"  # "PASS", "FAIL", "SKIP", "N/A"
    bloqueios: tuple[str, ...] = ()
    custo_brl: float = 0.0
    resumo: str = ""
    metadados: dict[str, Any] = field(default_factory=dict)

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa o turno para formato JSON-compatível."""
        dados = asdict(self)
        dados["commits"] = list(self.commits)
        dados["bloqueios"] = list(self.bloqueios)
        return dados

    @classmethod
    def de_dicionario(cls, dados: dict[str, Any]) -> TurnoProducao:
        """Desserializa o turno a partir de um dicionário."""
        return cls(
            turno_id=dados["turno_id"],
            executor=dados.get("executor", "AGY"),
            repositorio=dados.get("repositorio", "CHDevFlow"),
            missao_ref=dados.get("missao_ref", "N/A"),
            inicio_utc=dados["inicio_utc"],
            fim_utc=dados.get("fim_utc", dados["inicio_utc"]),
            resultado=dados.get("resultado", "EM_ANDAMENTO"),
            commits=tuple(dados.get("commits", ())),
            pr_numero=dados.get("pr_numero"),
            pr_url=dados.get("pr_url"),
            testes_executados=int(dados.get("testes_executados", 0)),
            testes_status=dados.get("testes_status", "PASS"),
            bloqueios=tuple(dados.get("bloqueios", ())),
            custo_brl=float(dados.get("custo_brl", 0.0)),
            resumo=dados.get("resumo", ""),
            metadados=dict(dados.get("metadados", {})),
        )


@dataclass(frozen=True)
class ItemPlanejamentoTurno:
    """Item ou tarefa planejada para execução em turnos futuros."""

    tarefa_id: str
    missao_ref: str
    repositorio: str
    executor_previsto: str
    prioridade: str = "P1"  # "P0", "P1", "P2", "P3"
    estimativa_turnos: int = 1
    dependencias: tuple[str, ...] = ()
    pre_requisitos: tuple[str, ...] = ()
    status: str = "PLANEJADA"
    detalhes: str = ""
    criado_em_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa a tarefa para JSON."""
        dados = asdict(self)
        dados["dependencias"] = list(self.dependencias)
        dados["pre_requisitos"] = list(self.pre_requisitos)
        return dados

    @classmethod
    def de_dicionario(cls, dados: dict[str, Any]) -> ItemPlanejamentoTurno:
        """Desserializa a tarefa de dicionário."""
        return cls(
            tarefa_id=dados["tarefa_id"],
            missao_ref=dados.get("missao_ref", "N/A"),
            repositorio=dados.get("repositorio", "CHDevFlow"),
            executor_previsto=dados.get("executor_previsto", "AGY"),
            prioridade=dados.get("prioridade", "P1"),
            estimativa_turnos=int(dados.get("estimativa_turnos", 1)),
            dependencias=tuple(dados.get("dependencias", ())),
            pre_requisitos=tuple(dados.get("pre_requisitos", ())),
            status=dados.get("status", "PLANEJADA"),
            detalhes=dados.get("detalhes", ""),
            criado_em_utc=dados.get(
                "criado_em_utc", datetime.now(timezone.utc).isoformat()
            ),
        )


@dataclass(frozen=True)
class RelatorioPassagemTurno:
    """Documento estruturado de passagem de turno (Handover) entre executores."""

    relatorio_id: str
    gerado_em_utc: str
    turno_atual_id: str | None
    executor_sainte: str
    executor_entrante: str | None
    resumo_produzido: str
    entregas_realizadas: tuple[str, ...]
    bloqueios_ativos: tuple[str, ...]
    proximas_tarefas_prioritarias: tuple[ItemPlanejamentoTurno, ...]
    pendencias_autorizacao: tuple[str, ...]

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa o relatório para JSON."""
        return {
            "relatorio_id": self.relatorio_id,
            "gerado_em_utc": self.gerado_em_utc,
            "turno_atual_id": self.turno_atual_id,
            "executor_sainte": self.executor_sainte,
            "executor_entrante": self.executor_entrante,
            "resumo_produzido": self.resumo_produzido,
            "entregas_realizadas": list(self.entregas_realizadas),
            "bloqueios_ativos": list(self.bloqueios_ativos),
            "proximas_tarefas_prioritarias": [
                t.para_dicionario() for t in self.proximas_tarefas_prioritarias
            ],
            "pendencias_autorizacao": list(self.pendencias_autorizacao),
        }


class CHFactoryManager:
    """Gerenciador de estado persistente, histórico, timeline e planejamento da CH-FACTORY."""

    def __init__(self, caminho_arquivo: Path | str | None = None) -> None:
        """Inicializa o gestor da fábrica com bloqueio interprocesso e persistência segura."""
        self._lock = Lock()
        if caminho_arquivo is not None:
            self.caminho_arquivo = Path(caminho_arquivo)
        else:
            self.caminho_arquivo = obter_diretorio_dados() / NOME_ARQUIVO_FACTORY_PADRAO

        self.caminho_lock = self.caminho_arquivo.with_suffix(".lock")
        self._file_lock = InterprocessFileLock(self.caminho_lock)

        self._turnos: list[TurnoProducao] = []
        self._planejamento: list[ItemPlanejamentoTurno] = []
        self._carregar_estado()

    # -------------------------------------------------------------------------
    # Persistência Atômica Segura
    # -------------------------------------------------------------------------

    def _carregar_estado(self) -> None:
        """Carrega turnos e tarefas do armazenamento JSON se disponível."""
        if not self.caminho_arquivo.exists():
            return

        try:
            with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)

            turnos_carregados = [
                TurnoProducao.de_dicionario(d)
                for d in dados.get("turnos", [])
            ]
            planejamento_carregado = [
                ItemPlanejamentoTurno.de_dicionario(d)
                for d in dados.get("planejamento", [])
            ]

            self._turnos = turnos_carregados
            self._planejamento = planejamento_carregado
        except Exception:
            # Fallback fail-closed: mantém listas vazias se houver corrupção
            pass

    def _salvar_estado(self) -> None:
        """Persiste atomicamente o estado em disco (0o600) via arquivo temporário."""
        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
        dir_pai = self.caminho_arquivo.parent

        dados = {
            "versao": "1.0",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "turnos": [t.para_dicionario() for t in self._turnos],
            "planejamento": [p.para_dicionario() for p in self._planejamento],
        }

        fd, temp_path = tempfile.mkstemp(
            dir=dir_pai, prefix="factory_", suffix=".tmp"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(temp_path, 0o600)
            except OSError:
                pass
            os.replace(temp_path, self.caminho_arquivo)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    # -------------------------------------------------------------------------
    # Prioridade 1: Histórico Persistente de Produção por Turno
    # -------------------------------------------------------------------------

    def registrar_turno(self, turno: TurnoProducao) -> TurnoProducao:
        """Registra e persiste um novo turno de produção com exclusão mútua atômica."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            # Evita duplicatas pelo turno_id
            indices = [i for i, t in enumerate(self._turnos) if t.turno_id == turno.turno_id]
            if indices:
                self._turnos[indices[0]] = turno
            else:
                self._turnos.append(turno)

            self._salvar_estado()
            return turno

    def obter_turno(self, turno_id: str) -> TurnoProducao | None:
        """Recupera um turno específico pelo identificador."""
        with self._lock, self._file_lock:
            self._carregar_estado()
            for t in self._turnos:
                if t.turno_id == turno_id:
                    return t
            return None

    def listar_turnos(self) -> tuple[TurnoProducao, ...]:
        """Retorna todos os turnos registrados em ordem cronológica."""
        with self._lock, self._file_lock:
            self._carregar_estado()
            return tuple(self._turnos)

    # -------------------------------------------------------------------------
    # Prioridade 2: Timeline com Filtros Multi-Critério
    # -------------------------------------------------------------------------

    def filtrar_timeline(
        self,
        inicio_data: str | None = None,
        fim_data: str | None = None,
        projeto: str | None = None,
        executor: str | None = None,
        resultado: str | None = None,
    ) -> tuple[TurnoProducao, ...]:
        """Filtra o histórico de produção por data, projeto, executor e resultado.

        Args:
            inicio_data: Filtro de data mínima ISO 8601 (inclusive).
            fim_data: Filtro de data máxima ISO 8601 (inclusive).
            projeto: Nome ou slug do projeto/repositório.
            executor: Executor responsável (AGY, ChatGPT, Codex, etc.).
            resultado: Status de resultado (SUCESSO, BLOQUEADO, etc.).
        """
        with self._lock, self._file_lock:
            self._carregar_estado()

            resultados: list[TurnoProducao] = []
            for t in self._turnos:
                # Filtro por executor
                if executor and t.executor.upper() != executor.upper():
                    continue

                # Filtro por repositório/projeto
                if projeto:
                    proj_norm = projeto.lower().replace("hallanbrito/", "")
                    repo_norm = t.repositorio.lower().replace("hallanbrito/", "")
                    if proj_norm != repo_norm and proj_norm not in repo_norm:
                        continue

                # Filtro por resultado
                if resultado and t.resultado.upper() != resultado.upper():
                    continue

                # Filtro por período temporal
                if inicio_data:
                    dt_turno = t.inicio_utc[:10] if len(t.inicio_utc) >= 10 else t.inicio_utc
                    if dt_turno < inicio_data[:10]:
                        continue

                if fim_data:
                    dt_turno = t.fim_utc[:10] if len(t.fim_utc) >= 10 else t.fim_utc
                    if dt_turno > fim_data[:10]:
                        continue

                resultados.append(t)

            # Ordena por início UTC
            resultados.sort(key=lambda x: x.inicio_utc)
            return tuple(resultados)

    # -------------------------------------------------------------------------
    # Prioridade 3: Planejamento das Tarefas dos Próximos Turnos
    # -------------------------------------------------------------------------

    def adicionar_tarefa_planejada(
        self, tarefa: ItemPlanejamentoTurno
    ) -> ItemPlanejamentoTurno:
        """Adiciona ou atualiza uma tarefa no planejamento da fábrica."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            indices = [
                i for i, p in enumerate(self._planejamento)
                if p.tarefa_id == tarefa.tarefa_id
            ]
            if indices:
                self._planejamento[indices[0]] = tarefa
            else:
                self._planejamento.append(tarefa)

            self._salvar_estado()
            return tarefa

    def listar_planejamento(self) -> tuple[ItemPlanejamentoTurno, ...]:
        """Retorna todas as tarefas registradas no planejamento."""
        with self._lock, self._file_lock:
            self._carregar_estado()
            return tuple(self._planejamento)

    def atualizar_status_tarefa(
        self, tarefa_id: str, novo_status: str
    ) -> ItemPlanejamentoTurno:
        """Atualiza o status de execução de uma tarefa do planejamento."""
        if novo_status not in STATUS_TAREFA_VALIDOS:
            raise ValueError(
                f"Status inválido: '{novo_status}'. Válidos: {STATUS_TAREFA_VALIDOS}"
            )

        with self._lock, self._file_lock:
            self._carregar_estado()

            for i, p in enumerate(self._planejamento):
                if p.tarefa_id == tarefa_id:
                    tarefa_atualizada = ItemPlanejamentoTurno(
                        tarefa_id=p.tarefa_id,
                        missao_ref=p.missao_ref,
                        repositorio=p.repositorio,
                        executor_previsto=p.executor_previsto,
                        prioridade=p.prioridade,
                        estimativa_turnos=p.estimativa_turnos,
                        dependencias=p.dependencias,
                        pre_requisitos=p.pre_requisitos,
                        status=novo_status,
                        detalhes=p.detalhes,
                        criado_em_utc=p.criado_em_utc,
                    )
                    self._planejamento[i] = tarefa_atualizada
                    self._salvar_estado()
                    return tarefa_atualizada

            raise KeyError(f"Tarefa não encontrada no planejamento: '{tarefa_id}'")

    # -------------------------------------------------------------------------
    # Prioridade 4: Identificação de Dependências e Pré-requisitos
    # -------------------------------------------------------------------------

    def verificar_dependencias_tarefa(
        self,
        tarefa_id: str,
        tarefas_concluidas: set[str] | None = None,
        pre_requisitos_satisfeitos: set[str] | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        """Verifica se todas as dependências e pré-requisitos de uma tarefa estão satisfeitos.

        Retorna:
            (elegivel, motivos_bloqueio)
        """
        with self._lock, self._file_lock:
            self._carregar_estado()

            tarefa = None
            for p in self._planejamento:
                if p.tarefa_id == tarefa_id:
                    tarefa = p
                    break

            if tarefa is None:
                return False, (f"Tarefa '{tarefa_id}' inexistente no planejamento",)

            concluidas = set(tarefas_concluidas or ())
            # Também considera concluídas as tarefas marcadas como CONCLUIDA no planejamento
            for p in self._planejamento:
                if p.status == "CONCLUIDA":
                    concluidas.add(p.tarefa_id)

            pre_satisfeitos = set(pre_requisitos_satisfeitos or ())

            bloqueios: list[str] = []

            # 1. Verifica dependências de outras tarefas
            for dep in tarefa.dependencias:
                if dep not in concluidas:
                    bloqueios.append(f"Dependência pendente da tarefa '{dep}'")

            # 2. Verifica pré-requisitos técnicos ou humanos
            for req in tarefa.pre_requisitos:
                if req not in pre_satisfeitos:
                    bloqueios.append(f"Pré-requisito pendente: '{req}'")

            elegivel = len(bloqueios) == 0
            return elegivel, tuple(bloqueios)

    def obter_proximas_tarefas_elegiveis(
        self,
        executor: str | None = None,
        tarefas_concluidas: set[str] | None = None,
        pre_requisitos_satisfeitos: set[str] | None = None,
    ) -> tuple[ItemPlanejamentoTurno, ...]:
        """Retorna tarefas aptas para execução imediata, ordenadas por prioridade estrita (P0 > P1 > P2 > P3)."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            elegiveis: list[ItemPlanejamentoTurno] = []
            for p in self._planejamento:
                if p.status in ("CONCLUIDA", "CANCELADA", "EM_EXECUCAO"):
                    continue

                if executor and p.executor_previsto.upper() != executor.upper():
                    continue

                is_ok, _ = self.verificar_dependencias_tarefa(
                    p.tarefa_id,
                    tarefas_concluidas=tarefas_concluidas,
                    pre_requisitos_satisfeitos=pre_requisitos_satisfeitos,
                )
                if is_ok:
                    elegiveis.append(p)

            # Ordena por peso de prioridade
            elegiveis.sort(key=lambda t: (PESO_PRIORIDADE.get(t.prioridade, 99), t.tarefa_id))
            return tuple(elegiveis)

    # -------------------------------------------------------------------------
    # Prioridade 5: Relatório Automático de Passagem de Turno (Handover)
    # -------------------------------------------------------------------------

    def gerar_relatorio_passagem_turno(
        self,
        executor_sainte: str = "AGY",
        executor_entrante: str | None = "ChatGPT",
        turno_recente_id: str | None = None,
    ) -> RelatorioPassagemTurno:
        """Gera o relatório formal e auditável de passagem de turno."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            # Identifica o turno mais recente do executor sainte
            turno_alvo: TurnoProducao | None = None
            if turno_recente_id:
                for t in self._turnos:
                    if t.turno_id == turno_recente_id:
                        turno_alvo = t
                        break
            elif self._turnos:
                turnos_sainte = [t for t in self._turnos if t.executor.upper() == executor_sainte.upper()]
                if turnos_sainte:
                    turno_alvo = turnos_sainte[-1]
                else:
                    turno_alvo = self._turnos[-1]

            resumo = turno_alvo.resumo if turno_alvo else "Nenhum turno anterior registrado."
            entregas: list[str] = []
            bloqueios: list[str] = []

            if turno_alvo:
                if turno_alvo.pr_numero:
                    entregas.append(f"PR #{turno_alvo.pr_numero} ({turno_alvo.missao_ref})")
                if turno_alvo.commits:
                    entregas.append(f"Commits: {', '.join(turno_alvo.commits[:3])}")
                if turno_alvo.resultado == "SUCESSO" and not entregas:
                    entregas.append(f"Missão {turno_alvo.missao_ref} implementada com sucesso")
                bloqueios.extend(turno_alvo.bloqueios)

            proximas = self.obter_proximas_tarefas_elegiveis()
            pendencias_auth: list[str] = []
            for p in self._planejamento:
                if "AUTORIZACAO_PO" in p.pre_requisitos:
                    pendencias_auth.append(f"{p.tarefa_id}: {p.missao_ref} ({p.repositorio})")

            relatorio = RelatorioPassagemTurno(
                relatorio_id=f"handover-{uuid.uuid4().hex[:12]}",
                gerado_em_utc=datetime.now(timezone.utc).isoformat(),
                turno_atual_id=turno_alvo.turno_id if turno_alvo else None,
                executor_sainte=executor_sainte,
                executor_entrante=executor_entrante,
                resumo_produzido=resumo,
                entregas_realizadas=tuple(entregas),
                bloqueios_ativos=tuple(bloqueios),
                proximas_tarefas_prioritarias=proximas[:5],
                pendencias_autorizacao=tuple(pendencias_auth),
            )
            return relatorio

    def formatar_relatorio_passagem_markdown(
        self, relatorio: RelatorioPassagemTurno
    ) -> str:
        """Renderiza o relatório de passagem de turno em formato Markdown padrão RUC."""
        linhas = [
            "# CH-FACTORY — Relatório de Passagem de Turno (Handover)",
            "",
            f"> **ID do Handover:** `{relatorio.relatorio_id}`<br>",
            f"> **Data/Hora UTC:** `{relatorio.gerado_em_utc}`<br>",
            f"> **Executor Sainte:** `{relatorio.executor_sainte}`<br>",
            f"> **Executor Entrante:** `{relatorio.executor_entrante or 'Indefinido'}`<br>",
            f"> **Turno Referência:** `{relatorio.turno_atual_id or 'N/A'}`",
            "",
            "---",
            "",
            "## 1. Resumo da Produção do Turno",
            "",
            relatorio.resumo_produzido or "Nenhum trabalho específico detalhado.",
            "",
            "## 2. Entregas Realizadas",
            "",
        ]

        if relatorio.entregas_realizadas:
            for entrega in relatorio.entregas_realizadas:
                linhas.append(f"- {entrega}")
        else:
            linhas.append("- Nenhuma entrega de software concluída neste turno.")

        linhas.extend([
            "",
            "## 3. Bloqueios Ativos e Riscos",
            "",
        ])

        if relatorio.bloqueios_ativos:
            for b in relatorio.bloqueios_ativos:
                linhas.append(f"- ⚠️ {b}")
        else:
            linhas.append("- Nenhum bloqueio ativo registrado.")

        linhas.extend([
            "",
            "## 4. Próximas Tarefas Elegíveis (Fila Prioritária)",
            "",
        ])

        if relatorio.proximas_tarefas_prioritarias:
            linhas.append("| Prioridade | ID Tarefa | Missão / Issue | Repositório | Executor Previsto |")
            linhas.append("|---|---|---|---|---|")
            for t in relatorio.proximas_tarefas_prioritarias:
                linhas.append(
                    f"| **{t.prioridade}** | `{t.tarefa_id}` | {t.missao_ref} | `{t.repositorio}` | {t.executor_previsto} |"
                )
        else:
            linhas.append("Nenhuma tarefa imediatamente elegível (SEM_TRABALHO_LIBERADO).")

        linhas.extend([
            "",
            "## 5. Pendências de Decisão / Autorização do PO",
            "",
        ])

        if relatorio.pendencias_autorizacao:
            for p in relatorio.pendencias_autorizacao:
                linhas.append(f"- [ ] Aguardando autorização do PO: `{p}`")
        else:
            linhas.append("- Nenhuma pendência de autorização do PO ativa.")

        linhas.extend([
            "",
            "---",
            "**Governança:** AGY PRODUZ. CHATGPT SUPERVISIONA. HALLAN DECIDE.",
        ])

        return "\n".join(linhas)

    # -------------------------------------------------------------------------
    # Prioridade 6: Integração com Supervisor e Control Center
    # -------------------------------------------------------------------------

    def integrar_com_supervisor(
        self,
        relatorio_ciclo: RelatorioCicloSupervisao,
        executor: str = "AGY",
    ) -> TurnoProducao:
        """Converte automaticamente a saída de um ciclo do Supervisor em um turno persistente."""
        resultado = "SUCESSO"
        if relatorio_ciclo.origem_dados == "BLOQUEIO_CONCORRENCIA":
            resultado = "CYCLE_OVERLAP_PREVENTED"
        elif relatorio_ciclo.total_bloqueados > 0 and relatorio_ciclo.total_elegiveis_agy == 0:
            resultado = "BLOQUEADO"
        elif relatorio_ciclo.total_elegiveis_agy == 0:
            resultado = "SEM_TRABALHO_LIBERADO"

        bloqueios: list[str] = []
        for p in relatorio_ciclo.pareceres:
            if not p.elegivel:
                bloqueios.extend(p.motivos_bloqueio)

        reserva = relatorio_ciclo.reserva_efetuada
        missao_ref = "N/A"
        repo = "CHDevFlow"
        if reserva:
            missao_ref = f"#{reserva.item.issue_numero} ({reserva.item.titulo})"
            repo = reserva.item.repositorio

        turno = TurnoProducao(
            turno_id=f"turno-{relatorio_ciclo.run_id}",
            executor=executor,
            repositorio=repo,
            missao_ref=missao_ref,
            inicio_utc=relatorio_ciclo.inicio_utc,
            fim_utc=relatorio_ciclo.termino_utc,
            resultado=resultado,
            commits=(),
            pr_numero=None,
            pr_url=None,
            testes_executados=0,
            testes_status="PASS",
            bloqueios=tuple(bloqueios[:5]),
            custo_brl=relatorio_ciclo.custo_adicional_brl,
            resumo=(
                f"Ciclo de supervisão horária multi-repositório executado. "
                f"Origem dados: {relatorio_ciclo.origem_dados}. "
                f"Analisados: {relatorio_ciclo.total_itens_analisados}. "
                f"Elegíveis: {relatorio_ciclo.total_elegiveis_agy}."
            ),
            metadados={
                "run_id": relatorio_ciclo.run_id,
                "origem_dados": relatorio_ciclo.origem_dados,
                "repositorios_cadastrados": relatorio_ciclo.repositorios_cadastrados,
                "repositorios_consultados": relatorio_ciclo.repositorios_consultados,
                "repositorios_verificados": relatorio_ciclo.repositorios_verificados,
            },
        )
        return self.registrar_turno(turno)

    def obter_snapshot_fabrica(self) -> dict[str, Any]:
        """Gera um snapshot consolidado do estado da fábrica para consumo pelo Control Center."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            total_turnos = len(self._turnos)
            turnos_sucesso = sum(1 for t in self._turnos if t.resultado == "SUCESSO")
            turnos_bloqueados = sum(1 for t in self._turnos if t.resultado == "BLOQUEADO")

            tarefas_concluidas = sum(1 for p in self._planejamento if p.status == "CONCLUIDA")
            tarefas_planejadas = sum(1 for p in self._planejamento if p.status == "PLANEJADA")

            return {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "estatisticas": {
                    "total_turnos": total_turnos,
                    "turnos_sucesso": turnos_sucesso,
                    "turnos_bloqueados": turnos_bloqueados,
                    "total_tarefas_planejamento": len(self._planejamento),
                    "tarefas_concluidas": tarefas_concluidas,
                    "tarefas_planejadas": tarefas_planejadas,
                },
                "turnos_recentes": [t.para_dicionario() for t in self._turnos[-10:]],
                "proximas_tarefas": [
                    t.para_dicionario() for t in self.obter_proximas_tarefas_elegiveis()[:5]
                ],
            }


def run_factory_cli(args: Any) -> int:
    """Ponto de entrada executável para os subcomandos 'ch factory'."""
    import sys

    config_path = getattr(args, "config_file", None)
    factory = CHFactoryManager(config_path)
    action = getattr(args, "factory_action", None)

    if action == "history":
        turnos = factory.listar_turnos()
        limit = getattr(args, "limit", None)
        if limit:
            turnos = turnos[-limit:]

        if getattr(args, "json", False):
            print(json.dumps([t.para_dicionario() for t in turnos], indent=2, ensure_ascii=False))
            return 0

        print(f"=== Histórico de Produção CH-FACTORY ({len(turnos)} turnos) ===")
        for t in turnos:
            print(f"[{t.inicio_utc[:16]}] {t.turno_id} | {t.executor} | {t.repositorio} | {t.resultado} | {t.missao_ref}")
            if t.resumo:
                print(f"   Resumo: {t.resumo}")
            if t.bloqueios:
                print(f"   Bloqueios: {'; '.join(t.bloqueios)}")
        return 0

    if action == "timeline":
        turnos = factory.filtrar_timeline(
            inicio_data=getattr(args, "from_date", None),
            fim_data=getattr(args, "to_date", None),
            projeto=getattr(args, "project", None),
            executor=getattr(args, "executor", None),
            resultado=getattr(args, "result", None),
        )
        if getattr(args, "json", False):
            print(json.dumps([t.para_dicionario() for t in turnos], indent=2, ensure_ascii=False))
            return 0

        print(f"=== Timeline Filtrada CH-FACTORY ({len(turnos)} eventos) ===")
        for t in turnos:
            status_symbol = "✅" if t.resultado == "SUCESSO" else ("⚠️" if t.resultado == "BLOQUEADO" else "ℹ️")
            print(f"{status_symbol} [{t.inicio_utc[:16]}] {t.executor} @ {t.repositorio}: {t.missao_ref} -> {t.resultado}")
            if t.commits:
                print(f"     Commits: {', '.join(t.commits)}")
            if t.pr_numero:
                print(f"     PR: #{t.pr_numero}")
        return 0

    if action == "plan":
        if getattr(args, "add", None):
            nova_tarefa = ItemPlanejamentoTurno(
                tarefa_id=args.add,
                missao_ref=getattr(args, "ref", "N/A"),
                repositorio=getattr(args, "repo", "CHDevFlow"),
                executor_previsto=getattr(args, "executor", "AGY"),
                prioridade=getattr(args, "priority", "P1"),
                estimativa_turnos=getattr(args, "estimate", 1),
                dependencias=tuple(d.strip() for d in getattr(args, "deps", "").split(",") if d.strip()),
                pre_requisitos=tuple(r.strip() for r in getattr(args, "reqs", "").split(",") if r.strip()),
                status=getattr(args, "status", "PLANEJADA"),
                detalhes=getattr(args, "details", ""),
            )
            factory.adicionar_tarefa_planejada(nova_tarefa)
            print(f"Tarefa '{nova_tarefa.tarefa_id}' adicionada ao planejamento da fábrica com prioridade {nova_tarefa.prioridade}.")
            return 0

        if getattr(args, "update_status", None):
            partes = getattr(args, "update_status", "").split(":")
            if len(partes) == 2:
                tid, novo_st = partes[0].strip(), partes[1].strip()
                tarefa = factory.atualizar_status_tarefa(tid, novo_st)
                print(f"Tarefa '{tid}' atualizada para status '{tarefa.status}'.")
                return 0
            else:
                print("Formato esperado para --update-status: ID_TAREFA:NOVO_STATUS", file=sys.stderr)
                return 1

        tarefas = factory.listar_planejamento()
        if getattr(args, "json", False):
            print(json.dumps([t.para_dicionario() for t in tarefas], indent=2, ensure_ascii=False))
            return 0

        print(f"=== Planejamento de Turnos CH-FACTORY ({len(tarefas)} tarefas) ===")
        for t in tarefas:
            ok, motivos = factory.verificar_dependencias_tarefa(t.tarefa_id)
            flag = "PRONTA" if ok else f"BLOQUEADA ({len(motivos)} pendências)"
            print(f"[{t.prioridade}] {t.tarefa_id} | {t.missao_ref} ({t.repositorio}) | {t.executor_previsto} | Status: {t.status} | Aptidão: {flag}")
            if not ok:
                for m in motivos:
                    print(f"     - {m}")
        return 0

    if action == "handover":
        sainte = getattr(args, "sainte", "AGY")
        entrante = getattr(args, "entrante", "ChatGPT")
        shift_id = getattr(args, "shift_id", None)
        relatorio = factory.gerar_relatorio_passagem_turno(
            executor_sainte=sainte,
            executor_entrante=entrante,
            turno_recente_id=shift_id,
        )

        if getattr(args, "json", False):
            print(json.dumps(relatorio.para_dicionario(), indent=2, ensure_ascii=False))
            return 0

        md = factory.formatar_relatorio_passagem_markdown(relatorio)
        output_file = getattr(args, "output", None)
        if output_file:
            p = Path(output_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            print(f"Relatório de passagem de turno gravado em: {p}")
        else:
            print(md)
        return 0

    if action == "snapshot":
        snap = factory.obter_snapshot_fabrica()
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    print("Subcomando do factory não especificado. Use 'ch factory --help'.", file=sys.stderr)
    return 1
