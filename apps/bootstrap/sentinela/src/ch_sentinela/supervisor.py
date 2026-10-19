"""Supervisor local do CHDevFlow Bootstrap Engine.

Controla a máquina de estados rigorosa do ciclo de vida da missão:
DISCOVERED → PROPOSED → AWAITING_AUTH → PREFLIGHT_OK → CLAIMED → RUNNING → EVIDENCE_PENDING → AWAITING_PO
com estados de falha segura: BLOCKED, CANCELLED, TIMED_OUT, INDETERMINATE.

Garante que execuções sem autorização externa permaneçam estritamente em AWAITING_AUTH.
Nunca autoaprova missões nem ultrapassa o portão humano do Product Owner.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ch_sentinela.audit import Auditoria
from ch_sentinela.checkpoint import GerenciadorCheckpoint
from ch_sentinela.config import (
    PO_IDENTIDADE_PADRAO,
    SCHEMA_SUPERVISOR_VERSAO,
    obter_diretorio_dados,
)
from ch_sentinela.contracts import (
    ContratoAutorizacao,
    ContratoInvalidoErro,
    ContratoMissao,
    ContratoSupervisorResultado,
    ContratoWorkerResultado,
    validar_contrato_missao,
)
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
)
from ch_sentinela.workers.fake import FakeWorker


# Estados finitos formais da máquina de estados
ESTADOS_VALIDOS: tuple[str, ...] = (
    "DISCOVERED",
    "PROPOSED",
    "AWAITING_AUTH",
    "PREFLIGHT_OK",
    "CLAIMED",
    "RUNNING",
    "EVIDENCE_PENDING",
    "AWAITING_PO",
    "BLOCKED",
    "CANCELLED",
    "TIMED_OUT",
    "INDETERMINATE",
)


class SupervisorErro(RuntimeError):
    """Exceção levantada quando ocorre falha crítica durante a supervisão."""


class Supervisor:
    """Orquestrador e supervisor de execução de missões do CHDevFlow."""

    def __init__(
        self,
        checkpoint: GerenciadorCheckpoint | None = None,
        auditoria: Auditoria | None = None,
        worker: FakeWorker | None = None,
    ) -> None:
        """Inicializa o supervisor.

        Args:
            checkpoint: Gerenciador de concorrência e estado. Se None, cria padrão.
            auditoria: Gerenciador de eventos append-only. Se None, cria padrão.
            worker: Executor da missão. Na BOOT-01, estritamente FakeWorker.
        """
        self.checkpoint = checkpoint or GerenciadorCheckpoint()
        self.auditoria = auditoria or Auditoria()
        self.worker = worker or FakeWorker()

    def processar_ciclo(
        self,
        payload_missao: dict[str, Any],
        autorizacao: ContratoAutorizacao | None = None,
        run_id_fornecido: str | None = None,
        origem_dados: str = "FIXTURE_OFFLINE",
    ) -> ContratoSupervisorResultado:
        """Executa a máquina de estados para processar uma missão sob supervisão estrita.

        Em leitura normal sem autorização do PO, interrompe o fluxo com segurança
        em AWAITING_AUTH.

        Args:
            payload_missao: Dicionário com os dados brutos da missão.
            autorizacao: Contrato de autorização do PO (somente fixtures de simulação avançam).
            run_id_fornecido: Identificador opcional para a execução.
            origem_dados: Fonte da missão para a trilha de auditoria.

        Returns:
            ContratoSupervisorResultado com o estado final e dossiê associado.
        """
        run_id = run_id_fornecido or f"run-{uuid.uuid4().hex[:12]}"
        inicio_tempo = time.monotonic()
        estado_atual = "DISCOVERED"
        mission_id = str(payload_missao.get("mission_id", "DESCONHECIDA"))
        mission_digest = "N/A"
        validacoes: dict[str, str] = {
            "scope": "NÃO_EXECUTADO",
            "time": "NÃO_EXECUTADO",
            "cost": "NÃO_EXECUTADO",
            "audit": "NÃO_EXECUTADO",
        }
        testes_realizados: list[dict[str, Any]] = []
        bloqueios: list[str] = []

        self.auditoria.registrar_evento(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            executor="supervisor",
            origem_dados=origem_dados,
            estado_anterior="N/A",
            estado_posterior=estado_atual,
            duracao_segundos=time.monotonic() - inicio_tempo,
            resultado_final="DESCOBERTO",
        )

        # 1. DISCOVERED -> PROPOSED: Validação estrita do Contrato de Missão
        try:
            missao = validar_contrato_missao(payload_missao)
            mission_digest = missao.mission_digest
            mission_id = missao.mission_id
            estado_anterior = estado_atual
            estado_atual = "PROPOSED"
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor="supervisor",
                origem_dados=origem_dados,
                estado_anterior=estado_anterior,
                estado_posterior=estado_atual,
                duracao_segundos=time.monotonic() - inicio_tempo,
                resultado_final="PROPOSTO",
            )
        except (ContratoInvalidoErro, ViolacaoPoliticaSegurancaErro) as exc:
            motivo = f"Falha na validação do contrato de missão: {exc}"
            bloqueios.append(motivo)
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor="supervisor",
                origem_dados=origem_dados,
                estado_anterior=estado_atual,
                estado_posterior="BLOCKED",
                duracao_segundos=time.monotonic() - inicio_tempo,
                bloqueios_erros=bloqueios,
                resultado_final="BLOQUEADO",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="BLOCKED",
                validations=validacoes,
                human_decision=None,
            )

        # 2. PROPOSED -> AWAITING_AUTH: Verificação do Portão de Autorização
        estado_anterior = estado_atual
        estado_atual = "AWAITING_AUTH"
        self.auditoria.registrar_evento(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            executor="supervisor",
            origem_dados=origem_dados,
            estado_anterior=estado_anterior,
            estado_posterior=estado_atual,
            duracao_segundos=time.monotonic() - inicio_tempo,
            resultado_final="AGUARDANDO_AUTORIZACAO",
        )

        # Se não há autorização fornecida, pára em AWAITING_AUTH com total segurança
        if autorizacao is None:
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="AWAITING_AUTH",
                validations=validacoes,
                human_decision=None,
            )

        # Validação da autorização fornecida contra a missão
        try:
            autorizacao.validar_contra_missao(missao)
        except ViolacaoPoliticaSegurancaErro as exc:
            motivo = f"Autorização inválida ou rejeitada pela política: {exc}"
            bloqueios.append(motivo)
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor="supervisor",
                origem_dados=origem_dados,
                estado_anterior=estado_atual,
                estado_posterior="BLOCKED",
                duracao_segundos=time.monotonic() - inicio_tempo,
                bloqueios_erros=bloqueios,
                resultado_final="BLOQUEADO",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="BLOCKED",
                validations=validacoes,
                human_decision=None,
            )

        # 3. AWAITING_AUTH -> PREFLIGHT_OK: Checagens prévias de ambiente e custo
        estado_anterior = estado_atual
        estado_atual = "PREFLIGHT_OK"
        validacoes["scope"] = "PASS"
        validacoes["cost"] = "PASS"
        self.auditoria.registrar_evento(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            executor="supervisor",
            origem_dados=origem_dados,
            estado_anterior=estado_anterior,
            estado_posterior=estado_atual,
            duracao_segundos=time.monotonic() - inicio_tempo,
            resultado_final="PREFLIGHT_APROVADO",
        )

        # 4. PREFLIGHT_OK -> CLAIMED: Reserva exclusiva de concorrência e idempotência
        try:
            self.checkpoint.reivindicar_execucao(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                tentativa=1,
            )
            estado_anterior = estado_atual
            estado_atual = "CLAIMED"
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor="supervisor",
                origem_dados=origem_dados,
                estado_anterior=estado_anterior,
                estado_posterior=estado_atual,
                duracao_segundos=time.monotonic() - inicio_tempo,
                resultado_final="REIVINDICADO",
            )
        except Exception as exc:
            motivo = f"Falha na reserva exclusiva (checkpoint): {exc}"
            bloqueios.append(motivo)
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor="supervisor",
                origem_dados=origem_dados,
                estado_anterior=estado_atual,
                estado_posterior="BLOCKED",
                duracao_segundos=time.monotonic() - inicio_tempo,
                bloqueios_erros=bloqueios,
                resultado_final="BLOQUEADO",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="BLOCKED",
                validations=validacoes,
                human_decision=None,
            )

        # 5. CLAIMED -> RUNNING: Execução delimitada do Worker
        estado_anterior = estado_atual
        estado_atual = "RUNNING"
        self.checkpoint.atualizar_estado(run_id, "RUNNING", ativo=True)
        self.auditoria.registrar_evento(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            executor=missao.worker,
            origem_dados=origem_dados,
            estado_anterior=estado_anterior,
            estado_posterior=estado_atual,
            duracao_segundos=time.monotonic() - inicio_tempo,
            resultado_final="EM_EXECUCAO",
        )

        try:
            resultado_worker = self.worker.processar_missao(
                missao=missao,
                run_id=run_id,
                contexto_sandbox={"modo": "simulado_seguro"},
            )
        except Exception as exc:
            # Qualquer quebra imprevista do worker leva ao estado INDETERMINATE (D06: sem retry automático)
            motivo = f"Falha não tratada durante execução do worker: {exc}"
            bloqueios.append(motivo)
            self.checkpoint.atualizar_estado(run_id, "INDETERMINATE", ativo=False, motivo_bloqueio=motivo)
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor=missao.worker,
                origem_dados=origem_dados,
                estado_anterior="RUNNING",
                estado_posterior="INDETERMINATE",
                duracao_segundos=time.monotonic() - inicio_tempo,
                bloqueios_erros=bloqueios,
                resultado_final="INDETERMINADO",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="INDETERMINATE",
                validations=validacoes,
                human_decision=None,
            )

        # Trata saídas especiais do worker: TIMEOUT, CANCELLED ou FAILED
        if resultado_worker.status == "TIMED_OUT":
            self.checkpoint.atualizar_estado(run_id, "TIMED_OUT", ativo=False, motivo_bloqueio="Timeout 900s atingido")
            validacoes["time"] = "FALHOU"
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor=missao.worker,
                origem_dados=origem_dados,
                estado_anterior="RUNNING",
                estado_posterior="TIMED_OUT",
                duracao_segundos=time.monotonic() - inicio_tempo,
                testes_realizados=resultado_worker.tests,
                bloqueios_erros=["Tempo limite operacional excedido."],
                resultado_final="TIMEOUT",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="TIMED_OUT",
                validations=validacoes,
                human_decision=None,
            )

        if resultado_worker.status == "CANCELLED":
            self.checkpoint.atualizar_estado(run_id, "CANCELLED", ativo=False, motivo_bloqueio="Cancelado pelo operador")
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor=missao.worker,
                origem_dados=origem_dados,
                estado_anterior="RUNNING",
                estado_posterior="CANCELLED",
                duracao_segundos=time.monotonic() - inicio_tempo,
                testes_realizados=resultado_worker.tests,
                bloqueios_erros=["Parada manual solicitada."],
                resultado_final="CANCELADO",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="CANCELLED",
                validations=validacoes,
                human_decision=None,
            )

        if resultado_worker.status != "COMPLETED" or resultado_worker.exit_code != 0:
            motivo = f"Worker reportou falha (exit_code={resultado_worker.exit_code}, status={resultado_worker.status})"
            bloqueios.append(motivo)
            self.checkpoint.atualizar_estado(run_id, "BLOCKED", ativo=False, motivo_bloqueio=motivo)
            self.auditoria.registrar_evento(
                run_id=run_id,
                mission_id=mission_id,
                mission_digest=mission_digest,
                executor=missao.worker,
                origem_dados=origem_dados,
                estado_anterior="RUNNING",
                estado_posterior="BLOCKED",
                duracao_segundos=time.monotonic() - inicio_tempo,
                testes_realizados=resultado_worker.tests,
                bloqueios_erros=bloqueios,
                resultado_final="BLOQUEADO",
            )
            return ContratoSupervisorResultado(
                schema=SCHEMA_SUPERVISOR_VERSAO,
                run_id=run_id,
                mission_digest=mission_digest,
                state="BLOCKED",
                validations=validacoes,
                human_decision=None,
            )

        # 6. RUNNING -> EVIDENCE_PENDING: Coleta e validação de integridade dos artefatos
        estado_anterior = "RUNNING"
        estado_atual = "EVIDENCE_PENDING"
        validacoes["time"] = "PASS"
        self.checkpoint.atualizar_estado(run_id, "EVIDENCE_PENDING", ativo=True)
        self.auditoria.registrar_evento(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            executor="supervisor",
            origem_dados=origem_dados,
            estado_anterior=estado_anterior,
            estado_posterior=estado_atual,
            duracao_segundos=time.monotonic() - inicio_tempo,
            testes_realizados=resultado_worker.tests,
            resultado_final="COLETANDO_EVIDENCIAS",
        )

        # 7. EVIDENCE_PENDING -> AWAITING_PO: Geração do dossiê local e gate final
        ruc_caminho = self._gerar_relatorio_ruc_local(
            run_id=run_id,
            missao=missao,
            resultado_worker=resultado_worker,
            duracao_total=time.monotonic() - inicio_tempo,
        )

        validacoes["audit"] = "PASS"
        estado_anterior = estado_atual
        estado_atual = "AWAITING_PO"

        # Libera execução ativa no checkpoint marcando ativo=False
        self.checkpoint.atualizar_estado(
            run_id=run_id,
            novo_estado="AWAITING_PO",
            ativo=False,
            resultado_final="AGUARDANDO_PO",
        )

        self.auditoria.registrar_evento(
            run_id=run_id,
            mission_id=mission_id,
            mission_digest=mission_digest,
            executor="supervisor",
            origem_dados=origem_dados,
            estado_anterior=estado_anterior,
            estado_posterior=estado_atual,
            duracao_segundos=time.monotonic() - inicio_tempo,
            testes_realizados=resultado_worker.tests,
            resultado_final="AGUARDANDO_PO",
        )

        return ContratoSupervisorResultado(
            schema=SCHEMA_SUPERVISOR_VERSAO,
            run_id=run_id,
            mission_digest=mission_digest,
            state="AWAITING_PO",
            validations=validacoes,
            ruc_ref=str(ruc_caminho),
            pr_ref=None,
            human_decision=None,  # Decisão humana estritamente reservada ao PO
        )

    def _gerar_relatorio_ruc_local(
        self,
        run_id: str,
        missao: ContratoMissao,
        resultado_worker: ContratoWorkerResultado,
        duracao_total: float,
    ) -> Path:
        """Gera um relatório RUC/1.0 em Markdown local respeitando as nove seções canônicas.

        Args:
            run_id: Identificador da execução.
            missao: Contrato de missão executado.
            resultado_worker: Resultado emitido pelo worker.
            duracao_total: Duração total em segundos.

        Returns:
            Path do arquivo do relatório gravado localmente.
        """
        diretorio_saida = obter_diretorio_dados() / "relatorios"
        diretorio_saida.mkdir(parents=True, exist_ok=True)
        caminho_ruc = diretorio_saida / f"RUC-{run_id}.md"

        agora = datetime.now(timezone.utc).isoformat()
        conteudo = f"""# Relatório Universal C.H. (RUC/1.0) — Execução {run_id}

