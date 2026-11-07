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
import subprocess
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


def inspect(payload, selected=None, state_reader=None, activity_reader=None):
    """Inspeção pura exceto leitura de estados via callback; ignora CLOSED."""
    state_reader = state_reader or legacy.issue_state
    activity_reader = activity_reader or (
        lambda repo, num: legacy.ch_stage_evidence.probe(repo, num, legacy.gh)
    )
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
            # A coluna Todo não é uma evidência de ausência de trabalho.
            try:
                evidence = activity_reader(REPO, n)
                if evidence.get("status") == "CLEAR":
                    changes.append({"number": n, "field": "Etapa CH", "value": "BACKLOG",
                                    "url": c["url"]})
                elif evidence.get("status") == "WORK_FOUND":
                    notes.append(f"ETAPA_PENDENTE_PO: #{n}: atividade vinculada: "
                                 + legacy.ch_stage_evidence.format_refs(evidence)
                                 + "; BACKLOG não sugerido")
                else:
                    notes.append(f"ETAPA_PENDENTE_PO: #{n}: histórico inconclusivo; preservar etapa")
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
                notes.append(f"ETAPA_PENDENTE_PO: #{n}: consulta de histórico falhou; preservar etapa")
    if chosen is not None and not chosen.issubset(found):
        raise ValueError("Uma ou mais Issues não estão neste Project/repositório")
    return sorted(changes, key=lambda x: (x["number"], x["field"])), notes, snapshots


def make_plan(payload, numbers, state_reader=None):
    changes, notes, snapshots = inspect(payload, numbers, state_reader)
    blockers = [note for note in notes if not note.startswith("ETAPA_PENDENTE_PO:")]
    if blockers:
        raise ValueError("Lote inseguro: " + "; ".join(blockers))
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
    blockers = [note for note in notes if not note.startswith("ETAPA_PENDENTE_PO:")]
    if blockers or changes != remaining:
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



# CH-GOV-01 / F2.2: admissao fisica independente do KSYNC-03 legado.
# As funcoes existentes de inspecao e apply_plan NAO sao modificadas.
ADMIT_SCHEMA = "CHDEVFLOW-ADMIT/1"
ADMIT_FIELDS = ("Esteira", "Etapa CH", "Autonomia CH")
ADMIT_AUTONOMY = ("CH-0", "CH-1", "CH-2", "CH-3")
ADMIT_APPROVAL_ISSUE = 63


def _admit_context_reader(number):
    """Le apenas Issue, Project, esquema e historico; nenhuma mutation."""
    issue = legacy.gh_json(
        "issue", "view", str(number), "-R", REPO,
        "--json", "id,number,title,body,labels,state,url"
    )
    project = legacy.gh_json(
        "project", "view", str(PROJECT), "--owner", OWNER, "--format", "json"
    )
    fields = legacy.gh_json(
        "project", "field-list", str(PROJECT), "--owner", OWNER,
        "--format", "json", "-L", "100"
    )
    items = fetch_project()
    activity = legacy.ch_stage_evidence.probe(REPO, number, legacy.gh)
    return {"issue": issue, "project": project, "fields": fields,
            "items": items, "activity": activity}


def _admit_approval_reader(comment_id):
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("Autorizacao externa do PO: ID de comentario invalido")
    return legacy.gh_json(
        "api", f"repos/{REPO}/issues/comments/{comment_id}"
    )


def _admit_issue_fingerprint(issue):
    labels = issue.get("labels", [])
    if not isinstance(labels, list):
        raise ValueError("Labels da Issue invalidas")
    names = [entry.get("name") if isinstance(entry, dict) else entry
             for entry in labels]
    if any(not isinstance(name, str) for name in names):
        raise ValueError("Labels da Issue invalidas")
    return digest({"id": issue.get("id"), "number": issue.get("number"),
                   "title": issue.get("title"), "body": issue.get("body"),
                   "state": issue.get("state"), "url": issue.get("url"),
                   "labels": sorted(names)})


