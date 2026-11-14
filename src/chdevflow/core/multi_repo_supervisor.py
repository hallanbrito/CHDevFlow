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
    obter_diretorio_dados,
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
from chdevflow.core.multi_repo_queue import (
    FilaSequencialMultiRepo,
    InterprocessFileLock,
    ItemFila,
    RegistroReserva,
    SupervisorLockError,
)
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
        autorizacoes: dict[str | int, ContratoAutorizacao] | None = None,
        exigir_autorizacao_formal: bool = True,
        lock_path: Path | None = None,
        forcar_live: bool = False,
    ) -> RelatorioCicloSupervisao:
        """Executa um ciclo completo de supervisão em modo DRY_RUN.

        Respeita rigorosamente a Decisão D05: ciclo pontual sem loop infinito.

        Args:
            snapshot_projeto: Fotografia pré-carregada do Project #2 (para modo offline).
            titulos_customizados: Dicionário opcional para nomes das tarefas na fila.
            run_id: Identificador opcional da execução.
            run_id_fornecido: Identificador opcional da execução (retrocompatibilidade).
            trace_simulado: Trace de simulação para testar o adaptador.
            autorizacoes: Contratos formais de autorização do PO por issue/repo.
            exigir_autorizacao_formal: Se True, exige contrato formal do PO para aprovação.
            lock_path: Caminho customizado para o arquivo de lock (usado em testes).
            forcar_live: Se True, força a consulta live ignorando snapshots.

        Returns:
            RelatorioCicloSupervisao com todos os dados do ciclo para auditoria.
        """
        inicio = datetime.now(timezone.utc).isoformat()
        id_efetivo = run_id or run_id_fornecido or f"multi-run-{uuid.uuid4().hex[:12]}"

        # Trava atômica interprocesso do ciclo completo (prevenção estrita de sobreposição)
        caminho_lock = lock_path or (obter_diretorio_dados() / "supervisor_multi_ciclo.lock")
        trava_ciclo = InterprocessFileLock(caminho_lock, max_age_seconds=900)

        try:
            trava_ciclo.acquire()
        except SupervisorLockError as exc:
            termino = datetime.now(timezone.utc).isoformat()
            parecer_bloqueio = ParecerElegibilidade(
                elegivel=False,
                status="CYCLE_OVERLAP_PREVENTED",
                motivo=f"Sobreposição de ciclo prevenida por lock atômico: {sanitizar_texto_segredos(str(exc))}",
                repositorio=REPOSITORIO_CANONICO,
                issue_number=None,
                esteira="AGY",
                etapa_ch=None,
                decisao_po=None,
                autonomia_ch=None,
                prioridade_ch=None,
                risco_ch=None,
            )
            return RelatorioCicloSupervisao(
                run_id=id_efetivo,
                inicio_utc=inicio,
                termino_utc=termino,
                intervalo_minutos=self.intervalo_minutos,
                modo_operacao=self.modo_operacao,
                execucao_autonoma_habilitada=EXECUCAO_AUTONOMA_HABILITADA,
                total_repositorios_verificados=0,
                total_itens_analisados=0,
                total_elegiveis_agy=0,
                total_bloqueados=1,
                total_outra_esteira=0,
                pareceres=(parecer_bloqueio,),
                itens_fila=(),
                reserva_efetuada=None,
                custo_adicional_brl=0.0,
                origem_dados="BLOQUEIO_CONCORRENCIA",
                repositorios_cadastrados=tuple(r.full_name for r in listar_repositorios_permitidos()),
                repositorios_consultados=(),
                repositorios_verificados=(),
            )

        try:
            # Passo 1: Leitura do Project #2 (LIVE ou FIXTURE explícita)
            origem_dados = "FIXTURE_OFFLINE"
            falha_leitura_externa: str | None = None
            if snapshot_projeto is not None and not forcar_live:
                origem_dados = "FIXTURE_OFFLINE"
                dados_project = snapshot_projeto
            else:
                origem_dados = "LIVE_GITHUB"
                leitor = self.leitor_gh
                if leitor is None:
                    try:
                        leitor = LeitorGitHub()
                    except Exception as exc:
                        falha_leitura_externa = f"Falha ao instanciar LeitorGitHub: {exc}"
                        leitor = None

                if leitor is not None:
                    try:
                        dados_project = leitor.listar_itens_projeto()
                    except Exception as exc:
                        falha_leitura_externa = str(exc)
                        origem_dados = "LIVE_GITHUB_FALHA"
                        dados_project = {"items": []}
                else:
                    origem_dados = "LIVE_GITHUB_FALHA"
                    dados_project = {"items": []}

            itens_raw = dados_project.get("items", []) if isinstance(dados_project, dict) else []
            if not isinstance(itens_raw, list):
                itens_raw = []

            # Passo 2, 3, 4 e 5: Verificação dos cartões e avaliação de governança
            pareceres: list[ParecerElegibilidade] = []
            elegiveis_agy: list[ParecerElegibilidade] = []
            total_bloqueados = 0
            total_outra_esteira = 0

            if falha_leitura_externa:
                pareceres.append(
                    ParecerElegibilidade(
                        elegivel=False,
                        status="BLOQUEADO_DADOS",
                        motivo=f"Falha de consulta LIVE ao GitHub Project #2: {sanitizar_texto_segredos(falha_leitura_externa)}",
                        repositorio=REPOSITORIO_CANONICO,
                        issue_number=None,
                        esteira="AGY",
                        etapa_ch=None,
                        decisao_po=None,
                        autonomia_ch=None,
                        prioridade_ch=None,
                        risco_ch=None,
                    )
                )
                total_bloqueados += 1

            for item in itens_raw:
                if not isinstance(item, dict):
                    continue

                parecer = self.verificador.avaliar_item_projeto(
                    item,
                    autorizacoes=autorizacoes,
                    exigir_contrato_po=exigir_autorizacao_formal,
                )
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
                trace_resultado = self.adaptador.executar_dry_run(
                    run_id=id_efetivo, trace_simulado=trace_simulado
                )
                self.fila.finalizar_reserva(
                    chave=reserva_efetuada.chave,
                    estado_final=trace_resultado.status,
                    motivo=f"Prévia DRY_RUN inerte concluída ({trace_resultado.reason}).",
                    custo_brl=0.0,
                )

            termino = datetime.now(timezone.utc).isoformat()

            # Identificação segregada de repositórios (Priority 5)
            repos_cadastrados = tuple(r.full_name for r in listar_repositorios_permitidos())
            if origem_dados == "LIVE_GITHUB" and not falha_leitura_externa:
                repos_consultados = repos_cadastrados
            elif snapshot_projeto is not None:
                repos_no_snapshot = set()
                for it in itens_raw:
                    if isinstance(it, dict):
                        c = it.get("content") if isinstance(it.get("content"), dict) else {}
                        r = c.get("repository") or it.get("repository")
                        if r:
                            try:
                                repos_no_snapshot.add(validar_repositorio_autorizado(str(r)).full_name)
                            except Exception:
                                pass
                repos_consultados = tuple(sorted(repos_no_snapshot)) or repos_cadastrados
            else:
                repos_consultados = (REPOSITORIO_CANONICO,)

            repos_verificados = tuple(
                sorted({p.repositorio for p in pareceres if p.repositorio and p.status != "BLOQUEADO_DADOS"})
            )

            # Passo 9 e 10: Consolidação do relatório estruturado RUC/1.0
            relatorio = RelatorioCicloSupervisao(
                run_id=id_efetivo,
                inicio_utc=inicio,
                termino_utc=termino,
                intervalo_minutos=self.intervalo_minutos,
                modo_operacao=self.modo_operacao,
                execucao_autonoma_habilitada=EXECUCAO_AUTONOMA_HABILITADA,
                total_repositorios_verificados=len(repos_verificados),
                total_itens_analisados=len(itens_raw),
                total_elegiveis_agy=len(elegiveis_agy),
                total_bloqueados=total_bloqueados,
                total_outra_esteira=total_outra_esteira,
                pareceres=tuple(pareceres),
                itens_fila=tuple(itens_fila),
                reserva_efetuada=reserva_efetuada,
                custo_adicional_brl=0.0,
                origem_dados=origem_dados,
                repositorios_cadastrados=repos_cadastrados,
                repositorios_consultados=repos_consultados,
                repositorios_verificados=repos_verificados,
            )

            return relatorio
        finally:
            trava_ciclo.release()