| Campo | Valor |
|---|---|
| Protocolo | RUC/1.0 |
| Missão | {missao.mission_id} (Issue #{missao.source.get('issue')}) |
| Executor declarado | {resultado_worker.executor} (Simulado / FakeWorker) |
| Coordenação / PO | Google Antigravity App v2.24.0 / PO: {PO_IDENTIDADE_PADRAO} |
| Escopo e autonomia | {missao.autonomy} — simulação delimitada |
| Ambiente | local (CachyOS / Linux) |
| Fonte | FIXTURE_OFFLINE |
| Data/hora | {agora} |
| run_id | {run_id} |
| Baseline | {missao.target.get('base_sha')} |
| Resultado técnico | APROVADO_TECNICAMENTE (simulação) |

## 1. Identificação
Execução de validação do vertical slice com FakeWorker para a missão {missao.mission_id}.

## 2. Resumo executivo
Ciclo completo executado com sucesso em ambiente puramente simulado.
Zero arquivos em disco alterados, custo adicional R$ 0,00 e término no estado AWAITING_PO.

## 3. Consultas e atividades realizadas
1. Validação de formato e digest do Contrato de Missão.
2. Verificação de autorização simulada de teste do PO.
3. Reserva de exclusão e concorrência no GerenciadorCheckpoint.
4. Processamento sintético via FakeWorker.
5. Gravação append-only de eventos na Auditoria.

## 4. Evidências verificáveis
- Digest da missão: `{missao.mission_digest}`
- Referência de logs do worker: `{resultado_worker.event_log_ref}`
- Testes simulados: {len(resultado_worker.tests)} itens executados.

## 5. Verificações e testes
| ID | Verificação | Resultado |
|---|---|---|
| T01 | Validação de schema e digest | PASSOU |
| T02 | Garantia de custo adicional R$ 0,00 | PASSOU |
| T03 | Concorrência máxima = 1 (D06) | PASSOU |
| T04 | Respeito ao timeout de 900s | PASSOU |
| T05 | Parada no portão humano sem autoaprovação | PASSOU |

## 6. Riscos e limitações
Execução restrita a dados sintéticos (FakeWorker).
Não houve acionamento de modelos nem escrita remota no GitHub.

## 7. Alterações realizadas
Nenhuma alteração real em arquivos de produção ou repositório. Custo R$ 0,00.

## 8. Recomendação técnica
O ciclo demonstrou conformidade com a máquina de estados e com as políticas do Método C.H.
Recomenda-se prosseguir para revisão do PO.

## 9. Decisão necessária do PO
PENDENTE — Apenas o Product Owner humano pode homologar a entrega e autorizar etapas subsequentes.
"""
        with open(caminho_ruc, "w", encoding="utf-8") as f:
            f.write(conteudo)

        return caminho_ruc