def _admit_approval_fingerprint(proof, number, lane, autonomy):
    """Uma etiqueta ou confirmacao local jamais substitui comentario real do PO."""
    if not isinstance(proof, dict) or proof.get("user", {}).get("login") != OWNER:
        raise ValueError("Comentario de autorizacao nao pertence ao PO")
    issue_url = proof.get("issue_url")
    if issue_url not in (
        f"https://api.github.com/repos/{REPO}/issues/{number}",
        f"https://api.github.com/repos/{REPO}/issues/{ADMIT_APPROVAL_ISSUE}",
    ):
        raise ValueError("Autorizacao vinculada a Issue incorreta")
    statement = (f"CH-GOV-01 ADMIT PROJECT#{PROJECT} ISSUE#{number} "
                 f"ESTEIRA={lane} ETAPA=BACKLOG AUTONOMIA={autonomy}")
    body = proof.get("body")
    if not isinstance(body, str) or statement not in body.splitlines():
        raise ValueError("PO nao aprovou exatamente a Issue e os tres campos")
    if type(proof.get("id")) is not int or proof["id"] <= 0:
        raise ValueError("ID da autorizacao invalido")
    return digest({"id": proof["id"], "body": body, "author": OWNER,
                   "issue_url": issue_url, "updated_at": proof.get("updated_at")})


def _admit_project_item(items, number):
    """Verifica totalidade e identifica zero ou um item da Issue."""
    if (not isinstance(items, dict) or not isinstance(items.get("items"), list)
            or type(items.get("totalCount")) is not int
            or len(items["items"]) != items["totalCount"]
            or items["totalCount"] > legacy.MAX_ITEMS):
        raise ValueError("Snapshot Project incompleto ou invalido")
    matches = []
    for item in items["items"]:
        if not isinstance(item, dict):
            raise ValueError("Cartao Project invalido")
        content = item.get("content")
        if (isinstance(content, dict) and content.get("type") == "Issue"
                and content.get("repository") == REPO
                and content.get("number") == number):
            if content.get("url") != f"https://github.com/{REPO}/issues/{number}":
                raise ValueError("URL da Issue diverge do Project")
            if not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("ID do cartao ausente")
            matches.append(item)
    if len(matches) > 1:
        raise ValueError("Issue duplicada no Project")
    return matches[0] if matches else None


def _admit_field_options(fields, values):
    if not isinstance(fields, dict) or not isinstance(fields.get("fields"), list):
        raise ValueError("Esquema de campos nao verificavel")
    selected = []
    for name in ADMIT_FIELDS:
        matches = [field for field in fields["fields"]
                   if isinstance(field, dict) and field.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"Campo {name} ausente ou duplicado")
        field = matches[0]
        if field.get("type") not in ("ProjectV2SingleSelectField", "SingleSelect"):
            raise ValueError(f"Campo {name} nao e SingleSelect")
        if not isinstance(field.get("id"), str) or not field["id"]:
            raise ValueError(f"Field ID de {name} ausente")
        choices = [opt for opt in field.get("options", [])
                   if isinstance(opt, dict) and opt.get("name") == values[name]]
        if len(choices) != 1 or not isinstance(choices[0].get("id"), str) or not choices[0]["id"]:
            raise ValueError(f"Option ID de {name} invalido")
        selected.append({"name": name, "field_id": field["id"],
                         "option_id": choices[0]["id"], "value": values[name]})
    return selected


