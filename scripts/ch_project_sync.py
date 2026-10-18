#!/usr/bin/env python3
"""Sincronizador conservador do Kanban C.H. DevFlow por GitHub CLI.

Em modo padrão, apenas lê o GitHub e exibe uma prévia.
Com --apply, preenche exclusivamente campos vazios de Esteira e Etapa CH.
Nunca interpreta etiquetas como autorização para executar agentes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import shutil
import subprocess
import sys
from typing import Callable

DEFAULT_OWNER = "hallanbrito"
DEFAULT_REPO = "hallanbrito/CHDevFlow"
DEFAULT_PROJECT = 2
LANES = {
    "ch:po": "Hallan",
    "ch:chatgpt": "ChatGPT",
    "ch:codex": "Codex",
    "ch:agy": "AGY",
}
MAX_ITEMS = 500
MAX_CHANGES = 100


@dataclass(frozen=True)
class Change:
    number: int
    title: str
    url: str
    field: str
    value: str


def _safe_error(output: str) -> str:
    """Evitar reproduzir tokens comuns que eventualmente apareçam em stderr."""
    output = re.sub(r"\b(?:gh[opusr]_|github_pat_)[A-Za-z0-9_]+", "[CREDENCIAL_OCULTADA]", output)
    return output.strip()[:1200]


def gh(*args: str) -> str:
    done = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False, timeout=45
    )
    if done.returncode:
        raise RuntimeError(
            "GitHub CLI falhou: " + _safe_error(done.stderr or done.stdout)
        )
    return done.stdout


def gh_json(*args: str) -> dict:
    raw = gh(*args)
    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub CLI retornou JSON vazio ou inválido.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Formato JSON inesperado do GitHub CLI.")
    return result


def issue_state(repo: str, number: int) -> str:
    data = gh_json(
        "issue", "view", str(number), "-R", repo,
        "--json", "number,state,url"
    )
    expected = f"https://github.com/{repo}/issues/{number}"
    if data.get("number") != number or data.get("url") != expected:
        raise RuntimeError(f"Issue #{number}: resposta do gh não corresponde ao alvo.")
    state = data.get("state")
    if state not in ("OPEN", "CLOSED"):
        raise RuntimeError(f"Issue #{number}: estado ausente ou inválido.")
    return state


def _field_value(item: dict, field_name: str) -> str | None:
    """O JSON do gh usa nomes de campos personalizados em minúsculas."""
    found = [(key, value) for key, value in item.items()
             if isinstance(key, str) and key.casefold() == field_name.casefold()]
    if len(found) > 1:
        raise RuntimeError(f"Campo duplicado no JSON: {field_name}.")
    if not found or found[0][1] is None:
        return None
    value = found[0][1]
    if not isinstance(value, str):
        raise RuntimeError(f"Campo {field_name} com valor de tipo inesperado.")
    return value.strip() or None


def build_plan(
    payload: dict,
    repo: str,
    state_reader: Callable[[str, int], str],
    issue_filter: int | None = None,
) -> tuple[list[Change], list[str]]:
    items = payload.get("items")
    count = payload.get("totalCount")
    if not isinstance(items, list) or not isinstance(count, int):
        raise RuntimeError("Resposta incompleta: items/totalCount ausentes.")
    if len(items) != count:
        raise RuntimeError(
            f"Project incompleto: {len(items)} itens recebidos, totalCount={count}. "
            "Não aplicar alterações em consulta parcial."
        )

    seen: set[int] = set()
    plan: list[Change] = []
    notes: list[str] = []
    found_target = issue_filter is None

    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("Item do Project não é objeto JSON.")
        content = item.get("content")
        if not isinstance(content, dict) or content.get("type") != "Issue":
            continue
        if content.get("repository") != repo:
            continue
        number = content.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise RuntimeError("Número de Issue inválido no Project.")
        if number in seen:
            raise RuntimeError(f"Issue #{number} duplicada no Project.")
        seen.add(number)
        if issue_filter is not None and number != issue_filter:
            continue
        found_target = True

        expected_url = f"https://github.com/{repo}/issues/{number}"
        if content.get("url") != expected_url:
            raise RuntimeError(f"Issue #{number}: URL de conteúdo inesperada.")
        labels = item.get("labels")
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            notes.append(f"#{number}: labels ausentes ou inválidas; ignorado.")
            continue
        if "ch:workflow" not in labels:
            notes.append(f"#{number}: sem ch:workflow; ignorado.")
            continue
        selected = {LANES[label] for label in labels if label in LANES}
        if len(selected) != 1:
            notes.append(
                f"#{number}: " +
                ("etiquetas de executor conflitantes" if selected else "sem etiqueta de executor") +
                "; nenhuma alteração."
            )
            continue

        lane = next(iter(selected))
        name = str(content.get("title") or item.get("title") or f"Issue #{number}")
        current_lane = _field_value(item, "Esteira")
        current_stage = _field_value(item, "Etapa CH")

        if current_lane is None:
            plan.append(Change(number, name, expected_url, "Esteira", lane))
        elif current_lane != lane:
            notes.append(f"#{number}: Esteira atual {current_lane!r} difere da etiqueta {lane!r}; preservar.")

        # Apenas o BACKLOG inicial. Jamais avançar etapas por conta própria.
        # Confirmar estado OPEN pela Issue, não pelo status Todo no Project.
        if current_stage is None:
            project_status = item.get("status")
            if project_status != "Todo":
                notes.append(f"#{number}: etapa vazia, status do Project não é Todo; preservar.")
                continue
            state = state_reader(repo, number)
            if state == "OPEN":
                plan.append(Change(number, name, expected_url, "Etapa CH", "BACKLOG"))
            else:
                notes.append(f"#{number}: Issue CLOSED; homologação requer decisão do PO.")

    if not found_target:
        raise RuntimeError(f"Issue #{issue_filter} não encontrada no Project/repositório.")
    return plan, notes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--project", type=int, default=DEFAULT_PROJECT)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--issue", type=int, help="Limitar a uma Issue para piloto.")
    parser.add_argument("--apply", action="store_true",
                        help="Aplicar apenas as atualizações exibidas na prévia.")
    args = parser.parse_args(argv)
    if (not re.fullmatch(r"[A-Za-z0-9-]+", args.owner)
            or not args.repo.startswith(args.owner + "/")
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo)
            or args.project < 1 or (args.issue is not None and args.issue < 1)):
        parser.error("Owner, repositório, Project ou Issue inválidos.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not shutil.which("gh"):
        print("BLOQUEADO: GitHub CLI (gh) não instalado.", file=sys.stderr)
        return 1
    print("C.H. DevFlow — sincronização conservadora do Kanban")
    print("Modo:", "APLICAR (apenas com --apply)" if args.apply else "PRÉVIA (sem escrita)")
    try:
        payload = gh_json(
            "project", "item-list", str(args.project),
            "--owner", args.owner, "--format", "json",
            "-L", str(MAX_ITEMS)
        )
        changes, notes = build_plan(payload, args.repo, issue_state, args.issue)
        for note in notes:
            print("ATENÇÃO:", note)
        for change in changes:
            print(f"#{change.number} | {change.field}: (vazio) -> {change.value} | {change.url}")
        if not changes:
            print("Sem atualizações necessárias. Nenhum campo alterado.")
            return 0
        print(f"Total de campos previstos: {len(changes)}")
        if not args.apply:
            print("Prévia concluída. Para aplicar: repita incluindo --apply.")
            return 0
        if len(changes) > MAX_CHANGES:
            raise RuntimeError(
                f"{len(changes)} alterações excedem o limite {MAX_CHANGES}. "
                "Use --issue para segmentar."
            )
        updated = 0
        for change in changes:
            gh(
                "project", "item-edit", str(args.project),
                "--owner", args.owner, "--url", change.url,
                "--field", change.field, "--value", change.value
            )
            updated += 1
            print(f"APLICADO: #{change.number} {change.field}={change.value}")
        print(f"Concluído: {updated} campos alterados. Rode novamente para confirmar idempotência.")
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print("BLOQUEADO: " + _safe_error(str(exc)), file=sys.stderr)
        print("Se houve --apply, confira o Project antes de repetir; pode existir aplicação parcial.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
