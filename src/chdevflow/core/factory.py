"""Motor de Gestão de Turnos e Produção — CH-FACTORY (Fatia F1 / Issue #72).

Implementa rigorosamente os critérios de aceite da Fatia F1 conforme autorização do PO
e apontamentos da Auditoria Independente CH-1:
1. Modelo de Eventos de Turno (`TurnoProducao`) com segregação entre SUPERVISAO e ENTREGA_SOFTWARE.
2. Persistência Local Atômica Segura (permissões 0o600, lock exclusivo no SO, tolerância a falhas).
3. Deduplicação e Idempotência estritas no registro de eventos.
4. Suporte nativo a fuso horário America/Fortaleza (UTC-3) com persistência canônica UTC.
5. Rotulagem explícita de evidências (`VERIFICADO`, `NAO_VERIFICADO`, `SIMULADO_OFFLINE`).
6. Sanitização automática de segredos e tokens nos dados de entrada/saída.
7. Interface Filtrável da Timeline por multi-critérios (data, projeto, executor, resultado, tipo).
8. Passagem Mínima de Turno (`PassagemTurnoMinima`) estruturada e auditável.
9. Snapshot para integração desacoplada com o Control Center.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from ch_sentinela.config import obter_diretorio_dados
from ch_sentinela.security.policies import sanitizar_texto_segredos


NOME_ARQUIVO_FACTORY_PADRAO = "ch_factory_estado.json"
TZ_FORTALEZA = ZoneInfo("America/Fortaleza")

TIPOS_REGISTRO_VALIDOS = ("SUPERVISAO", "ENTREGA_SOFTWARE")
RESULTADOS_VALIDOS = (
    "SUCESSO",
    "BLOQUEADO",
    "SEM_TRABALHO_LIBERADO",
    "EM_ANDAMENTO",
    "FALHA",
    "CYCLE_OVERLAP_PREVENTED",
)
STATUS_EVIDENCIA_VALIDOS = ("VERIFICADO", "NAO_VERIFICADO", "SIMULADO_OFFLINE")


class FactoryLockError(RuntimeError):
    """Exceção levantada quando outro processo detém o lock da fábrica."""
    pass


class InterprocessFileLock:
    """Controle estrito de exclusão mútua interprocesso baseado em criação atômica no SO (O_CREAT | O_EXCL)."""

    def __init__(
        self,
        lock_path: Path | str,
        max_age_seconds: int = 900,
    ) -> None:
        self.lock_path = Path(lock_path)
        self.max_age_seconds = max_age_seconds
        self._acquired = False

    def __enter__(self) -> InterprocessFileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def acquire(self) -> bool:
        if self._acquired:
            return True

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                conteudo = json.loads(self.lock_path.read_text(encoding="utf-8"))
                ts_inicio = datetime.fromisoformat(conteudo.get("timestamp_utc", ""))
                idade = (datetime.now(timezone.utc) - ts_inicio).total_seconds()
                if idade > self.max_age_seconds:
                    try:
                        self.lock_path.unlink()
                    except OSError:
                        pass
                else:
                    raise FactoryLockError(
                        f"Lock interprocesso ativo (PID {conteudo.get('pid')}, "
                        f"iniciado há {int(idade)}s). Concorrência bloqueada."
                    )
            except (json.JSONDecodeError, ValueError, KeyError):
                raise FactoryLockError(
                    f"Arquivo de lock existente '{self.lock_path}' impede operação concorrente."
                )

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
            return True
        except FileExistsError as exc:
            raise FactoryLockError(
                f"Lock concorrente detectado: arquivo '{self.lock_path}' já existe."
            ) from exc

    def release(self) -> None:
        if self._acquired and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass
            self._acquired = False


@dataclass(frozen=True)
class TurnoProducao:
    """Registro imutável de evento de execução de um turno de produção na CH-FACTORY."""

    turno_id: str
    executor: str
    repositorio: str
    missao_ref: str
    inicio_utc: str
    fim_utc: str
    resultado: str
    tipo_registro: str = "SUPERVISAO"  # "SUPERVISAO" ou "ENTREGA_SOFTWARE"
    status_evidencia: str = "NAO_VERIFICADO"  # "VERIFICADO", "NAO_VERIFICADO", "SIMULADO_OFFLINE"
    commits: tuple[str, ...] = ()
    pr_numero: int | None = None
    pr_url: str | None = None
    testes_executados: int = 0
    testes_status: str = "PASS"  # "PASS", "FAIL", "SKIP", "NAO_VERIFICADO"
    bloqueios: tuple[str, ...] = ()
    custo_brl: float = 0.0
    resumo: str = ""
    metadados: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Sanitização obrigatória de resumo e bloqueios contra segredos e tokens
        if self.resumo:
            object.__setattr__(self, "resumo", sanitizar_texto_segredos(self.resumo))
        if self.bloqueios:
            object.__setattr__(
                self,
                "bloqueios",
                tuple(sanitizar_texto_segredos(b) for b in self.bloqueios),
            )

        # Diferenciação entre Supervisão e Entrega Real
        if self.tipo_registro == "SUPERVISAO":
            if self.commits:
                raise ValueError(
                    "Turno do tipo SUPERVISAO não pode conter commits de código. "
                    "Use tipo_registro='ENTREGA_SOFTWARE' para entregas de software reais."
                )

    @property
    def inicio_fortaleza(self) -> str:
        """Retorna o timestamp de início convertido para o fuso America/Fortaleza."""
        try:
            dt_utc = datetime.fromisoformat(self.inicio_utc)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            return dt_utc.astimezone(TZ_FORTALEZA).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            return self.inicio_utc

    @property
    def fim_fortaleza(self) -> str:
        """Retorna o timestamp de término convertido para o fuso America/Fortaleza."""
        try:
            dt_utc = datetime.fromisoformat(self.fim_utc)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            return dt_utc.astimezone(TZ_FORTALEZA).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            return self.fim_utc

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa o turno para formato JSON-compatível com campos de fuso local."""
        dados = asdict(self)
        dados["commits"] = list(self.commits)
        dados["bloqueios"] = list(self.bloqueios)
        dados["inicio_fortaleza"] = self.inicio_fortaleza
        dados["fim_fortaleza"] = self.fim_fortaleza
        return dados

    @classmethod
    def de_dicionario(cls, dados: dict[str, Any]) -> TurnoProducao:
        """Desserializa o turno a partir de um dicionário JSON."""
        return cls(
            turno_id=dados["turno_id"],
            executor=dados.get("executor", "AGY"),
            repositorio=dados.get("repositorio", "CHDevFlow"),
            missao_ref=dados.get("missao_ref", "N/A"),
            inicio_utc=dados["inicio_utc"],
            fim_utc=dados.get("fim_utc", dados["inicio_utc"]),
            resultado=dados.get("resultado", "EM_ANDAMENTO"),
            tipo_registro=dados.get("tipo_registro", "SUPERVISAO"),
            status_evidencia=dados.get("status_evidencia", "NAO_VERIFICADO"),
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
class PassagemTurnoMinima:
    """Documento estruturado e mínimo de passagem de turno (F1 Handover)."""

    handover_id: str
    gerado_em_utc: str
    gerado_em_fortaleza: str
    executor_sainte: str
    executor_entrante: str
    turno_referencia_id: str | None
    tipo_ultimo_registro: str
    resumo_producao: str
    entregas_software: tuple[str, ...]
    bloqueios_ativos: tuple[str, ...]
    status_evidencia: str
    proxima_acao_recomendada: str

    def para_dicionario(self) -> dict[str, Any]:
        """Serializa o handover para formato JSON."""
        return {
            "handover_id": self.handover_id,
            "gerado_em_utc": self.gerado_em_utc,
            "gerado_em_fortaleza": self.gerado_em_fortaleza,
            "executor_sainte": self.executor_sainte,
            "executor_entrante": self.executor_entrante,
            "turno_referencia_id": self.turno_referencia_id,
            "tipo_ultimo_registro": self.tipo_ultimo_registro,
            "resumo_producao": self.resumo_producao,
            "entregas_software": list(self.entregas_software),
            "bloqueios_ativos": list(self.bloqueios_ativos),
            "status_evidencia": self.status_evidencia,
            "proxima_acao_recomendada": self.proxima_acao_recomendada,
        }


class CHFactoryManager:
    """Gerenciador de persistência local atômica e consulta da timeline CH-FACTORY (F1)."""

    def __init__(self, caminho_arquivo: Path | str | None = None) -> None:
        """Inicializa o gestor com bloqueio seguro e persistência local."""
        self._lock = RLock()
        if caminho_arquivo is not None:
            self.caminho_arquivo = Path(caminho_arquivo)
        else:
            self.caminho_arquivo = obter_diretorio_dados() / NOME_ARQUIVO_FACTORY_PADRAO

        self.caminho_lock = self.caminho_arquivo.with_suffix(".lock")
        self._file_lock = InterprocessFileLock(self.caminho_lock)

        self._turnos: list[TurnoProducao] = []
        self._carregar_estado()

    # -------------------------------------------------------------------------
    # Persistência Atômica Local (0o600)
    # -------------------------------------------------------------------------

    def _carregar_estado(self) -> None:
        """Carrega turnos do armazenamento JSON local se existir."""
        if not self.caminho_arquivo.exists():
            return

        try:
            with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)

            turnos_carregados = [
                TurnoProducao.de_dicionario(d)
                for d in dados.get("turnos", [])
            ]
            self._turnos = turnos_carregados
        except Exception:
            # Fallback fail-closed: mantém listas vazias se houver corrupção
            pass

    def _salvar_estado(self) -> None:
        """Persiste atomicamente o estado em disco (0o600) via arquivo temporário."""
        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
        dir_pai = self.caminho_arquivo.parent

        dados = {
            "versao": "1.0-F1",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "fuso_horario_padrao": "America/Fortaleza",
            "total_turnos": len(self._turnos),
            "turnos": [t.para_dicionario() for t in self._turnos],
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
    # API de Registro, Deduplicação e Idempotência
    # -------------------------------------------------------------------------

    def registrar_turno(self, turno: TurnoProducao) -> TurnoProducao:
        """Registra e persiste um novo turno de forma atômica e idempotente."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            # Deduplicação estrita por turno_id
            indices = [i for i, t in enumerate(self._turnos) if t.turno_id == turno.turno_id]
            if indices:
                # Idempotência: substitui exatamente o registro com o mesmo ID
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
    # Interface Filtrável da Timeline
    # -------------------------------------------------------------------------

    def filtrar_timeline(
        self,
        inicio_data: str | None = None,
        fim_data: str | None = None,
        projeto: str | None = None,
        executor: str | None = None,
        resultado: str | None = None,
        tipo_registro: str | None = None,
    ) -> tuple[TurnoProducao, ...]:
        """Filtra eventos da timeline por data, projeto, executor, resultado e tipo.

        Args:
            inicio_data: Data mínima ISO (AAAA-MM-DD).
            fim_data: Data máxima ISO (AAAA-MM-DD).
            projeto: Nome ou slug do repositório/projeto.
            executor: Identificador do executor (AGY, ChatGPT, Codex, etc.).
            resultado: Status de resultado (SUCESSO, BLOQUEADO, etc.).
            tipo_registro: 'SUPERVISAO' ou 'ENTREGA_SOFTWARE'.
        """
        with self._lock, self._file_lock:
            self._carregar_estado()

            resultados: list[TurnoProducao] = []
            for t in self._turnos:
                if executor and t.executor.upper() != executor.upper():
                    continue

                if tipo_registro and t.tipo_registro.upper() != tipo_registro.upper():
                    continue

                if projeto:
                    proj_norm = projeto.lower().replace("hallanbrito/", "")
                    repo_norm = t.repositorio.lower().replace("hallanbrito/", "")
                    if proj_norm != repo_norm and proj_norm not in repo_norm:
                        continue

                if resultado and t.resultado.upper() != resultado.upper():
                    continue

                if inicio_data:
                    dt_turno = t.inicio_utc[:10] if len(t.inicio_utc) >= 10 else t.inicio_utc
                    if dt_turno < inicio_data[:10]:
                        continue

                if fim_data:
                    dt_turno = t.fim_utc[:10] if len(t.fim_utc) >= 10 else t.fim_utc
                    if dt_turno > fim_data[:10]:
                        continue

                resultados.append(t)

            # Ordenação cronológica estrita por timestamp de início
            resultados.sort(key=lambda x: x.inicio_utc)
            return tuple(resultados)

    # -------------------------------------------------------------------------
    # Passagem Mínima de Turno (F1 Handover)
    # -------------------------------------------------------------------------

    def gerar_passagem_turno_minima(
        self,
        executor_sainte: str = "AGY",
        executor_entrante: str = "ChatGPT",
        turno_recente_id: str | None = None,
    ) -> PassagemTurnoMinima:
        """Gera o documento mínimo de passagem de turno da Fatia F1."""
        with self._lock, self._file_lock:
            self._carregar_estado()

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

            agora_utc = datetime.now(timezone.utc)
            agora_fortaleza = agora_utc.astimezone(TZ_FORTALEZA).strftime("%Y-%m-%d %H:%M:%S %Z")

            entregas: list[str] = []
            bloqueios: list[str] = []
            tipo_ultimo = "SUPERVISAO"
            resumo = "Nenhum turno anterior registrado."
            status_ev = "NAO_VERIFICADO"

            if turno_alvo:
                tipo_ultimo = turno_alvo.tipo_registro
                resumo = turno_alvo.resumo or f"Turno {turno_alvo.turno_id} concluído com resultado {turno_alvo.resultado}."
                status_ev = turno_alvo.status_evidencia
                if turno_alvo.pr_numero:
                    entregas.append(f"PR #{turno_alvo.pr_numero} ({turno_alvo.missao_ref})")
                if turno_alvo.commits:
                    entregas.append(f"Commits: {', '.join(turno_alvo.commits[:3])}")
                if turno_alvo.tipo_registro == "ENTREGA_SOFTWARE" and not entregas:
                    entregas.append(f"Software entregue na missão {turno_alvo.missao_ref}")
                bloqueios.extend(turno_alvo.bloqueios)

            proxima_acao = "Aguardando auditoria independente e decisão do PO."
            if bloqueios:
                proxima_acao = f"Resolver bloqueio prioritário: {bloqueios[0]}"

            return PassagemTurnoMinima(
                handover_id=f"handover-min-{uuid.uuid4().hex[:8]}",
                gerado_em_utc=agora_utc.isoformat(),
                gerado_em_fortaleza=agora_fortaleza,
                executor_sainte=executor_sainte,
                executor_entrante=executor_entrante,
                turno_referencia_id=turno_alvo.turno_id if turno_alvo else None,
                tipo_ultimo_registro=tipo_ultimo,
                resumo_producao=resumo,
                entregas_software=tuple(entregas),
                bloqueios_ativos=tuple(bloqueios),
                status_evidencia=status_ev,
                proxima_acao_recomendada=proxima_acao,
            )

    def formatar_passagem_turno_markdown(self, handover: PassagemTurnoMinima) -> str:
        """Renderiza a passagem mínima de turno em Markdown auditável."""
        linhas = [
            "# CH-FACTORY — Passagem Mínima de Turno (F1 Handover)",
            "",
            f"> **ID do Handover:** `{handover.handover_id}`<br>",
            f"> **Data/Hora Local (America/Fortaleza):** `{handover.gerado_em_fortaleza}`<br>",
            f"> **Data/Hora UTC:** `{handover.gerado_em_utc}`<br>",
            f"> **Executor Sainte:** `{handover.executor_sainte}`<br>",
            f"> **Executor Entrante:** `{handover.executor_entrante}`<br>",
            f"> **Turno Referência:** `{handover.turno_referencia_id or 'N/A'}`<br>",
            f"> **Tipo de Registro:** `{handover.tipo_ultimo_registro}`<br>",
            f"> **Status da Evidência:** `{handover.status_evidencia}`",
            "",
            "---",
            "",
            "## 1. Resumo da Produção do Turno",
            "",
            handover.resumo_producao,
            "",
            "## 2. Entregas de Software Realizadas",
            "",
        ]

        if handover.entregas_software:
            for e in handover.entregas_software:
                linhas.append(f"- {e}")
        else:
            linhas.append("- Nenhuma entrega de software concluída neste turno (apenas supervisão/consulta).")

        linhas.extend([
            "",
            "## 3. Bloqueios Ativos",
            "",
        ])

        if handover.bloqueios_ativos:
            for b in handover.bloqueios_ativos:
                linhas.append(f"- ⚠️ {b}")
        else:
            linhas.append("- Nenhum bloqueio ativo registrado.")

        linhas.extend([
            "",
            "## 4. Próxima Ação Recomendada",
            "",
            f"- {handover.proxima_acao_recomendada}",
            "",
            "---",
            "**Princípio Permanente:** AGY PRODUZ. CHATGPT SUPERVISIONA. HALLAN DECIDE.",
        ])

        return "\n".join(linhas)

    # -------------------------------------------------------------------------
    # Snapshot para Control Center
    # -------------------------------------------------------------------------

    def obter_snapshot_fabrica(self) -> dict[str, Any]:
        """Gera snapshot JSON para consumo desacoplado pelo Control Center."""
        with self._lock, self._file_lock:
            self._carregar_estado()

            agora_utc = datetime.now(timezone.utc)
            agora_fortaleza = agora_utc.astimezone(TZ_FORTALEZA).strftime("%Y-%m-%d %H:%M:%S %Z")

            total_turnos = len(self._turnos)
            turnos_sucesso = sum(1 for t in self._turnos if t.resultado == "SUCESSO")
            turnos_bloqueados = sum(1 for t in self._turnos if t.resultado == "BLOQUEADO")
            turnos_software = sum(1 for t in self._turnos if t.tipo_registro == "ENTREGA_SOFTWARE")
            turnos_supervisao = sum(1 for t in self._turnos if t.tipo_registro == "SUPERVISAO")

            return {
                "timestamp_utc": agora_utc.isoformat(),
                "timestamp_fortaleza": agora_fortaleza,
                "fuso_horario": "America/Fortaleza",
                "estatisticas": {
                    "total_turnos": total_turnos,
                    "turnos_sucesso": turnos_sucesso,
                    "turnos_bloqueados": turnos_bloqueados,
                    "turnos_entrega_software": turnos_software,
                    "turnos_supervisao": turnos_supervisao,
                },
                "turnos_recentes": [t.para_dicionario() for t in self._turnos[-10:]],
            }


def run_factory_cli(args: Any) -> int:
    """Ponto de entrada executável para os subcomandos 'ch factory' da Fatia F1."""
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
            print(f"[{t.inicio_fortaleza}] {t.turno_id} | {t.executor} | {t.repositorio} | {t.tipo_registro} | {t.resultado} | {t.missao_ref}")
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
            tipo_registro=getattr(args, "type", None),
        )
        if getattr(args, "json", False):
            print(json.dumps([t.para_dicionario() for t in turnos], indent=2, ensure_ascii=False))
            return 0

        print(f"=== Timeline Filtrada CH-FACTORY ({len(turnos)} eventos) ===")
        for t in turnos:
            status_symbol = "✅" if t.resultado == "SUCESSO" else ("⚠️" if t.resultado == "BLOQUEADO" else "ℹ️")
            tipo_tag = "[DEV]" if t.tipo_registro == "ENTREGA_SOFTWARE" else "[SUP]"
            print(f"{status_symbol} {tipo_tag} [{t.inicio_fortaleza}] {t.executor} @ {t.repositorio}: {t.missao_ref} -> {t.resultado}")
            if t.commits:
                print(f"     Commits: {', '.join(t.commits)}")
            if t.pr_numero:
                print(f"     PR: #{t.pr_numero}")
            if t.resumo:
                print(f"     Resumo: {t.resumo}")
        return 0

    if action == "handover":
        sainte = getattr(args, "sainte", "AGY")
        entrante = getattr(args, "entrante", "ChatGPT")
        shift_id = getattr(args, "shift_id", None)
        handover = factory.gerar_passagem_turno_minima(
            executor_sainte=sainte,
            executor_entrante=entrante,
            turno_recente_id=shift_id,
        )

        if getattr(args, "json", False):
            print(json.dumps(handover.para_dicionario(), indent=2, ensure_ascii=False))
            return 0

        md = factory.formatar_passagem_turno_markdown(handover)
        output_file = getattr(args, "output", None)
        if output_file:
            p = Path(output_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            print(f"Passagem de turno gravada em: {p}")
        else:
            print(md)
        return 0

    if action == "snapshot":
        snap = factory.obter_snapshot_fabrica()
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    print("Subcomando do factory não especificado. Use 'ch factory {history,timeline,handover,snapshot} --help'.", file=sys.stderr)
    return 1