def make_admit_plan(number, context, *, autonomy="CH-0", approval=None):
    """Plano pinado; sem chamada de escrita. CH-0 nunca deriva do corpo."""
    if type(number) is not int or number <= 0:
        raise ValueError("Issue precisa ser inteiro positivo")
    if autonomy not in ADMIT_AUTONOMY:
        raise ValueError("Autonomia CH fora do contrato")
    if not isinstance(context, dict):
        raise ValueError("Contexto LIVE invalido")
    issue = context.get("issue")
    project = context.get("project")
    if not isinstance(issue, dict) or not isinstance(project, dict):
        raise ValueError("Issue/Project LIVE indisponiveis")
    if (issue.get("number") != number or issue.get("state") != "OPEN"
            or issue.get("url") != f"https://github.com/{REPO}/issues/{number}"
            or not isinstance(issue.get("id"), str) or not issue["id"]):
        raise ValueError("Issue inexistente, fechada ou identidade divergente")
    if not isinstance(project.get("id"), str) or not project["id"]:
        raise ValueError("Project ID nao verificavel")
    from chdevflow.core.intake import validate_issue
    diagnosis = validate_issue(issue)
    if diagnosis["content_status"] != "CONTENT_VALID":
        raise ValueError("Intake F1 bloqueou admissao: "
                         + diagnosis["content_status"] + " "
                         + ", ".join(diagnosis["reasons"]))
    names = [x.get("name") if isinstance(x, dict) else x
             for x in issue["labels"]]
    lanes = {legacy.LANES[x] for x in names if x in legacy.LANES}
    if len(lanes) != 1:
        raise ValueError("Executor nao exclusivo")
    lane = next(iter(lanes))
    activity = context.get("activity")
    if not isinstance(activity, dict) or activity.get("status") != "CLEAR":
        raise ValueError("Etapa BACKLOG nao pode ser inferida: historico nao esta CLEAR")
    expected = {"Esteira": lane, "Etapa CH": "BACKLOG",
                "Autonomia CH": autonomy}
    selections = _admit_field_options(context.get("fields"), expected)
    item = _admit_project_item(context.get("items"), number)
    action = "ADD"
    if item is not None:
        actual = {name: legacy._field_value(item, name) for name in ADMIT_FIELDS}
        if actual != expected:
            raise ValueError("Cartao preexistente parcial/conflitante: reconciliacao PO")
        action = "ALREADY_REGISTERED"
    proof_id = None
    proof_digest = None
    if approval is not None:
        proof_digest = _admit_approval_fingerprint(approval, number, lane, autonomy)
        proof_id = approval["id"]
    data = {
        "schema": ADMIT_SCHEMA, "owner": OWNER, "repo": REPO, "project": PROJECT,
        "issue": number, "issue_id": issue["id"], "issue_url": issue["url"],
        "issue_fingerprint": _admit_issue_fingerprint(issue),
        "project_id": project["id"],
        "snapshot_digest": digest(context["items"]),
        "action": action, "item_id": item["id"] if item else None,
        "fields": selections, "autonomy": autonomy,
        "approval_id": proof_id, "approval_digest": proof_digest,
    }
    return {**data, "digest": digest(data)}


def _admit_validate_plan(plan):
    keys = {"schema", "owner", "repo", "project", "issue", "issue_id",
            "issue_url", "issue_fingerprint", "project_id", "snapshot_digest",
            "action", "item_id", "fields", "autonomy", "approval_id",
            "approval_digest", "digest"}
    if not isinstance(plan, dict) or set(plan) != keys:
        raise ValueError("Plano ADMIT invalido")
    if (plan["schema"], plan["owner"], plan["repo"], plan["project"]) != (
            ADMIT_SCHEMA, OWNER, REPO, PROJECT):
        raise ValueError("Destino do plano diverge")
    if (type(plan["issue"]) is not int or plan["issue"] <= 0
            or plan["autonomy"] not in ADMIT_AUTONOMY
            or plan["action"] not in ("ADD", "ALREADY_REGISTERED")):
        raise ValueError("Escopo do plano nao permitido")
    if (plan["approval_id"] is None or type(plan["approval_id"]) is not int
            or plan["approval_id"] <= 0
            or not isinstance(plan["approval_digest"], str)):
        raise ValueError("Plano sem autorizacao especifica do PO")
    if (not isinstance(plan["fields"], list) or
            [f.get("name") for f in plan["fields"] if isinstance(f, dict)] !=
            list(ADMIT_FIELDS)):
        raise ValueError("Tres campos obrigatorios invalidos")
    if not isinstance(plan["digest"], str) or digest(
            {k: v for k, v in plan.items() if k != "digest"}) != plan["digest"]:
        raise ValueError("Digest alterado")
    return plan


_ADMIT_ADD = ("mutation($projectId:ID!,$contentId:ID!){"
              "addProjectV2ItemById(input:{projectId:$projectId,"
              "contentId:$contentId}){item{id}}}")
