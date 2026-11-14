"""Interface de linha de comando principal do CHDevFlow (`ch`)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import subprocess

from chdevflow import __version__
from chdevflow.core.doctor import render_doctor_human, run_doctor
from chdevflow.core.evidence import render_evidence_human, run_verification
from chdevflow.core.init import run_init
from chdevflow.core.mission import create_mission
from chdevflow.core.intake import main as run_intake_check
from chdevflow.core.project import PRESETS, VALID_BACKENDS, VALID_DATABASES, VALID_FRONTENDS, create_project
from chdevflow.core.ruc import generate_ruc
from chdevflow.core.status import get_project_status, render_status_human
from chdevflow.core.submit import validate_and_submit
from chdevflow.core.tree import generate as generate_tree
from chdevflow.core.watch import run_watch
from chdevflow.core.factory import run_factory_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ch",
        description="CHDevFlow CLI — governança universal, execução especializada (Método C.H.)",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"chdevflow {__version__}",
        help="Exibe a versão instalada do CHDevFlow.",
    )

    subparsers = parser.add_subparsers(
        title="comandos",
        dest="command",
        metavar="<comando>",
    )

    # Subcomando: init
    parser_init = subparsers.add_parser(
        "init",
        help="Instala a fundação documental C.H. em um diretório de projeto.",
    )
    parser_init.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Caminho do diretório do projeto (padrão: diretório atual).",
    )
    parser_init.add_argument(
        "--profile",
        choices=["generic", "hallancraft"],
        default="generic",
        help="Perfil da fundação documental (padrão: generic).",
    )
    parser_init.add_argument(
        "--apply",
        action="store_true",
        help="Aplica as alterações no disco (o padrão é apenas simulação / dry-run).",
    )

    # Subcomando: new
    parser_new = subparsers.add_parser(
        "new",
        help="Cria um novo projeto governado pelo CHDevFlow com manifesto chdevflow.yaml.",
    )
    parser_new.add_argument(
        "name",
        type=str,
        help="Nome do projeto.",
    )
    parser_new.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório pai onde o projeto será criado (padrão: diretório atual).",
    )
    parser_new.add_argument(
        "--backend",
        choices=sorted(list(VALID_BACKENDS)),
        default="none",
        help="Tecnologia de backend.",
    )
    parser_new.add_argument(
        "--frontend",
        choices=sorted(list(VALID_FRONTENDS)),
        default="none",
        help="Tecnologia de frontend.",
    )
    parser_new.add_argument(
        "--database",
        choices=["postgres", "none"],
        default="none",
        help="Banco de dados planejado.",
    )
    parser_new.add_argument(
        "--preset",
        choices=sorted(list(PRESETS.keys())),
        default=None,
        help="Preset de combinação arquitetural (ex.: dotnet-angular).",
    )
    parser_new.add_argument(
        "--profile",
        choices=["generic", "hallancraft"],
        default="generic",
        help="Perfil da fundação documental.",
    )

    # Subcomando: status
    parser_status = subparsers.add_parser(
        "status",
        help="Verifica o estado local do projeto, Git, manifesto e governança C.H.",
    )
    parser_status.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_status.add_argument(
        "-s",
        "--strict",
        action="store_true",
        default=False,
        help="Modo estrito: falha com código 1 em caso de pendências estruturais obrigatórias.",
    )
    parser_status.add_argument(
        "--json",
        action="store_true",
        help="Exporta o status em formato JSON estruturado.",
    )

    # Subcomando: doctor
    parser_doctor = subparsers.add_parser(
        "doctor",
        help="Diagnostica ferramentas e pré-requisitos locais das stacks sem alterar o sistema.",
    )
    parser_doctor.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_doctor.add_argument(
        "--json",
        action="store_true",
        help="Exporta o diagnóstico em formato JSON estruturado.",
    )

    # Subcomando: verify
    parser_verify = subparsers.add_parser(
        "verify",
        help="Executa verificações definidas no manifesto e persiste evidências auditáveis.",
    )
    parser_verify.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_verify.add_argument(
        "--json",
        action="store_true",
        help="Exporta a evidência em formato JSON estruturado.",
    )
    parser_verify.add_argument(
        "--no-fail-fast",
        action="store_false",
        dest="fail_fast",
        default=True,
        help="Continua a execução dos checks subsequentes mesmo após falha.",
    )
    parser_verify.add_argument(
        "--trust",
        action="store_true",
        default=False,
        help="Concede e registra manifestação explícita de consentimento para o estado atual do projeto.",
    )
    parser_verify.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Apenas valida e exibe os comandos planejados sem disparar processos.",
    )
    parser_verify.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout máximo por comando de verificação em segundos (padrão: 120.0s).",
    )

    # CH-GOV-01: validação de entrada sem rede e sem mutação
    parser_intake = subparsers.add_parser("intake", help="Inspeciona entrada de missões (somente leitura).")
    intake_subs = parser_intake.add_subparsers(dest="intake_action", metavar="<ação>")
    intake_check = intake_subs.add_parser("check", help="Valida metadados de uma Issue, sem conceder autorização.")
    intake_check.add_argument("--event-json", type=Path, required=True)
    intake_check.add_argument("--json", action="store_true")
    intake_check.add_argument("--enforce", action="store_true")

    # Roteamento exclusivo: a admissao reside em scripts/ch_project_assist.py.
    parser_project = subparsers.add_parser(
        "project", help="Operacoes assistidas no GitHub Project, sem escrita por padrao."
    )
    project_subs = parser_project.add_subparsers(dest="project_action", metavar="<ação>")
    parser_project_admit = project_subs.add_parser(
        "admit", help="Previa e plano de admissao assistida de uma Issue."
    )
    parser_project_admit.add_argument("--issue", type=int, required=True)
    parser_project_admit.add_argument("--dry-run", action="store_true")
    parser_project_admit.add_argument("--autonomy", choices=["CH-0", "CH-1", "CH-2", "CH-3"])
    parser_project_admit.add_argument("--approval-comment", type=int)
    parser_project_admit.add_argument("--plan-file", type=Path)
    parser_project_admit.add_argument("--apply-plan", type=Path)
    parser_project_admit.add_argument("--confirm")
    parser_project_admit.add_argument("--audit-file", type=Path)

    # Subcomando: mission
    parser_mission = subparsers.add_parser(
        "mission",
        help="Gerencia e cria Fatias W locais sob governança C.H.",
    )
    mission_subs = parser_mission.add_subparsers(
        title="ações",
        dest="mission_action",
        metavar="<ação>",
    )
    parser_mission_new = mission_subs.add_parser(
        "new",
        help="Gera uma nova Fatia W a partir de modelo.",
    )
    parser_mission_new.add_argument(
        "title",
        type=str,
        help="Título da fatia/missão.",
    )
    parser_mission_new.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_mission_new.add_argument(
        "--executor",
        type=str,
        default=None,
        help="Executor da missão (obrigatório com --remote; padrão local: AGY).",
    )
    parser_mission_new.add_argument(
        "--autonomy",
        choices=["CH-0", "CH-1", "CH-2", "CH-3"],
        default=None,
        help="Nível de autonomia proposto (obrigatório com --remote; padrão local: CH-2).",
    )
    parser_mission_new.add_argument(
        "--remote",
        action="store_true",
        help="Cria também uma Issue no GitHub via 'gh' (requer gh autenticado).",
    )

    # Subcomando: ruc
    parser_ruc = subparsers.add_parser(
        "ruc",
        help="Gera o Relatório Universal C.H. (RUC/1.0) auditável a partir de evidências.",
    )
    parser_ruc.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_ruc.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Caminho de saída para gravação do RUC (padrão: docs/CH/RELATORIO-UNIVERSAL-CH-ULTIMO.md).",
    )
    parser_ruc.add_argument(
        "--title",
        type=str,
        default=None,
        help="Título ou contexto da missão relatada.",
    )

    # Subcomando: submit
    parser_submit = subparsers.add_parser(
        "submit",
        help="Valida a entrega da fatia e prepara submissão para revisão humana (AGUARDANDO_PO).",
    )
    parser_submit.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Diretório do projeto (padrão: diretório atual).",
    )
    parser_submit.add_argument(
        "--remote",
        action="store_true",
        help="Realiza push e abre/atualiza Draft PR no GitHub via gh.",
    )
    parser_submit.add_argument(
        "--title",
        type=str,
        default=None,
        help="Título do Draft PR.",
    )
    parser_submit.add_argument(
        "--body",
        type=str,
        default=None,
        help="Descrição da entrega para o Draft PR.",
    )
    parser_submit.add_argument(
        "--no-verify",
        action="store_true",
        help="Ignora verificação prévia (uso restrito e documentado).",
    )

    # Subcomando: watch
    parser_watch = subparsers.add_parser(
        "watch",
        help="Executa a observação pontual da Sentinela Python (estritamente --once conforme Decisão D05).",
    )
    parser_watch.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Execução pontual única (obrigatório na v0.1).",
    )
    parser_watch.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Modo somente leitura / observação.",
    )
    parser_watch.add_argument(
        "--fixture",
        type=str,
        default=None,
        help="Caminho opcional para fixture JSON de snapshot.",
    )

    # Subcomando: tree
    parser_tree = subparsers.add_parser(
        "tree",
        help="Gera ou atualiza docs/ARVORE_PROJETO.md sem expor conteúdos ou segredos.",
    )
    parser_tree.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Caminho da raiz do projeto (padrão: diretório atual).",
    )

    # Subcomando: factory (CH-FACTORY-01 / Fatia F1 / Issue #72)
    parser_factory = subparsers.add_parser(
        "factory",
        help="Gestão de turnos, histórico, timeline e passagem de turno da CH-FACTORY (Fatia F1 / Issue #72).",
    )
    parser_factory.add_argument(
        "--config-file",
        type=Path,
        default=None,
        help="Caminho para arquivo de estado JSON customizado da fábrica.",
    )
    factory_subs = parser_factory.add_subparsers(
        title="ações da fábrica",
        dest="factory_action",
        metavar="<ação>",
    )

    # factory history
    p_hist = factory_subs.add_parser("history", help="Exibe histórico de produção por turno.")
    p_hist.add_argument("--limit", type=int, default=None, help="Limita o número de turnos exibidos.")
    p_hist.add_argument("--json", action="store_true", default=False, help="Exporta em formato JSON.")

    # factory timeline
    p_time = factory_subs.add_parser("timeline", help="Exibe timeline de entregas com filtros multi-critério.")
    p_time.add_argument("--from-date", type=str, default=None, help="Data inicial (AAAA-MM-DD).")
    p_time.add_argument("--to-date", type=str, default=None, help="Data final (AAAA-MM-DD).")
    p_time.add_argument("--project", type=str, default=None, help="Filtro por nome/slug do projeto.")
    p_time.add_argument("--executor", type=str, default=None, help="Filtro por executor (AGY, ChatGPT, etc.).")
    p_time.add_argument("--result", type=str, default=None, help="Filtro por resultado (SUCESSO, BLOQUEADO, etc.).")
    p_time.add_argument("--type", type=str, default=None, choices=["SUPERVISAO", "ENTREGA_SOFTWARE"], help="Filtro por tipo de registro.")
    p_time.add_argument("--json", action="store_true", default=False, help="Exporta em formato JSON.")

    # factory handover
    p_hand = factory_subs.add_parser("handover", help="Gera passagem mínima de turno estruturada (F1 Handover).")
    p_hand.add_argument("--sainte", type=str, default="AGY", help="Executor sainte do turno (padrão: AGY).")
    p_hand.add_argument("--entrante", type=str, default="ChatGPT", help="Executor entrante do próximo turno.")
    p_hand.add_argument("--shift-id", type=str, default=None, help="ID específico do turno para referência.")
    p_hand.add_argument("--output", type=Path, default=None, help="Caminho para gravação do relatório Markdown.")
    p_hand.add_argument("--json", action="store_true", default=False, help="Exporta em formato JSON.")

    # factory snapshot
    p_snap = factory_subs.add_parser("snapshot", help="Exporta snapshot do estado da fábrica para o Control Center.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "init":
        try:
            run_init(destination=args.path, profile=args.profile, apply=args.apply)
            return 0
        except Exception as exc:
            print(f"Erro em 'ch init': {exc}", file=sys.stderr)
            return 1

    if args.command == "new":
        try:
            target = create_project(
                name=args.name,
                base_dir=args.path,
                backend=args.backend,
                frontend=args.frontend,
                database=args.database,
                preset=args.preset,
                profile=args.profile,
            )
            print(f"Projeto '{args.name}' criado com sucesso em: {target}")
            print("Próximos passos:")
            print(f"  cd {target.name}")
            print("  git init")
            print("  ch status")
            return 0
        except Exception as exc:
            print(f"Erro em 'ch new': {exc}", file=sys.stderr)
            return 1

    if args.command == "status":
        try:
            status_data = get_project_status(args.path, strict=args.strict)
            if args.json:
                print(json.dumps(status_data, indent=2, ensure_ascii=False))
            else:
                print(render_status_human(status_data))
            return status_data["expected_exit_code"]
        except Exception as exc:
            print(f"Erro em 'ch status': {exc}", file=sys.stderr)
            return 1

    if args.command == "doctor":
        try:
            report = run_doctor(args.path)
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print(render_doctor_human(report))
            return 0 if report["healthy"] else 1
        except Exception as exc:
            print(f"Erro em 'ch doctor': {exc}", file=sys.stderr)
            return 1

    if args.command == "verify":
        try:
            ev = run_verification(
                args.path,
                fail_fast=args.fail_fast,
                trust=getattr(args, "trust", False),
                dry_run=getattr(args, "dry_run", False),
                timeout_per_command=getattr(args, "timeout", 120.0),
            )
            if args.json:
                print(json.dumps(ev.to_dict(), indent=2, ensure_ascii=False))
            else:
                print(render_evidence_human(ev))
            return 0 if ev.overall_state == "PASS" else 1
        except Exception as exc:
            print(f"Erro em 'ch verify': {exc}", file=sys.stderr)
            return 1

    if args.command == "intake":
        if getattr(args, "intake_action", None) != "check":
            print("Uso: ch intake check --event-json <arquivo>", file=sys.stderr)
            return 1
        intake_argv = ["--event-json", str(args.event_json)]
        if args.json:
            intake_argv.append("--json")
        if args.enforce:
            intake_argv.append("--enforce")
        return run_intake_check(intake_argv)

    if args.command == "project":
        if args.project_action != "admit":
            print("Uso: ch project admit --issue <N> --dry-run", file=sys.stderr)
            return 1
        # Roteamento somente; o script concentra os gates e as mutations.
        script = Path(__file__).resolve().parents[2] / "scripts" / "ch_project_assist.py"
        if not script.is_file():
            print("Erro: admissao exige checkout/editable do CHDevFlow com scripts/ presente.",
                  file=sys.stderr)
            return 1
        command = [sys.executable, str(script), "admit", "--issue", str(args.issue)]
        if args.dry_run:
            command.append("--dry-run")
        for flag, value in (
            ("--autonomy", args.autonomy),
            ("--approval-comment", args.approval_comment),
            ("--plan-file", args.plan_file),
            ("--apply-plan", args.apply_plan),
            ("--confirm", args.confirm),
            ("--audit-file", args.audit_file),
        ):
            if value is not None:
                command.extend([flag, str(value)])
        try:
            return subprocess.run(command, check=False).returncode
        except OSError as exc:
            print(f"Erro ao iniciar admissao: {type(exc).__name__}", file=sys.stderr)
            return 1

    if args.command == "mission":
        if not getattr(args, "mission_action", None):
            print("Uso: ch mission new \"<título>\" [--remote]", file=sys.stderr)
            return 1
        if args.remote and (args.executor is None or args.autonomy is None):
            print("Erro em 'ch mission': --remote exige --executor e --autonomy "
                  "explicitamente.", file=sys.stderr)
            return 1
        # Compatibilidade: preservar os defaults históricos apenas em modo local.
        executor = args.executor if args.executor is not None else "AGY"
        autonomy = args.autonomy if args.autonomy is not None else "CH-2"
        try:
            path, msg = create_mission(
                title=args.title,
                project_path=args.path,
                executor=executor,
                autonomy=autonomy,
                remote=args.remote,
            )
            print(msg)
            return 0
        except Exception as exc:
            print(f"Erro em 'ch mission': {exc}", file=sys.stderr)
            return 1

    if args.command == "ruc":
        try:
            dest, _ = generate_ruc(
                project_path=args.path,
                output_path=args.output,
                mission_title=args.title,
            )
            print(f"Relatório Universal C.H. (RUC/1.0) gerado em: {dest}")
            return 0
        except Exception as exc:
            print(f"Erro em 'ch ruc': {exc}", file=sys.stderr)
            return 1

    if args.command == "submit":
        try:
            sub = validate_and_submit(
                project_path=args.path,
                remote=args.remote,
                title=args.title,
                body=args.body,
                skip_verify=args.no_verify,
            )
            print("=" * 60)
            print(f"CHDevFlow Submit — Entrega da Fatia: {sub['branch']}")
            print("=" * 60)
            print(f"  • Verificação     : {sub['verification']}")
            print(f"  • RUC gerado      : {sub['ruc_file']}")
            print(f"  • Estado final    : {sub['state']}")
            if sub["remote_executed"]:
                print(f"  • Remoto (GitHub) : {sub['remote_details']}")
            elif sub["state"] == "BLOQUEADO":
                print("  • Modo local      : Submissão em estado BLOQUEADO (verificação ignorada ou falha).")
                print("  • Restrição       : Submissão remota permanece expressamente PROIBIDA sem verificação PASS.")
            else:
                print("  • Modo local      : Validações concluídas. Use '--remote' para abrir Draft PR.")
            print("  • Nota de segurança: Nunca realiza merge. Homologação reservada ao PO.")
            print("=" * 60)
            return 0 if sub["state"] == "AGUARDANDO_PO" else 1
        except Exception as exc:
            print(f"Erro em 'ch submit': {exc}", file=sys.stderr)
            return 1

    if args.command == "watch":
        try:
            return run_watch(once=args.once, dry_run=args.dry_run, fixture=args.fixture)
        except Exception as exc:
            print(f"Erro em 'ch watch': {exc}", file=sys.stderr)
            return 1

    if args.command == "tree":
        try:
            dest, changed = generate_tree(args.path.resolve())
            print(f"{'Gerado' if changed else 'Sem alterações'}: {dest}")
            return 0
        except Exception as exc:
            print(f"Erro em 'ch tree': {exc}", file=sys.stderr)
            return 1

    if args.command == "factory":
        try:
            return run_factory_cli(args)
        except Exception as exc:
            print(f"Erro em 'ch factory': {exc}", file=sys.stderr)
            return 1

    print(f"Comando desconhecido: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
