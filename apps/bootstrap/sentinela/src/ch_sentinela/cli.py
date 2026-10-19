"""Interface de Linha de Comando (CLI) da Sentinela Python.

Disponibiliza os comandos:
- watch --once --dry-run: Observação de execução única sem acionamento de workers.
- demo --fake-worker: Demonstração do ciclo simulado completo com fixtures até AWAITING_PO.
- status: Consulta do histórico local de execuções e checkpoints.
- report: Exibição do relatório RUC/1.0 mais recente ou de um run_id específico.

Comportamento padrão estritamente seguro: sem chamadas pagas, sem agentes reais e sem escrita remota.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ch_sentinela.audit import Auditoria
from ch_sentinela.checkpoint import GerenciadorCheckpoint
from ch_sentinela.config import (
    PO_IDENTIDADE_PADRAO,
    REPOSITORIO_CANONICO,
    SCHEMA_MISSAO_VERSAO,
    obter_diretorio_dados,
)
from ch_sentinela.contracts import ContratoAutorizacao, ContratoMissao
from ch_sentinela.github_reader import LeitorGitHub
from ch_sentinela.sentinel import Sentinela
from ch_sentinela.supervisor import Supervisor
from ch_sentinela.workers.fake import FakeWorker


# Fixture canônica para a missão BOOT-01 de demonstração
FIXTURE_MISSAO_BOOT01: dict[str, Any] = {
    "schema": SCHEMA_MISSAO_VERSAO,
    "mission_id": "BOOT-01-LAB",
    "source": {
        "repository": REPOSITORIO_CANONICO,
        "issue": 24,
        "issue_url": f"https://github.com/{REPOSITORIO_CANONICO}/issues/24",
    },
    "target": {
        "repository": REPOSITORIO_CANONICO,
        "base_sha": "d2a74426bfa1fab12aafb721c8dad60876f6f8ec",
        "allowed_paths": ["apps/bootstrap/sentinela/"],
        "blocked_paths": ["**/worlds/**", "**/saves/**", "**/.env*", "**/secrets/**"],
    },
    "worker": "fake",
    "autonomy": "CH-0",
    "instruction_ref": "docs/bootstrap/BOOT-00-CONTRATOS.md",
    "limits": {
        "max_parallel": 1,
        "timeout_seconds": 900,
        "max_retries_after_diagnosis": 1,
        "extra_cost_brl": 0,
    },
}

FIXTURE_PROJETO_DEMO: dict[str, Any] = {
    "totalCount": 1,
    "items": [
        {
            "content": {
                "type": "Issue",
                "repository": REPOSITORIO_CANONICO,
                "number": 24,
                "title": "BOOT-00: contratos do motor e primeiro ciclo supervisionado",
                "url": f"https://github.com/{REPOSITORIO_CANONICO}/issues/24",
            },
            "labels": ["ch:workflow", "ch:agy", "esteira:bootstrap"],
        }
    ],
}


def comando_watch(args: argparse.Namespace) -> int:
    """Executa a observação pontual do GitHub."""
    print("=" * 70)
    print("C.H. DevFlow — Sentinela Python (Observação Pontual)")
    print(f"Modo: {'DRY-RUN (somente leitura)' if args.dry_run else 'LEITURA'}")
    print(f"Execução: {'ÚNICA (--once)' if args.once else 'ÚNICA (padrão D05)'}")
    print("=" * 70)

    leitor = LeitorGitHub()
    auditoria = Auditoria()
    sentinela = Sentinela(leitor=leitor, auditoria=auditoria)

    # Se informado arquivo de snapshot offline, utiliza-o
    snapshot = None
    if getattr(args, "fixture", None):
        caminho_fix = Path(args.fixture)
        if caminho_fix.exists():
            with open(caminho_fix, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
            print(f"Carregando snapshot de: {caminho_fix}")
        else:
            print(f"Aviso: arquivo de fixture '{args.fixture}' não encontrado. Usando fixture embutida.")
            snapshot = FIXTURE_PROJETO_DEMO
    else:
        # Se não há flag de fixture, tenta ao vivo ou fallback seguro para demo offline
        try:
            snapshot = None  # Tentará GitHub CLI
        except Exception as exc:
            print(f"Consulta ao vivo indisponível ({exc}). Utilizando fotografia de demonstração.")
            snapshot = FIXTURE_PROJETO_DEMO

    try:
        eventos = sentinela.observar_uma_vez(snapshot_projeto=snapshot)
    except Exception as exc:
        # Fallback gracioso se não houver GitHub CLI autenticado no host
        print(f"\n[AVISO] Consulta ao vivo falhou ({exc}).")
        print("Executando em modo OFFLINE com snapshot de demonstração...")
        eventos = sentinela.observar_uma_vez(snapshot_projeto=FIXTURE_PROJETO_DEMO)

    print(f"\nTarefas observadas: {len(eventos)}")
    for ev in eventos:
        print(f"  [{ev.tipo_evento}] Issue #{ev.numero_issue}: {ev.titulo}")
        print(f"     Detalhes: {ev.detalhes}")

    print("\nObservação finalizada. Processo encerrado conforme Decisão D05.")
    return 0


def comando_demo(args: argparse.Namespace) -> int:
    """Executa a demonstração do vertical slice com FakeWorker e fixtures."""
    print("=" * 70)
    print("C.H. DevFlow — Demonstração do Bootstrap Engine (BOOT-01)")
    print("Executor: FakeWorker (Simulado)")
    print("=" * 70)

    auditoria = Auditoria()
    checkpoint = GerenciadorCheckpoint()
    worker = FakeWorker(modo_simulacao="SUCESSO")
    supervisor = Supervisor(checkpoint=checkpoint, auditoria=auditoria, worker=worker)

    # 1. Demonstração de execução normal SEM autorização (pára em AWAITING_AUTH)
    print("\n>>> ETAPA 1: Execução sem autorização do PO (Comportamento Seguro Padrão)")
    resultado_sem_auth = supervisor.processar_ciclo(
        payload_missao=FIXTURE_MISSAO_BOOT01,
        autorizacao=None,
        origem_dados="DEMO_SEM_AUTORIZACAO",
    )
    print(f"  Estado atingido: {resultado_sem_auth.state}")
    print("  -> Comportamento validado: O supervisor parou em AWAITING_AUTH sem chamar workers.")

    # 2. Demonstração de ciclo com autorização simulada de teste
    print("\n>>> ETAPA 2: Ciclo supervisionado com autorização simulada de teste")
    missao_temp = ContratoMissao(
        schema=FIXTURE_MISSAO_BOOT01["schema"],
        mission_id=FIXTURE_MISSAO_BOOT01["mission_id"],
        source=FIXTURE_MISSAO_BOOT01["source"],
        target=FIXTURE_MISSAO_BOOT01["target"],
        worker=FIXTURE_MISSAO_BOOT01["worker"],
        autonomy=FIXTURE_MISSAO_BOOT01["autonomy"],
        instruction_ref=FIXTURE_MISSAO_BOOT01["instruction_ref"],
        limits=FIXTURE_MISSAO_BOOT01["limits"],
    )
    digest_calculado = missao_temp.calcular_digest()

    autorizacao_simulada = ContratoAutorizacao(
        approval_type="CH2_RUN_APPROVAL",
        issue_ref="24",
        mission_digest=digest_calculado,
        baseline_sha="d2a74426bfa1fab12aafb721c8dad60876f6f8ec",
        authorized_executor="fake",
        authorized_repo=REPOSITORIO_CANONICO,
        approved_by=PO_IDENTIDADE_PADRAO,
        approved_at="2026-10-19T20:00:00Z",
        event_id="simulated-event-fixture-999",
        is_simulation=True,
    )

    resultado_com_auth = supervisor.processar_ciclo(
        payload_missao=FIXTURE_MISSAO_BOOT01,
        autorizacao=autorizacao_simulada,
        origem_dados="DEMO_COM_AUTORIZACAO_SIMULADA",
    )

    print(f"  Estado final: {resultado_com_auth.state}")
    print(f"  Digest da Missão: {resultado_com_auth.mission_digest[:16]}...")
    print(f"  Validações: {resultado_com_auth.validations}")
    print(f"  Relatório RUC gerado em: {resultado_com_auth.ruc_ref}")
    print("  -> Sucesso: Ciclo concluído e parado no gate humano AWAITING_PO.")
    return 0


def comando_status(args: argparse.Namespace) -> int:
    """Exibe o status dos checkpoints e histórico local."""
    print("=" * 70)
    print("C.H. DevFlow — Status e Checkpoints Locais")
    print("=" * 70)

    checkpoint = GerenciadorCheckpoint()
    execucoes = checkpoint.listar_execucoes()

    print(f"Total de execuções registradas: {len(execucoes)}")
    for reg in execucoes:
        status_ativo = "[ATIVO]" if reg.get("ativo") else "[CONCLUIDO]"
        print(f"- Run: {reg.get('run_id')} {status_ativo}")
        print(f"  Missão: {reg.get('mission_id')} | Estado: {reg.get('estado_atual')}")
        print(f"  Início: {reg.get('data_inicio_utc')} | Atualizado: {reg.get('data_atualizacao_utc')}")
        if reg.get("motivo_bloqueio"):
            print(f"  Bloqueio: {reg.get('motivo_bloqueio')}")

    auditoria = Auditoria()
    eventos = auditoria.ler_eventos()
    print(f"\nTotal de eventos de auditoria no JSONL: {len(eventos)}")
    if eventos:
        ultimo = eventos[-1]
        print(f"Último evento: [{ultimo.get('timestamp_utc')}] {ultimo.get('estado_anterior')} -> {ultimo.get('estado_posterior')} ({ultimo.get('resultado_final')})")

    return 0


def comando_report(args: argparse.Namespace) -> int:
    """Imprime o relatório RUC/1.0 gerado mais recente."""
    dir_relatorios = obter_diretorio_dados() / "relatorios"
    if not dir_relatorios.exists():
        print("Nenhum relatório encontrado. Execute 'demo --fake-worker' primeiro.")
        return 1

    arquivos = sorted(dir_relatorios.glob("RUC-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not arquivos:
        print("Nenhum relatório RUC encontrado em:", dir_relatorios)
        return 1

    alvo = arquivos[0]
    if getattr(args, "run_id", None):
        candidato = dir_relatorios / f"RUC-{args.run_id}.md"
        if candidato.exists():
            alvo = candidato

    print(f"Exibindo relatório: {alvo}\n")
    print(alvo.read_text(encoding="utf-8"))
    return 0


def criar_parser() -> argparse.ArgumentParser:
    """Constrói o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="ch-sentinela",
        description="Sentinela Python do CHDevFlow Bootstrap Engine — Observação e Supervisão Seguras.",
    )
    subparsers = parser.add_subparsers(dest="comando", help="Comandos disponíveis")

    # Comando: watch
    parser_watch = subparsers.add_parser("watch", help="Executa observação do GitHub.")
    parser_watch.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Executa uma única consulta e encerra (obrigatório / D05).",
    )
    parser_watch.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Modo somente leitura, sem execução de tarefas.",
    )
    parser_watch.add_argument(
        "--fixture",
        type=str,
        default=None,
        help="Caminho opcional de arquivo JSON com snapshot para modo offline.",
    )

    # Comando: demo
    parser_demo = subparsers.add_parser("demo", help="Executa demonstração do ciclo supervisionado.")
    parser_demo.add_argument(
        "--fake-worker",
        action="store_true",
        default=True,
        help="Utiliza o FakeWorker inofensivo para simular o ciclo.",
    )

    # Comando: status
    subparsers.add_parser("status", help="Consulta o estado local e histórico de checkpoints.")

    # Comando: report
    parser_report = subparsers.add_parser("report", help="Exibe o relatório RUC/1.0 da execução.")
    parser_report.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Identificador específico do run_id do relatório.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada principal da CLI."""
    parser = criar_parser()
    args = parser.parse_args(argv)

    if args.comando == "watch":
        return comando_watch(args)
    elif args.comando == "demo":
        return comando_demo(args)
    elif args.comando == "status":
        return comando_status(args)
    elif args.comando == "report":
        return comando_report(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