_ADMIT_UPDATE = ("mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,"
                 "$optionId:String!){updateProjectV2ItemFieldValue("
                 "input:{projectId:$projectId,itemId:$itemId,"
                 "fieldId:$fieldId,value:{singleSelectOptionId:$optionId}})"
                 "{projectV2Item{id}}}")


def _admit_graphql(operation, params):
    """Unico adaptador de mutacao; nunca chamado no modo dry-run."""
    if operation not in ("add", "set"):
        raise ValueError("Operacao GraphQL proibida")
    query = _ADMIT_ADD if operation == "add" else _ADMIT_UPDATE
    result = legacy.gh_json("api", "graphql", "-f", "query=" + query,
                            *(arg for key, value in params.items()
                              for arg in ("-f", key + "=" + value)))
    if result.get("errors"):
        raise RuntimeError("GraphQL retornou erro")
    data = result.get("data")
    payload = (data.get("addProjectV2ItemById") if operation == "add"
               else data.get("updateProjectV2ItemFieldValue")) if isinstance(data, dict) else None
    node = payload.get("item" if operation == "add" else "projectV2Item") if isinstance(payload, dict) else None
    if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
        raise RuntimeError("Resposta GraphQL sem item ID verificavel")
    return node["id"]


def _admit_validate_observed(context, plan, item_id, completed):
    """Read-back LIVE depois da inclusao e de cada atualizacao."""
    if (context.get("project", {}).get("id") != plan["project_id"]
            or _admit_issue_fingerprint(context["issue"]) != plan["issue_fingerprint"]):
        raise ValueError("Issue ou Project alterados durante admissao")
    item = _admit_project_item(context.get("items"), plan["issue"])
    if item is None or item["id"] != item_id:
        raise ValueError("Read-back nao encontrou o cartao esperado")
    expected = {x["name"]: x["value"] if x["name"] in completed else None
                for x in plan["fields"]}
    current = {name: legacy._field_value(item, name) for name in ADMIT_FIELDS}
    if current != expected:
        raise ValueError("Read-back divergiu: campos incompletos ou conflitantes")
    return item


def apply_admit_plan(plan, confirm, *, reader=_admit_context_reader,
                     approval_reader=_admit_approval_reader,
                     graphql=_admit_graphql, interactive=None,
                     prompt=input, audit=None):
    """Gate humano, plano pinado, mutacoes sequenciais, sem retry automatico."""
    _admit_validate_plan(plan)
    if confirm != plan["digest"]:
        raise ValueError("Digest do plano nao confirmado")
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        raise ValueError("Admissao exige terminal humano interativo")
    if audit is None:
        raise ValueError("Auditoria persistente obrigatoria")
    # Reconsulta API e PO antes de qualquer escrita.
    fresh = reader(plan["issue"])
    proof = approval_reader(plan["approval_id"])
    rebuilt = make_admit_plan(plan["issue"], fresh,
                              autonomy=plan["autonomy"], approval=proof)
    if rebuilt != plan:
        raise ValueError("Plano obsoleto ou autorizacao alterada; nenhuma escrita")
    phrase = "APROVO ADMISSAO " + plan["digest"][:12]
    if prompt(f"Digite exatamente '{phrase}' apos decisao do PO: ") != phrase:
        raise ValueError("Confirmacao humana ausente")
    audit({"event": "PREFLIGHT", "digest": plan["digest"],
           "issue": plan["issue"], "approval_id": plan["approval_id"]})
    if plan["action"] == "ALREADY_REGISTERED":
        audit({"event": "ALREADY_REGISTERED", "item_id": plan["item_id"]})
        return plan["item_id"]

    uncertain = None
    completed = []
    item_id = None
    try:
        audit({"event": "ATTEMPT_ADD", "issue": plan["issue"]})
        uncertain = "addProjectV2ItemById"
        item_id = graphql("add", {"projectId": plan["project_id"],
                                  "contentId": plan["issue_id"]})
        _admit_validate_observed(reader(plan["issue"]), plan, item_id, completed)
        uncertain = None
        audit({"event": "VERIFIED_ADD", "item_id": item_id})
        for field in plan["fields"]:
            name = field["name"]
            # Verificacao LIVE imediatamente antes de cada mutacao.
            _admit_validate_observed(reader(plan["issue"]), plan, item_id, completed)
            audit({"event": "ATTEMPT_FIELD", "field": name,
                   "expected": field["value"]})
            uncertain = name
            returned_id = graphql("set", {
                "projectId": plan["project_id"], "itemId": item_id,
                "fieldId": field["field_id"], "optionId": field["option_id"],
            })
            if returned_id != item_id:
                raise ValueError("GraphQL alterou item incorreto")
            completed.append(name)
            _admit_validate_observed(reader(plan["issue"]), plan, item_id, completed)
            uncertain = None
            audit({"event": "VERIFIED_FIELD", "field": name,
                   "value": field["value"]})
        # Confirmacao global final; somente depois declarar cadastro verificado.
        _admit_validate_observed(reader(plan["issue"]), plan, item_id, completed)
        audit({"event": "COMPLETE", "item_id": item_id,
               "fields_verified": list(completed),
               "execution_authorized": False})
        return item_id
    except Exception as exc:
        audit({"event": "ABORT", "verified_fields": list(completed),
               "uncertain": uncertain, "reason_type": type(exc).__name__})
        raise RuntimeError("Admissao parcial ou indeterminada; "
                           "nao repetir sem reconciliacao e gate do PO") from exc


