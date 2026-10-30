#!/usr/bin/env python3
"""Exportador somente-leitura e auditável do GitHub Project #2 (Método C.H.).

Missão CH-ACCESS-01:
- Reutiliza recursos do CHDevFlow e Sentinela sem mutações no Project.
- Valida integridade em tempo de execução: totalCount de cartões e campos.
- Produz snapshot compacto, higienizado (sem corpos de issues, credenciais ou e-mails).
- Persistência com permissões restritas (0600) e fail-closed absoluto diante de erros.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Garante acesso aos pacotes internos do repositório
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_CORE = _REPO_ROOT / "src"
_SRC_SENTINELA = _REPO_ROOT / "apps" / "bootstrap" / "sentinela" / "src"
for _p in (_SRC_CORE, _SRC_SENTINELA):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from chdevflow.core.project_export import (
    DEFAULT_OUTPUT_PATH,
    ProjectExportError,
    ProjectExportIntegrityError,
    export_project_snapshot,
    save_snapshot_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ch_project_export.py",
        description="Exportador somente-leitura e seguro do GitHub Project #2 (Método C.H.).",
    )
    parser.add_argument(
        "--owner",
        type=str,
        default="hallanbrito",
        help="Proprietário do GitHub Project (padrão: hallanbrito).",
    )
    parser.add_argument(
        "--project",
        type=int,
        default=2,
        help="Número do GitHub Project (padrão: 2).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".ch_sentinela/project_snapshot.json"),
        help="Caminho do arquivo local privado para gravação do snapshot (padrão: .ch_sentinela/project_snapshot.json).",
    )
    parser.add_argument(
        "--fixture-items",
        type=Path,
        default=None,
        help="Caminho para fixture JSON de itens (apenas para testes offline).",
    )
    parser.add_argument(
        "--fixture-fields",
        type=Path,
        default=None,
        help="Caminho para fixture JSON de campos (apenas para testes offline).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Apenas valida a integridade ao vivo sem salvar arquivo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa a exportação e validação sem persistir no disco.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Imprime o snapshot JSON compacto diretamente na saída padrão (stdout).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Carregamento de fixtures offline explícitas, se fornecidas
    items_raw = None
    fields_raw = None
    source_override = None

    if args.fixture_items or args.fixture_fields:
        if not (args.fixture_items and args.fixture_fields):
            print(
                "ERRO: Para execução offline, informe obrigatoriamente tanto --fixture-items quanto --fixture-fields.",
                file=sys.stderr,
            )
            return 1
        try:
            with open(args.fixture_items, "r", encoding="utf-8") as f:
                items_raw = json.load(f)
            with open(args.fixture_fields, "r", encoding="utf-8") as f:
                fields_raw = json.load(f)
            source_override = "SNAPSHOT_OFFLINE"
        except Exception as exc:
            print(f"ERRO: Falha ao carregar fixtures offline: {exc}", file=sys.stderr)
            return 1

    # 2. Execução da exportação sob governança fail-closed
    try:
        snapshot = export_project_snapshot(
            owner=args.owner,
            project_number=args.project,
            items_raw=items_raw,
            fields_raw=fields_raw,
            source_override=source_override,
        )
    except (ProjectExportError, ProjectExportIntegrityError) as exc:
        print("=" * 60, file=sys.stderr)
        print("CHDevFlow — Exportador do GitHub Project #2: BLOQUEADO", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"  • Diagnóstico : {exc}", file=sys.stderr)
        print("  • Governança  : Falha fechada (fail-closed). Sem fallback para fixtures automáticas.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERRO INESPERADO no exportador: {exc}", file=sys.stderr)
        return 1

    integ = snapshot.get("integrity", {})
    origem = snapshot.get("source", "DESCONHECIDA")

    # 3. Tratamento de saídas específicas
    if args.stdout:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    if args.validate_only or args.dry_run:
        print("=" * 60)
        print("CHDevFlow — Validação de Integridade do GitHub Project #2")
        print("=" * 60)
        print(f"  • Origem           : {origem}")
        print(f"  • Total de Cartões : {integ.get('total_items_received')} recebidos / {integ.get('total_items_reported')} reportados (OK)")
        print(f"  • Total de Campos  : {integ.get('total_fields_received')} recebidos / {integ.get('total_fields_reported')} reportados (OK)")
        print(f"  • Unicidade de IDs : {'OK' if integ.get('unique_card_ids') else 'FALHA'}")
        print(f"  • Anomalias        : {len(integ.get('anomalies', []))} detectadas")
        print(f"  • Digest SHA-256   : {integ.get('snapshot_digest')}")
        print(f"  • Modo             : {'VALIDATE_ONLY' if args.validate_only else 'DRY_RUN'}")
        print("  • Estado           : APROVADO_TECNICAMENTE")
        print("=" * 60)
        return 0

    # 4. Gravação padrão com permissões restritas (0600)
    try:
        caminho_salvo = save_snapshot_file(snapshot, args.output)
    except Exception as exc:
        print(f"ERRO ao persistir arquivo de snapshot seguro: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("CHDevFlow — Exportação do GitHub Project #2 Concluída")
    print("=" * 60)
    print(f"  • Origem           : {origem}")
    print(f"  • Horário UTC      : {snapshot.get('captured_at_utc')}")
    print(f"  • Arquivo Gravado  : {caminho_salvo} (Permissões 0600)")
    print(f"  • Total de Cartões : {integ.get('total_items_received')} / {integ.get('total_items_reported')}")
    print(f"  • Total de Campos  : {integ.get('total_fields_received')} / {integ.get('total_fields_reported')}")
    print(f"  • Unicidade de IDs : {'OK' if integ.get('unique_card_ids') else 'FALHA'}")
    print(f"  • Anomalias        : {len(integ.get('anomalies', []))} detectadas")
    print(f"  • Digest SHA-256   : {integ.get('snapshot_digest')}")
    print("  • Estado           : APROVADO_TECNICAMENTE")
    print("  • Governança       : Somente leitura. Nenhuma alteração aplicada ao Project.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
