#!/usr/bin/env python3
"""KSYNC-03: inspector e aplicador assistido do Project #2.

Sem escrita remota por padrão. Aplicação requer plano pinado, comparação
com estado LIVE, confirmação humana interativa e autorização externa do PO.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
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


def _stable_item(item):
    """Reconciliar apenas a grafia de Esteira/Etapa; preservar demais dados."""
    excluded = {"esteira", "etapa ch"}
    stable = {k: v for k, v in item.items()
              if not (isinstance(k, str) and k.casefold() in excluded)}
    stable["Esteira"] = legacy._field_value(item, "Esteira")
    stable["Etapa CH"] = legacy._field_value(item, "Etapa CH")
    return stable


def _selected_items(payload, issues):
    result = {}
    for item in payload["items"]:
        c = item.get("content")
        if (isinstance(c, dict) and c.get("type") == "Issue"
                and c.get("repository") == REPO and c.get("number") in issues):
            result[c["number"]] = item
    if set(result) != set(issues):
        raise ValueError("Issues do lote não encontradas")
    return result


def _verify_state(payload, issues, expected, remaining, state_reader):
    """Revalida o lote inteiro, inclusive campos já alterados e não editáveis."""
    changes, notes, _ = inspect(payload, issues, state_reader)
    if notes or changes != remaining:
        raise ValueError("Mudanças pendentes divergentes ou conflito no Project")
    observed = _selected_items(payload, issues)
    for number, item in observed.items():
        if _stable_item(item) != expected[number]:
            raise ValueError(f"#{number}: snapshot divergiu durante lote")
    return observed


def apply_plan(data, confirm, *, reader=fetch_project, state_reader=None,
               writer=None, prompt=input, interactive=None, audit=None):
    """Gate manual; a autorização do PO é evento externo, nunca inferido."""
    issues = validate_plan(data)
    if confirm != data["digest"]:
        raise ValueError("Digest não confirmado")
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        raise ValueError("Aplicação requer terminal interativo; sem cron/CI")

    audit = audit or (lambda _record: None)
    try:
        audit({"event": "PREFLIGHT", "digest": data["digest"], "issues": issues})
        # Nenhuma escrita no Project antes de confirmar toda a versão do plano.
        baseline = reader()
        if make_plan(baseline, issues, state_reader) != data:
            raise ValueError("Estado remoto mudou: regenere o plano; nada aplicado")
        expected = {n: _stable_item(item) for n, item in
                    _selected_items(baseline, issues).items()}
        phrase = "APROVO KSYNC-03 " + data["digest"][:12]
        if prompt(f"Digite exatamente '{phrase}' após autorização externa do PO: ") != phrase:
            raise ValueError("Confirmação humana ausente")
    except Exception as exc:
        try:
            audit({"event": "BLOCKED_PREWRITE", "reason_type": type(exc).__name__})
        except Exception:
            pass
        raise

    state_reader = state_reader or legacy.issue_state
    writer = writer or legacy.gh
    done = []
    uncertain = None
    try:
        audit({"event": "START", "digest": data["digest"], "issues": issues,
               "requested_changes": len(data["changes"])})
        for entry in data["changes"]:
            remaining = data["changes"][len(done):]
            current = _verify_state(reader(), issues, expected, remaining, state_reader)
            n, field = entry["number"], entry["field"]
            before = legacy._field_value(current[n], field)
            if before is not None:
                raise ValueError(f"#{n}: campo {field} não está vazio")
            audit({"event": "ATTEMPT", "number": n, "field": field,
                   "before": before, "expected": entry["value"]})
            # Após ATTEMPT a escrita pode ter acontecido mesmo se a rede falhar.
            uncertain = entry
            writer("project", "item-edit", str(PROJECT), "--owner", OWNER,
                   "--url", entry["url"], "--field", field,
                   "--value", entry["value"])
            expected[n][field] = entry["value"]
            # Confere o valor EXATO gravado e todos os campos do lote.
            observed = _verify_state(reader(), issues, expected,
                                     data["changes"][len(done) + 1:], state_reader)
            after = legacy._field_value(observed[n], field)
            if after != entry["value"]:
                raise ValueError(f"#{n}: valor efetivo diferente do solicitado")
            audit({"event": "VERIFIED", "number": n, "field": field,
                   "before": before, "after": after,
                   "snapshot_sha256": digest(_stable_item(observed[n]))})
            done.append(entry)
            uncertain = None
        audit({"event": "COMPLETE", "confirmed": len(done)})
        return done
    except Exception as exc:
        record = {"event": "ABORT", "confirmed": len(done),
                  "uncertain": None if uncertain is None else
                  {"number": uncertain["number"], "field": uncertain["field"]},
                  "reason_type": type(exc).__name__}
        try:
            audit(record)
        except Exception:
            pass  # Falha no log também interrompe; preservar erro original.
        detail = (f"; resultado INDETERMINADO em #{uncertain['number']} "
                  f"{uncertain['field']}" if uncertain else "")
        raise RuntimeError(f"APLICAÇÃO PARCIAL POSSÍVEL ({len(done)} confirmadas){detail}; "
                           "não repetir sem auditoria. " + str(exc)) from exc


def _audit_writer(handle):
    def append(record):
        event = {"protocol": "RUC/1.0", "mission": "KSYNC-03/#19",
                 "timestamp_utc": datetime.now(timezone.utc).isoformat(), **record}
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return append


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues", help="IDs separados por vírgula, ex.: 18,19")
    parser.add_argument("--plan-file", type=Path, help="Salvar plano local, sem sobrescrever")
    parser.add_argument("--apply-plan", type=Path, help="Plano pinado para execução futura autorizada")
    parser.add_argument("--confirm", help="SHA256 exato do plano para executar")
    parser.add_argument("--audit-file", type=Path, help="JSONL de auditoria, criação exclusiva")
    args = parser.parse_args(argv)
    try:
        if args.apply_plan:
            if args.issues or args.plan_file or not args.confirm or not args.audit_file:
                raise ValueError("--apply-plan exige --confirm e --audit-file; sem outros modos")
            data = json.loads(args.apply_plan.read_text(encoding="utf-8"))
            # Criar registro exclusivo com 0600 antes de qualquer tentativa.
            fd = os.open(args.audit_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                done = apply_plan(data, args.confirm, audit=_audit_writer(handle))
            print(f"APLICADO E REVALIDADO: {len(done)} campos")
            return 0
        if args.confirm or args.audit_file:
            raise ValueError("--confirm/--audit-file somente com --apply-plan")
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
