#!/usr/bin/env python3
"""W-DATA-01-A: reconciliador assistido de Autonomia CH.

DRY-RUN por padrão. Não importa a CLI principal e não estende a allowlist KSYNC-03.
A execução remota NÃO é autorizada por este código: requer gate futuro, nominal,
autenticado por comentário do PO, plano EXECUTÁVEL pinado e TTY.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

OWNER = "hallanbrito"
REPO = "hallanbrito/CHDevFlow"
PROJECT = 2
ISSUES = (8, 10, 12, 13, 24)
TARGETS = {8: "CH-1", 10: "CH-1", 12: "CH-0", 13: "CH-0", 24: "CH-1"}
FIELD = "Autonomia CH"
CH1_SCHEMA = "CHDEVFLOW-CHDATA01-CH1-PLAN/1"
APPLY_SCHEMA = "CHDEVFLOW-CHDATA01-AUTONOMY-APPLY/1"
CH1_DIGEST = "68bcb20520d315853acd8073a548f2ec3dcabf02b3e766c3992a1197b4a2f88f"
SNAPSHOT_DIGEST = "7460350916057bd5f14bf0934560fff247f548d03dc0e531e5e6ebbb486f41c6"
PRESERVE = ("Etapa CH", "Esteira", "Status", "Prioridade CH", "Risco CH", "Decisao PO")
MAX_PLAN_AGE = timedelta(hours=24)
# W-DATA-01-B: R2 com contrato separado; o fluxo R1 permanece intacto.
RESUME_SCHEMA = "CHDEVFLOW-CHDATA01-AUTONOMY-RESUME/1"
RESUME_ISSUES = (10, 12, 13, 24)
R1_APPLY_DIGEST = "3393caca4c2b328644dbc10580eae1cabc798e80573a1196db3dbb90973bc26d"


def digest(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def unsigned(data: dict) -> dict:
    return {k: v for k, v in data.items() if k != "digest_sha256"}


def assert_digest(data: dict, expected: str | None = None) -> None:
    observed = data.get("digest_sha256")
    if not isinstance(observed, str) or len(observed) != 64 or digest(unsigned(data)) != observed:
        raise ValueError("Digest SHA-256 do plano adulterado/inválido")
    if expected is not None and observed != expected:
        raise ValueError("Digest do plano não coincide com o homologado")


def validate_ch1(plan: dict) -> dict[int, dict]:
    """Verifica o ARTEFATO consultivo, jamais o aceita como plano de mutation."""
    if not isinstance(plan, dict):
        raise ValueError("Plano CH-1 inválido")
    assert_digest(plan, CH1_DIGEST)
    if (plan.get("schema") != CH1_SCHEMA or plan.get("read_only") is not True
            or plan.get("not_an_apply_plan") is not True
            or plan.get("authorized_phase") != "CH-1"
            or plan.get("repo") != REPO or plan.get("project") != PROJECT
            or plan.get("source") != "LIVE_GITHUB"
            or plan.get("source_snapshot_sha256") != SNAPSHOT_DIGEST
            or plan.get("issues") != list(ISSUES)):
        raise ValueError("Escopo CH-1 divergente do homologado")
    changes = plan.get("changes")
    if not isinstance(changes, list) or len(changes) != len(ISSUES):
        raise ValueError("Quantidade de mudanças CH-1 incorreta")
    result = {}
    for change, number in zip(changes, ISSUES):
        if (not isinstance(change, dict) or change.get("issue") != number
                or change.get("field") != FIELD
                or change.get("proposed_after") != TARGETS[number]
                or change.get("before") != "NÃO_OBSERVADO"
                or change.get("issue_url") != f"https://github.com/{REPO}/issues/{number}"
                or not isinstance(change.get("card_id"), str)
                or not change["card_id"].startswith("PVTI_")
                or not isinstance(change.get("field_id"), str)
                or not isinstance(change.get("option_id"), str)
                or not isinstance(change.get("preserve"), dict)
                or set(change["preserve"]) != {"Etapa CH", "Esteira"}):
            raise ValueError(f"Issue #{number}: contrato CH-1 inválido")
        result[number] = change
    ratification = plan.get("po_ratification")
    if (not isinstance(ratification, dict) or ratification.get("issue") != 10
            or ratification.get("to_proposal") != "CH-1"
            or ratification.get("write_authorized") is not False):
        raise ValueError("Ratificação #10 ausente ou alterada")
    return result


def _module():
    """Somente sob adaptador LIVE explícito; evita rede em import/testes offline."""
    import ch_project_assist
    return ch_project_assist


def live_reader() -> dict:
    """Consultas READ-ONLY pelo contrato legado; nenhuma mutation."""
    app = _module()
    return {
        "project": app.legacy.gh_json("project", "view", "2", "--owner", OWNER, "--format", "json"),
        "fields": app.legacy.gh_json("project", "field-list", "2", "--owner", OWNER,
                                      "--format", "json", "-L", "100"),
        "items": app.fetch_project(),
    }


def approval_reader(comment_id: int) -> dict:
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("ID de comentário inválido")
    return _module().legacy.gh_json("api", f"repos/{REPO}/issues/comments/{comment_id}")


def set_only(params: dict[str, str]) -> str:
    """Reutiliza o adaptador GraphQL 'set' W-F2.2, sem caminho 'add'."""
    if set(params) != {"projectId", "itemId", "fieldId", "optionId"}:
        raise ValueError("Parâmetros de mutation proibidos")
    return _module()._admit_graphql("set", params)


def _value(item: dict, field: str) -> str | None:
    """Mesmo parser usado no fluxo KSYNC/W-F2.2, importado só quando necessário.

    Uma implementação pura equivalente permite testes offline sem acoplar ao gh.
    """
    for key, val in item.items():
        if isinstance(key, str) and key.casefold() == field.casefold():
            if val is None or val == "":
                return None
            if isinstance(val, dict) and isinstance(val.get("name"), str):
                return val["name"] or None
            if isinstance(val, str):
                return val
            raise ValueError(f"{field}: formato de campo inesperado")
    return None


def _project_schema(context: dict) -> tuple[str, str, dict[str, str]]:
    if not isinstance(context, dict):
        raise ValueError("Contexto LIVE inválido")
    project = context.get("project")
    fields = context.get("fields")
    raw = context.get("items")
    if (not isinstance(project, dict) or not isinstance(project.get("id"), str)
            or not project["id"] or not isinstance(fields, dict)
            or not isinstance(fields.get("fields"), list)
            or not isinstance(raw, dict) or not isinstance(raw.get("items"), list)
            or type(raw.get("totalCount")) is not int
            or len(raw["items"]) != raw["totalCount"] or raw["totalCount"] > 100):
        raise ValueError("LIVE Project/fields/items incompleto")
    choices = [f for f in fields["fields"] if isinstance(f, dict) and f.get("name") == FIELD]
    if len(choices) != 1 or choices[0].get("type") not in ("ProjectV2SingleSelectField", "SingleSelect"):
        raise ValueError("Autonomia CH ausente/duplicada ou não SingleSelect")
    f = choices[0]
    if not isinstance(f.get("id"), str) or not f["id"]:
        raise ValueError("Field ID inválido")
    options: dict[str, str] = {}
    for op in f.get("options", []):
        if isinstance(op, dict) and op.get("name") in {"CH-0", "CH-1"}:
            if op["name"] in options or not isinstance(op.get("id"), str) or not op["id"]:
                raise ValueError("Option ID duplicado/inválido")
            options[op["name"]] = op["id"]
    if set(options) != {"CH-0", "CH-1"}:
        raise ValueError("Opções CH-0/CH-1 indisponíveis")
    return project["id"], f["id"], options


def _items(context: dict) -> dict[int, dict]:
    all_items = context["items"]["items"]
    result: dict[int, dict] = {}
    for item in all_items:
        if not isinstance(item, dict):
            raise ValueError("Project contém item inválido")
        content = item.get("content")
        if (isinstance(content, dict) and content.get("repository") == REPO
                and content.get("type") == "Issue" and content.get("number") in ISSUES):
            number = content["number"]
            if number in result:
                raise ValueError(f"Issue #{number} duplicada")
            if (content.get("url") != f"https://github.com/{REPO}/issues/{number}"
                    or not isinstance(item.get("id"), str) or not item["id"]):
                raise ValueError(f"Issue #{number} com identidade inválida")
            result[number] = item
    if set(result) != set(ISSUES):
        raise ValueError("Lote incompleto no Project LIVE")
    if len({i["id"] for i in result.values()}) != len(ISSUES):
        raise ValueError("Card IDs duplicados")
    return result


def _preserved(item: dict) -> dict:
    # Esses campos não podem ser alterados pelo reconciliador.
    return {name: _value(item, name) for name in PRESERVE}


def make_apply_plan(ch1: dict, context: dict, *, captured_at: str | None = None) -> dict:
    reference = validate_ch1(ch1)
    project_id, field_id, options = _project_schema(context)
    found = _items(context)
    changes = []
    for number in ISSUES:
        item, old = found[number], reference[number]
        if (item["id"] != old["card_id"] or field_id != old["field_id"]
                or options[TARGETS[number]] != old["option_id"]):
            raise ValueError(f"#{number}: IDs LIVE divergentes da prova CH-1")
        if _value(item, FIELD) is not None:
            raise ValueError(f"#{number}: Autonomia CH já preenchida")
        preserve = _preserved(item)
        if (preserve["Etapa CH"] != (None if old["preserve"]["Etapa CH"] == "NÃO_OBSERVADO" else old["preserve"]["Etapa CH"])
                or preserve["Esteira"] != (None if old["preserve"]["Esteira"] == "NÃO_OBSERVADO" else old["preserve"]["Esteira"])):
            raise ValueError(f"#{number}: etapa/esteira alteradas desde CH-1; revisar")
        changes.append({
            "issue": number, "card_id": item["id"],
            "issue_url": f"https://github.com/{REPO}/issues/{number}",
            "field": FIELD, "field_id": field_id, "option_id": options[TARGETS[number]],
            "before": None, "after": TARGETS[number], "preserve_before": preserve,
        })
    stamp = captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "schema": APPLY_SCHEMA, "repo": REPO, "owner": OWNER, "project": PROJECT,
        "project_id": project_id, "field": FIELD, "field_id": field_id,
        "source_ch1_digest_sha256": CH1_DIGEST,
        "source_snapshot_digest_sha256": SNAPSHOT_DIGEST,
        "prepared_at_utc": stamp, "issues": list(ISSUES), "changes": changes,
        "mutations_authorized": False,
    }
    return {**payload, "digest_sha256": digest(payload)}


def validate_apply_plan(plan: dict) -> list[dict]:
    if not isinstance(plan, dict):
        raise ValueError("Plano não é um objeto")
    if set(plan) != {
        "schema", "repo", "owner", "project", "project_id", "field", "field_id",
        "source_ch1_digest_sha256", "source_snapshot_digest_sha256", "prepared_at_utc",
        "issues", "changes", "mutations_authorized", "digest_sha256",
    }:
        raise ValueError("Schema do plano executável inválido (CH-1 não é aplicável)")
    assert_digest(plan)
    if (plan["schema"] != APPLY_SCHEMA or plan["repo"] != REPO
            or plan["owner"] != OWNER or plan["project"] != PROJECT
            or plan["field"] != FIELD or plan["source_ch1_digest_sha256"] != CH1_DIGEST
            or plan["source_snapshot_digest_sha256"] != SNAPSHOT_DIGEST
            or plan["mutations_authorized"] is not False
            or plan["issues"] != list(ISSUES)
            or not isinstance(plan["project_id"], str) or not plan["project_id"]
            or not isinstance(plan["field_id"], str) or not plan["field_id"]):
        raise ValueError("Contrato/allowlist do plano inválido")
    if not isinstance(plan["changes"], list) or len(plan["changes"]) != 5:
        raise ValueError("Plano deve conter cinco mudanças")
    for n, change in zip(ISSUES, plan["changes"]):
        if (not isinstance(change, dict) or set(change) != {
            "issue", "card_id", "issue_url", "field", "field_id", "option_id",
            "before", "after", "preserve_before",
        } or change["issue"] != n or change["field"] != FIELD
                or change["field_id"] != plan["field_id"] or change["after"] != TARGETS[n]
                or change["before"] is not None
                or not isinstance(change["card_id"], str) or not change["card_id"].startswith("PVTI_")
                or not isinstance(change["option_id"], str) or not change["option_id"]
                or change["issue_url"] != f"https://github.com/{REPO}/issues/{n}"
                or not isinstance(change["preserve_before"], dict)
                or set(change["preserve_before"]) != set(PRESERVE)
                or any(v is not None and not isinstance(v, str)
                       for v in change["preserve_before"].values())):
            raise ValueError(f"#{n}: mudança fora da allowlist do lote")
    stamp = datetime.fromisoformat(plan["prepared_at_utc"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Timestamp sem UTC")
    age = datetime.now(timezone.utc) - stamp
    if age < -timedelta(minutes=2) or age > MAX_PLAN_AGE:
        raise ValueError("Plano expirou ou horário inválido; refazer e obter novo gate")
    return plan["changes"]


def check_live(plan: dict, context: dict, verified: set[int]) -> None:
    project_id, field_id, options = _project_schema(context)
    if project_id != plan["project_id"] or field_id != plan["field_id"]:
        raise ValueError("Project/Field ID alterados")
    found = _items(context)
    for change in plan["changes"]:
        n = change["issue"]
        current = found[n]
        expected = change["after"] if n in verified else None
        if (current["id"] != change["card_id"]
                or options[change["after"]] != change["option_id"]
                or _value(current, FIELD) != expected
                or _preserved(current) != change["preserve_before"]):
            raise ValueError(f"#{n}: divergência LIVE no lote; abortar sem retry")



def read_r1_audit(path: Path) -> tuple[list[dict], str]:
    """Aceita exclusivamente o log R1 com #8 verificada e sem outras tentativas."""
    raw = path.read_bytes()
    if not raw or len(raw) > 1000000 or not raw.endswith(b"\n"):
        raise ValueError("RUC R1 inválida ou truncada")
    events = [json.loads(line) for line in raw.splitlines()]
    if (len(events) != 6 or any(not isinstance(e, dict) or
            e.get("protocol") != "RUC/1.0" or e.get("mission") != "W-DATA-01-A" or
            e.get("plan_sha256") != R1_APPLY_DIGEST for e in events)):
        raise ValueError("RUC R1 não corresponde ao plano pinado")
    if ([e.get("event") for e in events] !=
            ["PREFLIGHT", "AUTH_VERIFIED", "START", "ATTEMPT", "VERIFIED", "ABORT"] or
            events[2].get("issues") != list(ISSUES) or
            events[3].get("issue") != 8 or events[3].get("field") != FIELD or
            events[3].get("before") is not None or events[3].get("after_expected") != "CH-1" or
            events[4].get("issue") != 8 or events[4].get("field") != FIELD or
            events[4].get("after") != "CH-1" or
            events[3].get("card_id") != events[4].get("card_id") or
            events[5].get("confirmed") != [8] or events[5].get("uncertain_issue") is not None):
        raise ValueError("RUC R1 não comprova execução exclusiva e verificada de #8")
    return events, hashlib.sha256(raw).hexdigest()


