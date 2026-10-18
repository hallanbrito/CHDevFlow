#!/usr/bin/env python3
"""KSYNC-03: inspector e aplicador assistido do Project #2.

Sem escrita remota por padrão. Aplicação requer plano pinado, comparação
com estado LIVE, confirmação humana interativa e autorização externa do PO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import ch_project_sync as legacy

OWNER = "hallanbrito"
REPO = "hallanbrito/CHDevFlow"
PROJECT = 2
SCHEMA = "CHDEVFLOW-KSYNC03/1"
MAX_ISSUES = 5
MAX_FIELDS = 10


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def fetch_project():
    return legacy.gh_json(
        "project", "item-list", str(PROJECT), "--owner", OWNER,
        "--format", "json", "-L", str(legacy.MAX_ITEMS)
    )


def parse_numbers(raw):
    try:
        numbers = [int(x.strip()) for x in raw.split(",")]
    except ValueError as exc:
        raise ValueError("Issues devem ser inteiros separados por vírgula") from exc
    if not numbers or any(n <= 0 for n in numbers) or len(set(numbers)) != len(numbers):
        raise ValueError("Issues inválidas ou repetidas")
    if len(numbers) > MAX_ISSUES:
        raise ValueError(f"Máximo de {MAX_ISSUES} Issues por lote")
    return sorted(numbers)


def inspect(payload, selected=None, state_reader=None):
    """Inspeção pura exceto leitura de estados via callback; ignora CLOSED."""
    state_reader = state_reader or legacy.issue_state
    items, count = payload.get("items"), payload.get("totalCount")
    if not isinstance(items, list) or type(count) is not int or len(items) != count:
        raise ValueError("Project incompleto: items/totalCount inválidos")
    if count > legacy.MAX_ITEMS:
        raise ValueError("Project excede limite de leitura")
    chosen = set(selected) if selected is not None else None
    found, changes, notes, snapshots = set(), [], [], {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Item JSON inválido")
        c = item.get("content")
        if not isinstance(c, dict) or c.get("type") != "Issue" or c.get("repository") != REPO:
            continue
        n = c.get("number")
        if type(n) is not int or n < 1 or n in found:
            raise ValueError("Issue duplicada ou inválida")
        found.add(n)
        if c.get("url") != f"https://github.com/{REPO}/issues/{n}":
            raise ValueError(f"#{n}: URL incompatível")
        if chosen is not None and n not in chosen:
            continue
        labels = item.get("labels")
        if not isinstance(labels, list) or not all(isinstance(s, str) for s in labels):
            notes.append(f"#{n}: labels inválidas; bloqueada")
            continue
        if "ch:workflow" not in labels:
            notes.append(f"#{n}: sem ch:workflow; preservada")
            continue
        lanes = {legacy.LANES[x] for x in labels if x in legacy.LANES}
        if len(lanes) != 1:
            notes.append(f"#{n}: executor ausente ou ambíguo; bloqueada")
            continue
        lane = next(iter(lanes))
        state = state_reader(REPO, n)
        if state not in ("OPEN", "CLOSED"):
            raise ValueError(f"#{n}: estado não verificável")
        if state == "CLOSED":
            notes.append(f"#{n}: CLOSED; exige decisão humana, nenhuma proposta")
            continue
        current_lane = legacy._field_value(item, "Esteira")
        current_stage = legacy._field_value(item, "Etapa CH")
        if current_lane is not None and current_lane != lane:
            notes.append(f"#{n}: conflito Esteira={current_lane!r} x etiqueta={lane!r}; preservada")
            continue
        if item.get("status") != "Todo":
            notes.append(f"#{n}: status não é Todo; nenhuma proposta inicial")
            continue
        snapshots[str(n)] = digest(item)
        if current_lane is None:
            changes.append({"number": n, "field": "Esteira", "value": lane,
                            "url": c["url"]})
        if current_stage is None:
            changes.append({"number": n, "field": "Etapa CH", "value": "BACKLOG",
                            "url": c["url"]})
    if chosen is not None and not chosen.issubset(found):
        raise ValueError("Uma ou mais Issues não estão neste Project/repositório")
    return sorted(changes, key=lambda x: (x["number"], x["field"])), notes, snapshots


def make_plan(payload, numbers, state_reader=None):
    changes, notes, snapshots = inspect(payload, numbers, state_reader)
    if notes:
        raise ValueError("Lote inseguro: " + "; ".join(notes))
    if not changes:
        raise ValueError("Lote sem alterações elegíveis")
    if len(changes) > MAX_FIELDS or {x["number"] for x in changes} != set(numbers):
        raise ValueError("Lote excede limite ou contém Issue sem alteração")
    base = {"schema": SCHEMA, "owner": OWNER, "repo": REPO,
            "project": PROJECT, "issues": list(numbers),
            "changes": changes, "snapshots": snapshots}
    return {**base, "digest": digest(base)}


def validate_plan(data):
    if not isinstance(data, dict) or set(data) != {
        "schema", "owner", "repo", "project", "issues", "changes", "snapshots", "digest"
    }:
        raise ValueError("Plano inválido")
    if (data["schema"], data["owner"], data["repo"], data["project"]) != (
        SCHEMA, OWNER, REPO, PROJECT
    ):
        raise ValueError("Destino do plano divergente")
    issues = data["issues"]
    if (not isinstance(issues, list) or not issues
            or any(type(n) is not int or n <= 0 for n in issues)
            or issues != sorted(set(issues)) or len(issues) > MAX_ISSUES):
        raise ValueError("Escopo de Issues inválido")
    if not isinstance(data["digest"], str) or len(data["digest"]) != 64:
        raise ValueError("Digest inválido")
    if digest({k: v for k, v in data.items() if k != "digest"}) != data["digest"]:
        raise ValueError("Plano alterado desde geração")
    if (not isinstance(data["changes"], list) or not data["changes"]
            or len(data["changes"]) > MAX_FIELDS):
        raise ValueError("Mudanças inválidas")
    allowed = {"Esteira": set(legacy.LANES.values()), "Etapa CH": {"BACKLOG"}}
    seen = set()
    for entry in data["changes"]:
        if not isinstance(entry, dict) or set(entry) != {"number", "field", "value", "url"}:
            raise ValueError("Entrada de plano inválida")
        n, field = entry["number"], entry["field"]
        if (n not in issues or field not in allowed or entry["value"] not in allowed[field]
                or entry["url"] != f"https://github.com/{REPO}/issues/{n}"
                or (n, field) in seen):
            raise ValueError("Mudança fora da allowlist")
        seen.add((n, field))
    if (not isinstance(data["snapshots"], dict)
            or set(data["snapshots"]) != {str(n) for n in issues}
            or any(not isinstance(v, str) or len(v) != 64 for v in data["snapshots"].values())):
        raise ValueError("Snapshots inválidos")
    return issues


def apply_plan(data, confirm, *, reader=fetch_project, state_reader=None,
               writer=None, prompt=input, interactive=None):
    """Só após confirmação no host; jamais assume que CLI comprova identidade do PO."""
    issues = validate_plan(data)
    if confirm != data["digest"]:
        raise ValueError("Digest não confirmado")
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        raise ValueError("Aplicação requer terminal interativo; sem cron/CI")
    fresh = make_plan(reader(), issues, state_reader)
    if fresh != data:
        raise ValueError("Estado remoto mudou: regenere o plano; nada aplicado")
    phrase = "APROVO KSYNC-03 " + data["digest"][:12]
    if prompt(f"Digite exatamente '{phrase}' após autorização externa do PO: ") != phrase:
        raise ValueError("Confirmação humana ausente")
    writer = writer or legacy.gh
    done = []
    try:
        for entry in data["changes"]:
            current, notes, _ = inspect(reader(), issues, state_reader)
            if notes or current != data["changes"][len(done):]:
                raise ValueError("Divergência ou conflito durante lote")
            writer("project", "item-edit", str(PROJECT), "--owner", OWNER,
                   "--url", entry["url"], "--field", entry["field"],
                   "--value", entry["value"])
            done.append(entry)
            current, notes, _ = inspect(reader(), issues, state_reader)
            if notes or current != data["changes"][len(done):]:
                raise ValueError("Pós-escrita inconsistente")
        return done
    except Exception as exc:
        raise RuntimeError(f"APLICAÇÃO PARCIAL POSSÍVEL ({len(done)} confirmadas); "
                           "não repetir sem auditoria. " + str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", help="IDs separados por vírgula, ex.: 18,19")
    parser.add_argument("--plan-file", type=Path, help="Salvar plano local, sem sobrescrever")
    parser.add_argument("--apply-plan", type=Path, help="Plano pinado para execução futura autorizada")
    parser.add_argument("--confirm", help="SHA256 exato do plano para executar")
    args = parser.parse_args(argv)
    try:
        if args.apply_plan:
            if args.issues or args.plan_file or not args.confirm:
                raise ValueError("--apply-plan exige apenas --confirm")
            data = json.loads(args.apply_plan.read_text(encoding="utf-8"))
            done = apply_plan(data, args.confirm)
            print(f"APLICADO E REVALIDADO: {len(done)} campos")
            return 0
        if args.confirm:
            raise ValueError("--confirm somente com --apply-plan")
        numbers = parse_numbers(args.issues) if args.issues else None
        payload = fetch_project()
        changes, notes, _ = inspect(payload, numbers)
        print("CHDevFlow KSYNC-03 | PRÉVIA, sem escrita remota")
        for note in notes:
            print("ATENÇÃO:", note)
        for c in changes:
            print(f"#{c['number']} | {c['field']}: (vazio) -> {c['value']}")
        print(f"Campos elegíveis: {len(changes)}; Issues: {len(set(x['number'] for x in changes))}")
        if args.plan_file:
            if numbers is None:
                raise ValueError("--plan-file exige --issues explícitas")
            plan = make_plan(payload, numbers)
            with args.plan_file.open("x", encoding="utf-8") as f:
                f.write(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
            print(f"Plano criado: {args.plan_file} | digest={plan['digest']}")
            print("Plano NÃO é autorização; aplicação depende de gate específico do PO.")
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print("BLOQUEADO:", legacy._safe_error(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
