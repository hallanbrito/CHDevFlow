"""Supervisor central de orquestração multi-repositório do CHDevFlow.

Implementa o ciclo horário supervisionado de 10 passos:
1. Consulta o Project #2 por API autenticada (ou snapshot offline).
2. Confirma campos de governança e identidade das missões.
3. Consulta os repositórios cadastrados e suas Issues/PRs vinculadas.
4. Identifica exclusivamente missões atribuídas à Esteira AGY.
5. Verifica decisão explícita do PO, escopo, baseline, risco, custo e pré-requisitos.
6. Ordena missões elegíveis pela prioridade efetivamente verificada (P0 > P1 > P2 > P3).
7. Reserva uma única missão por vez, com lock persistente e idempotência.
8. Executa apenas dentro do contrato aprovado (em DRY_RUN inerte nesta fase).
9. Produz evidências auditáveis sem alterações reais.
10. Emite o Relatório Universal C.H. (RUC/1.0) para auditoria independente do ChatGPT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
import uuid

from ch_sentinela.config import (
    CUSTO_ADICIONAL_PERMITIDO_BRL,
    LIMITE_TEMPO_EXECUCAO_SEGUNDOS,
    MAXIMO_EXECUCOES_ATIVAS,
    PO_IDENTIDADE_PADRAO,
    REPOSITORIO_CANONICO,
)
from ch_sentinela.contracts import ContratoAutorizacao, ContratoWorkerResultado
from ch_sentinela.github_reader import LeitorGitHub
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    sanitizar_texto_segredos,
)
from chdevflow.core.dry_run_dispatcher import FixtureTrace, NormalizedTrace
from chdevflow.core.multi_repo_adapters import (
    EXECUCAO_AUTONOMA_HABILITADA,
    AdaptadorAGY,
    AdaptadorAgenteBase,
    obter_adaptador,
)
from chdevflow.core.multi_repo_queue import FilaSequencialMultiRepo, ItemFila, RegistroReserva
from chdevflow.core.multi_repo_registry import (
    listar_repositorios_ativos,
    listar_repositorios_permitidos,
    obter_repositorio,
    validar_repositorio_autorizado,
)
from chdevflow.core.multi_repo_reports import RelatorioCicloSupervisao
from chdevflow.core.multi_repo_verifier import (
    ParecerElegibilidade,
    VerificadorAutorizacaoMultiRepo,
)


INTERVALO_SUPERVISAO_PADRAO_MINUTOS = 60


class SupervisorMultiRepo:
    """Orquestrador do ciclo de supervisão multi-repositório com centralização no CHDevFlow."""

    def __init__(
        self,
        intervalo_minutos: int = INTERVALO_SUPERVISAO_PADRAO_MINUTOS,
        modo_operacao: str = "DRY_RUN",
        fila: FilaSequencialMultiRepo | None = None,
        verificador: VerificadorAutorizacaoMultiRepo | None = None,
        adaptador: AdaptadorAgenteBase | None = None,
        leitor_gh: LeitorGitHub | None = None,
    ) -> None:
        """Inicializa o supervisor multi-repositório.

        Args:
            intervalo_minutos: Intervalo do ciclo (padrão 60 minutos).
            modo_operacao: 'DRY_RUN' ou 'SIMULADO' (nesta fase, nenhum modo real é aceito).
            fila: Fila persistente. Se None, cria com caminho padrão.
            verificador: Validador fail-closed de governança. Se None, cria padrão.
            adaptador: Adaptador do agente (padrão AGY).
            leitor_gh: Leitor somente-leitura de API do GitHub.
        """
        self.intervalo_minutos = intervalo_minutos
        self.modo_operacao = modo_operacao
        self.fila = fila or FilaSequencialMultiRepo()
        self.verificador = verificador or VerificadorAutorizacaoMultiRepo()
        self.adaptador = adaptador or AdaptadorAGY()
        self.leitor_gh = leitor_gh

    def executar_ciclo(
        self,
        snapshot_projeto: dict[str, Any] | None = None,
        titulos_customizados: dict[str, str] | None = None,
        run_id: str | None = None,
        run_id_fornecido: str | None = None,
        trace_simulado: FixtureTrace | None = None,
    ) -> RelatorioCicloSupervisao:
        """Executa um ciclo completo de supervisão em modo DRY_RUN.

        Respeita rigorosamente a Decisão D05: ciclo pontual sem loop infinito.

        Args:
            snapshot_projeto: Fotografia pré-carregada do Project #2 (para modo offline).
            titulos_customizados: Dicionário opcional para nomes das tarefas na fila.
            run_id: Identificador opcional da execução.
            run_id_fornecido: Identificador opcional da execução (retrocompatibilidade).
            trace_simulado: Trace de simulação para testar o adaptador.

        Returns:
            RelatorioCicloSupervisao com todos os dados do ciclo para auditoria.
        """
        inicio = datetime.now(timezone.utc).isoformat()
        id_efetivo = run_id or run_id_fornecido or f"multi-run-{uuid.uuid4().hex[:12]}"

        # Passo 1: Leitura do Project #2
        if snapshot_projeto is not None:
            dados_project = snapshot_projeto
        elif self.leitor_gh is not None:
            dados_project = self.leitor_gh.listar_itens_projeto()
        else:
            # Sem leitor nem snapshot: fail-closed
            dados_project = {"items": []}

        itens_raw = dados_project.get("items", [])
        if not isinstance(itens_raw, list):
            itens_raw = []

        # Passo 2, 3, 4 e 5: Verificação dos cartões e avaliação de governança
        pareceres: list[ParecerElegibilidade] = []
        elegiveis_agy: list[ParecerElegibilidade] = []
        total_bloqueados = 0
        total_outra_esteira = 0

        for item in itens_raw:
            if not isinstance(item, dict):
                continue

            parecer = self.verificador.avaliar_item_projeto(item)
            pareceres.append(parecer)

            if parecer.elegivel:
                elegiveis_agy.append(parecer)
            elif parecer.status == "IGNORADO_OUTRA_ESTEIRA":
                total_outra_esteira += 1
            else:
                total_bloqueados += 1

        # Passo 6: Atualização da fila sequencial e ordenação estrita por prioridade
        itens_fila = self.fila.sincronizar_com_pareceres(elegiveis_agy, titulos_customizados)

        # Passo 7: Reserva exclusiva de uma única missão (lock e idempotência)
        reserva_efetuada: RegistroReserva | None = None
        if itens_fila:
            try:
                reserva_efetuada = self.fila.reservar_proxima(run_id=id_efetivo, attempt=1)
            except RuntimeError as exc:
                # Concorrência ativa detectada: preserva estado
                reserva_efetuada = self.fila.obter_reserva_ativa()

        # Passo 8: Execução estritamente em modo inerte (DRY_RUN)
        if reserva_efetuada and reserva_efetuada.estado == "CLAIMED":
            # Aciona o adaptador em modo dry-run sem processos externos reais
            trace_resultado = self.adaptador.executar_dry_run(
                run_id=id_efetivo, trace_simulado=trace_simulado
            )
            # Finaliza a reserva com o status do dry-run
            self.fila.finalizar_reserva(
                chave=reserva_efetuada.chave,
                estado_final=trace_resultado.status,
                motivo=f"Prévia DRY_RUN inerte concluída ({trace_resultado.reason}).",
                custo_brl=0.0,
            )

        termino = datetime.now(timezone.utc).isoformat()

        # Passo 9 e 10: Consolidação do relatório estruturado
        relatorio = RelatorioCicloSupervisao(
            run_id=id_efetivo,
            inicio_utc=inicio,
            termino_utc=termino,
            intervalo_minutos=self.intervalo_minutos,
            modo_operacao=self.modo_operacao,
            execucao_autonoma_habilitada=EXECUCAO_AUTONOMA_HABILITADA,
            total_repositorios_verificados=len(listar_repositorios_ativos()),
            total_itens_analisados=len(itens_raw),
            total_elegiveis_agy=len(elegiveis_agy),
            total_bloqueados=total_bloqueados,
            total_outra_esteira=total_outra_esteira,
            pareceres=tuple(pareceres),
            itens_fila=tuple(itens_fila),
            reserva_efetuada=reserva_efetuada,
            custo_adicional_brl=0.0,
        )

        return relatorio