def make_resume_plan(ch1: dict, context: dict, events: list[dict],
                     audit_sha: str, *, captured_at: str | None = None) -> dict:
    reference = validate_ch1(ch1)
    if (len(events) != 6 or events[4].get("event") != "VERIFIED" or
            events[4].get("issue") != 8 or
            events[4].get("card_id") != reference[8]["card_id"] or
            not isinstance(audit_sha, str) or len(audit_sha) != 64):
        raise ValueError("Prova R1 não vincula o cartão #8")
    project_id, field_id, options = _project_schema(context)
    cards = _items(context)
    precondition, changes = None, []
    for n in ISSUES:
        card, historic = cards[n], reference[n]
        if (card["id"] != historic["card_id"] or field_id != historic["field_id"] or
                options[TARGETS[n]] != historic["option_id"]):
            raise ValueError(f"#{n}: identidade/options mudaram desde CH-1")
        preserve = _preserved(card)
        for key in ("Etapa CH", "Esteira"):
            old = historic["preserve"][key]
            if preserve[key] != (None if old == "NÃO_OBSERVADO" else old):
                raise ValueError(f"#{n}: campo {key} mudou")
        actual = _value(card, FIELD)
        if actual != ("CH-1" if n == 8 else None):
            raise ValueError(f"#{n}: pré-condição de Autonomia CH divergente")
        entry = {"issue": n, "card_id": card["id"],
                 "issue_url": f"https://github.com/{REPO}/issues/{n}",
                 "field": FIELD, "field_id": field_id,
                 "option_id": options[TARGETS[n]],
                 "before": "CH-1" if n == 8 else None,
                 "after": TARGETS[n], "preserve_before": preserve}
        if n == 8:
            precondition = entry
        else:
            changes.append(entry)
    data = {"schema": RESUME_SCHEMA, "repo": REPO, "owner": OWNER,
            "project": PROJECT, "project_id": project_id, "field": FIELD,
            "field_id": field_id, "source_ch1_digest_sha256": CH1_DIGEST,
            "source_snapshot_digest_sha256": SNAPSHOT_DIGEST,
            "source_r1_plan_sha256": R1_APPLY_DIGEST,
            "source_r1_audit_sha256": audit_sha,
            "prepared_at_utc": captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "issues": list(RESUME_ISSUES), "precondition": precondition,
            "changes": changes, "mutations_authorized": False}
    return {**data, "digest_sha256": digest(data)}