def run_multi_repo_supervisor_cli(argv: list[str] | None = None) -> int:
    """Executa o ciclo de supervisão multi-repositório a partir da linha de comando."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m chdevflow.core.multi_repo_supervisor",
        description="Ciclo horário supervisionado multi-repositório do CHDevFlow (CH-AUTO-MULTI-01).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Execução pontual única de ciclo (padrão seguro D05).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Modo simulação / dry-run sem execução de processos reais (padrão seguro).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Força consulta LIVE autenticada ao GitHub Project #2.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Caminho opcional para fixture JSON de itens do Project (testes offline).",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=None,
        help="Caminho para gravação do relatório RUC/1.0 gerado.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Exporta o resultado do ciclo em formato JSON estruturado.",
    )
    args = parser.parse_args(argv)

    snapshot = None
    if args.fixture and not args.live:
        with open(args.fixture, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

    # Se não houver fixture ou forçar live, tenta com LeitorGitHub (fail-closed se desautenticado)
    leitor = None
    if snapshot is None or args.live:
        try:
            leitor = LeitorGitHub()
        except Exception:
            leitor = None

    supervisor = SupervisorMultiRepo(
        intervalo_minutos=60,
        modo_operacao="DRY_RUN",
        leitor_gh=leitor,
    )

    relatorio = supervisor.executar_ciclo(snapshot_projeto=snapshot, forcar_live=args.live)
    ruc_md = relatorio.gerar_markdown_ruc()

    if args.output_report:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(ruc_md, encoding="utf-8")

    if args.json:
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


if __name__ == "__main__":
    import sys
    sys.exit(run_multi_repo_supervisor_cli(sys.argv[1:]))