def admit_main(argv=None, *, reader=_admit_context_reader,
               approval_reader=_admit_approval_reader,
               graphql=_admit_graphql):
    parser = argparse.ArgumentParser(prog="ch project admit",
                                     description="Admissao assistida — dry-run por padrao")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--autonomy", choices=ADMIT_AUTONOMY, default="CH-0")
    parser.add_argument("--approval-comment", type=int)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--confirm")
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.issue <= 0:
            raise ValueError("Numero da Issue invalido")
        if args.apply_plan:
            if (args.dry_run or args.plan_file or args.approval_comment
                    or not args.confirm or not args.audit_file):
                raise ValueError("Aplicacao exige --apply-plan, --confirm e --audit-file")
            plan = json.loads(args.apply_plan.read_text(encoding="utf-8"))
            if plan.get("issue") != args.issue:
                raise ValueError("Issue nao corresponde ao plano")
            fd = os.open(args.audit_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                def audit(event):
                    f.write(json.dumps({"protocol": "RUC/1.0",
                                        "mission": "CH-GOV-01/F2.2",
                                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                                        **event}, ensure_ascii=False, sort_keys=True) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                item_id = apply_admit_plan(plan, args.confirm, reader=reader,
                                          approval_reader=approval_reader,
                                          graphql=graphql, audit=audit)
            print(f"CADASTRO VERIFICADO: Issue #{args.issue} / item {item_id}")
            return 0
        if args.confirm or args.audit_file:
            raise ValueError("Confirmacao/auditoria apenas em --apply-plan")
        if args.plan_file and not args.approval_comment:
            raise ValueError("--plan-file exige --approval-comment do PO")
        context = reader(args.issue)
        proof = approval_reader(args.approval_comment) if args.approval_comment else None
        plan = make_admit_plan(args.issue, context,
                               autonomy=args.autonomy, approval=proof)
        print(f"ADMIT PREVIEW (SEM ESCRITA) Issue #{args.issue}: {plan['action']}")
        for f in plan["fields"]:
            print(f"  {f['name']}: {f['value']} (field={f['field_id']}, option={f['option_id']})")
        print("Digest:", plan["digest"])
        print("Project nao alterado; planos nao autorizam execucao.")
        if args.plan_file:
            fd = os.open(args.plan_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print("Plano criado:", args.plan_file)
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired,
            json.JSONDecodeError, KeyError, TypeError) as exc:
        print("ADMIT BLOQUEADO:", legacy._safe_error(str(exc)), file=sys.stderr)
        return 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "admit":
        return admit_main(argv[1:])
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
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print("BLOQUEADO:", legacy._safe_error(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