def validate_resume_plan(plan: dict) -> list[dict]:
    keys = {"schema", "repo", "owner", "project", "project_id", "field",
            "field_id", "source_ch1_digest_sha256", "source_snapshot_digest_sha256",
            "source_r1_plan_sha256", "source_r1_audit_sha256", "prepared_at_utc",
            "issues", "precondition", "changes", "mutations_authorized", "digest_sha256"}
    if not isinstance(plan, dict) or set(plan) != keys:
        raise ValueError("Schema R2 inválido")
    assert_digest(plan)
    if (plan["schema"] != RESUME_SCHEMA or plan["owner"] != OWNER or
            plan["repo"] != REPO or plan["project"] != PROJECT or
            plan["field"] != FIELD or plan["issues"] != list(RESUME_ISSUES) or
            plan["source_ch1_digest_sha256"] != CH1_DIGEST or
            plan["source_snapshot_digest_sha256"] != SNAPSHOT_DIGEST or
            plan["source_r1_plan_sha256"] != R1_APPLY_DIGEST or
            not isinstance(plan["source_r1_audit_sha256"], str) or
            len(plan["source_r1_audit_sha256"]) != 64 or
            plan["mutations_authorized"] is not False or
            not isinstance(plan["project_id"], str) or not plan["project_id"] or
            not isinstance(plan["field_id"], str) or not plan["field_id"] or
            not isinstance(plan["changes"], list) or len(plan["changes"]) != 4):
        raise ValueError("R2 fora da allowlist")
    for n, item in zip(ISSUES, [plan["precondition"], *plan["changes"]]):
        if (not isinstance(item, dict) or set(item) !=
                {"issue", "card_id", "issue_url", "field", "field_id", "option_id",
                 "before", "after", "preserve_before"} or item["issue"] != n or
                item["field"] != FIELD or item["field_id"] != plan["field_id"] or
                item["after"] != TARGETS[n] or
                item["before"] != ("CH-1" if n == 8 else None) or
                item["issue_url"] != f"https://github.com/{REPO}/issues/{n}" or
                not isinstance(item["card_id"], str) or
                not item["card_id"].startswith("PVTI_") or
                not isinstance(item["option_id"], str) or not item["option_id"] or
                not isinstance(item["preserve_before"], dict) or
                set(item["preserve_before"]) != set(PRESERVE) or
                any(v is not None and not isinstance(v, str)
                    for v in item["preserve_before"].values())):
            raise ValueError(f"#{n}: campo/estado inválido no plano R2")
    timestamp = datetime.fromisoformat(plan["prepared_at_utc"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or not (-timedelta(minutes=2) <=
            datetime.now(timezone.utc) - timestamp <= MAX_PLAN_AGE):
        raise ValueError("Plano R2 expirado ou horário inválido")
    return plan["changes"]


def check_resume_live(plan: dict, context: dict, verified: set[int]) -> None:
    project_id, field_id, options = _project_schema(context)
    if project_id != plan["project_id"] or field_id != plan["field_id"]:
        raise ValueError("ID Project/Field R2 alterado")
    items = _items(context)
    for entry in [plan["precondition"], *plan["changes"]]:
        n = entry["issue"]
        expected = entry["after"] if n == 8 or n in verified else None
        card = items[n]
        if (card["id"] != entry["card_id"] or
                options[entry["after"]] != entry["option_id"] or
                _value(card, FIELD) != expected or
                _preserved(card) != entry["preserve_before"]):
            raise ValueError(f"#{n}: estado LIVE divergente, abortar R2")


def resume_approval_statement(plan_sha: str) -> str:
    return (f"APROVO CH-DATA-01 RETOMAR PROJECT#2 LOTE01-R2 SHA256={plan_sha} "
            "#8=CH-1(PRESERVAR) #10=CH-1 #12=CH-0 #13=CH-0 #24=CH-1 CAMPO=Autonomia CH")


def verify_resume_approval(comment: dict, plan: dict, comment_id: int) -> str:
    if (not isinstance(comment, dict) or type(comment_id) is not int or
            comment.get("id") != comment_id or
            comment.get("issue_url") != f"https://api.github.com/repos/{REPO}/issues/62" or
            not isinstance(comment.get("user"), dict) or
            comment["user"].get("login") != OWNER):
        raise ValueError("Aprovação R2 não publicada pelo PO na Issue #62")
    body = comment.get("body")
    if (not isinstance(body, str) or
            resume_approval_statement(plan["digest_sha256"]) not in body.splitlines() or
            "ACEITO RISCO RESIDUAL DE CONCORRENCIA SEM CAS ATOMICO" not in body.splitlines() or
            not isinstance(comment.get("created_at"), str) or
            not isinstance(comment.get("updated_at"), str)):
        raise ValueError("Comentário R2 sem digest e risco exatos")
    return digest({"id": comment_id, "author": OWNER, "body": body,
                   "issue_url": comment["issue_url"],
                   "created_at": comment["created_at"], "updated_at": comment["updated_at"]})


def apply_resume_plan(plan: dict, comment_id: int, *,
                      schema_reader: Callable[[], dict], items_reader: Callable[[], dict],
                      proof_reader: Callable[[int], dict], graphql_set: Callable[[dict], str],
                      audit: Callable[[dict], None], interactive: bool,
                      prompt: Callable[[str], str]) -> int:
    """Cache de schema apenas; itens LIVE são relidos antes/depois de cada mutation."""
    changes = validate_resume_plan(plan)
    if not interactive or not callable(audit):
        raise ValueError("TTY e auditoria R2 obrigatórios")
    verified: set[int] = set()
    uncertain = None
    fingerprint = verify_resume_approval(proof_reader(comment_id), plan, comment_id)
    try:
        initial = schema_reader()
        check_resume_live(plan, initial, verified)
        schema_cache = {"project": initial["project"], "fields": initial["fields"]}
        audit({"event": "PREFLIGHT_R2", "r1_audit_sha256": plan["source_r1_audit_sha256"],
               "approval_comment_id": comment_id, "approval_fingerprint": fingerprint})
        phrase = "APROVO CH-DATA-01 R2 " + plan["digest_sha256"][:12]
        if prompt(f"Digite exatamente '{phrase}' (gate R2 do PO): ") != phrase:
            raise ValueError("Confirmação interativa R2 ausente")
        audit({"event": "AUTH_VERIFIED_R2", "approval_comment_id": comment_id})
        audit({"event": "START_R2", "issues": list(RESUME_ISSUES), "precondition_issue": 8})
        for change in changes:
            n = change["issue"]
            if verify_resume_approval(proof_reader(comment_id), plan, comment_id) != fingerprint:
                raise ValueError("Autorização R2 mudou")
            check_resume_live(plan, {**schema_cache, "items": items_reader()}, verified)
            audit({"event": "ATTEMPT_R2", "issue": n, "field": FIELD,
                   "card_id": change["card_id"], "before": None,
                   "after_expected": change["after"]})
            uncertain = n
            got = graphql_set({"projectId": plan["project_id"],
                               "itemId": change["card_id"], "fieldId": plan["field_id"],
                               "optionId": change["option_id"]})
            if got != change["card_id"]:
                raise RuntimeError(f"#{n}: GraphQL retornou card divergente")
            check_resume_live(plan, {**schema_cache, "items": items_reader()}, verified | {n})
            audit({"event": "VERIFIED_R2", "issue": n, "field": FIELD,
                   "card_id": change["card_id"], "before": None, "after": change["after"]})
            verified.add(n)
            uncertain = None
        check_resume_live(plan, schema_reader(), verified)
        audit({"event": "COMPLETE_R2", "confirmed": sorted(verified),
               "mutations_verified": len(verified), "execution_authorized": False})
        return len(verified)
    except Exception as exc:
        event = ("UNCERTAIN_R2" if uncertain is not None else
                 "BLOCKED_PREWRITE_R2" if not verified else "ABORT_R2")
        try:
            audit({"event": event, "confirmed": sorted(verified),
                   "uncertain_issue": uncertain, "reason_type": type(exc).__name__})
        except Exception:
            pass
        raise RuntimeError(f"RETOMADA R2 PARCIAL: {len(verified)} verificadas; "
                           f"incerta=#{uncertain}; não repetir sem reconciliação") from exc


def approval_statement(digest_sha256: str) -> str:
    return (f"APROVO CH-DATA-01 APLICAR PROJECT#2 LOTE01 SHA256={digest_sha256} "
            "#8=CH-1 #10=CH-1 #12=CH-0 #13=CH-0 #24=CH-1 CAMPO=Autonomia CH")


def verify_approval(comment: dict, plan: dict, comment_id: int) -> str:
    if not isinstance(comment, dict) or comment.get("id") != comment_id:
        raise ValueError("Comentário de aprovação inválido")
    who = comment.get("user")
    if (not isinstance(who, dict) or who.get("login") != OWNER
            or comment.get("issue_url") != f"https://api.github.com/repos/{REPO}/issues/62"):
        raise ValueError("Autorização não foi publicada pelo PO na Issue #62")
    lines = comment.get("body")
    if (not isinstance(lines, str) or approval_statement(plan["digest_sha256"]) not in lines.splitlines()
            or "ACEITO RISCO RESIDUAL DE CONCORRENCIA SEM CAS ATOMICO" not in lines.splitlines()):
        raise ValueError("Autorização não contém digest, matriz e risco aceito literalmente")
    if (not isinstance(comment.get("updated_at"), str)
            or not isinstance(comment.get("created_at"), str)):
        raise ValueError("Prova não tem timestamp auditável")
    return digest({"id": comment_id, "author": who["login"], "body": lines,
                   "created_at": comment["created_at"], "updated_at": comment["updated_at"],
                   "issue_url": comment["issue_url"]})


def apply_plan(plan: dict, comment_id: int, *, reader: Callable[[], dict],
               proof_reader: Callable[[int], dict], graphql_set: Callable[[dict], str],
               audit: Callable[[dict], None], interactive: bool, prompt: Callable[[str], str]) -> int:
    """Execução totalmente injetável; testes offline nunca chamam rede."""
    changes = validate_apply_plan(plan)
    if not interactive:
        raise ValueError("TTY humana obrigatória; cron/CI e não interativo bloqueados")
    if not callable(audit):
        raise ValueError("Auditoria persistente obrigatória")
    verified: set[int] = set()
    uncertain: int | None = None
    proof = proof_reader(comment_id)
    fingerprint = verify_approval(proof, plan, comment_id)
    try:
        check_live(plan, reader(), verified)
        audit({"event": "PREFLIGHT", "plan_sha256": plan["digest_sha256"],
               "approval_comment_id": comment_id, "approval_fingerprint": fingerprint})
        phrase = "APROVO CH-DATA-01 " + plan["digest_sha256"][:12]
        if prompt(f"Digite exatamente '{phrase}' (gate CH-2 do PO): ") != phrase:
            raise ValueError("Confirmação humana ausente")
        if verify_approval(proof_reader(comment_id), plan, comment_id) != fingerprint:
            raise ValueError("Comentário do PO foi alterado")
        audit({"event": "AUTH_VERIFIED", "approval_comment_id": comment_id,
               "approval_fingerprint": fingerprint})
        audit({"event": "START", "issues": list(ISSUES), "field": FIELD})
        for entry in changes:
            number = entry["issue"]
            if verify_approval(proof_reader(comment_id), plan, comment_id) != fingerprint:
                raise ValueError("Comentário de aprovação alterado durante lote")
            check_live(plan, reader(), verified)
            audit({"event": "ATTEMPT", "issue": number, "card_id": entry["card_id"],
                   "field": FIELD, "before": None, "after_expected": entry["after"]})
            uncertain = number  # Mesmo após timeout, a mutation pode ter sido aplicada.
            item_id = graphql_set({"projectId": plan["project_id"],
                                   "itemId": entry["card_id"], "fieldId": plan["field_id"],
                                   "optionId": entry["option_id"]})
            if item_id != entry["card_id"]:
                raise RuntimeError(f"#{number}: GraphQL retornou Card ID divergente")
            check_live(plan, reader(), verified | {number})
            audit({"event": "VERIFIED", "issue": number, "card_id": entry["card_id"],
                   "field": FIELD, "before": None, "after": entry["after"]})
            verified.add(number)
            uncertain = None
        check_live(plan, reader(), verified)
        audit({"event": "COMPLETE", "confirmed": len(verified), "execution_authorized": False})
        return len(verified)
    except Exception as exc:
        event = "UNCERTAIN" if uncertain is not None else ("BLOCKED_PREWRITE" if not verified else "ABORT")
        try:
            audit({"event": event, "confirmed": sorted(verified), "uncertain_issue": uncertain,
                   "reason_type": type(exc).__name__})
        except Exception:
            pass
        raise RuntimeError(f"LOTE NÃO CONCLUÍDO: {len(verified)} verificadas; "
                           f"incerta=#{uncertain}; não repetir sem reconciliação") from exc


def _write_unique(path: Path, data: dict) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _audit_open(path: Path):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8")


def _audit_record(handle, plan_sha: str, *, mission: str = "W-DATA-01-A"):
    def write(record: dict) -> None:
        entry = {"protocol": "RUC/1.0", "mission": mission,
                 "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                 "plan_sha256": plan_sha, **record}
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return write


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ch1-plan", type=Path, help="Plano detalhado CH-1 homologado")
    parser.add_argument("--plan-output", type=Path, help="Gravar plano EXECUTÁVEL novo, sem aplicar")
    parser.add_argument("--apply-plan", type=Path, help="Aplicação somente com aprovação CH-2 posterior")
    parser.add_argument("--approval-comment", type=int)
    parser.add_argument("--confirm", help="Digest completo de plano executável (além do TTY)")
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--resume-r2", action="store_true")
    parser.add_argument("--r1-audit", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.apply_plan is None:
            if (args.approval_comment or args.confirm or args.audit_file):
                raise ValueError("Argumentos de escrita proibidos em dry-run")
            if args.resume_r2 != (args.r1_audit is not None):
                raise ValueError("R2 exige --resume-r2 e --r1-audit juntos")
            if args.resume_r2 and args.plan_output is None:
                raise ValueError("R2 exige --plan-output exclusivo")
            if not args.ch1_plan:
                raise ValueError("Informe --ch1-plan em modo de leitura")
            ch1 = json.loads(args.ch1_plan.read_text(encoding="utf-8"))
            if args.plan_output is None:
                validate_ch1(ch1)
                print("CH-1 homologado; MATRIZ APENAS CONSULTIVA; nenhuma chamada de escrita")
                return 0
            if args.resume_r2:
                events, audit_sha = read_r1_audit(args.r1_audit)
                plan = make_resume_plan(ch1, live_reader(), events, audit_sha)
                validate_resume_plan(plan)
            else:
                plan = make_apply_plan(ch1, live_reader())
            _write_unique(args.plan_output, plan)
            print("PLANO EXECUTÁVEL GERADO, NÃO AUTORIZADO PARA EXECUÇÃO")
            print("Digest SHA-256:", plan["digest_sha256"])
            return 0
        if (args.ch1_plan or args.plan_output or args.resume_r2
                or args.approval_comment is None or not args.confirm or args.audit_file is None):
            raise ValueError("Aplicação exige --apply-plan --confirm --approval-comment --audit-file")
        plan = json.loads(args.apply_plan.read_text(encoding="utf-8"))
        if plan.get("schema") == RESUME_SCHEMA:
            validate_resume_plan(plan)
            if args.r1_audit is None:
                raise ValueError("R2 exige a auditoria R1 original")
            _, audit_sha = read_r1_audit(args.r1_audit)
            if audit_sha != plan["source_r1_audit_sha256"]:
                raise ValueError("RUC R1 não coincide com plano R2")
        else:
            if args.r1_audit is not None:
                raise ValueError("RUC R1 não pertence à aplicação R1")
            validate_apply_plan(plan)
        if args.confirm != plan["digest_sha256"]:
            raise ValueError("Digest completo incorreto")
        if not sys.stdin.isatty():
            raise ValueError("Aplicação exige TTY humano")
        with _audit_open(args.audit_file) as out:
            audit = _audit_record(out, plan["digest_sha256"],
                      mission="W-DATA-01-B" if plan["schema"] == RESUME_SCHEMA else "W-DATA-01-A")
            if plan["schema"] == RESUME_SCHEMA:
                result = apply_resume_plan(plan, args.approval_comment,
                             schema_reader=live_reader,
                             items_reader=lambda: _module().fetch_project(),
                             proof_reader=approval_reader, graphql_set=set_only,
                             audit=audit, interactive=True, prompt=input)
            else:
                result = apply_plan(plan, args.approval_comment, reader=live_reader,
                                    proof_reader=approval_reader, graphql_set=set_only,
                                    audit=audit, interactive=True, prompt=input)
        print(f"LOTE VERIFICADO: {result} campos Autonomia CH")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"BLOQUEADO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())