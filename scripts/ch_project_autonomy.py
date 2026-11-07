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


def _audit_record(handle, plan_sha: str):
    def write(record: dict) -> None:
        entry = {"protocol": "RUC/1.0", "mission": "W-DATA-01-A",
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
    args = parser.parse_args(argv)
    try:
        if args.apply_plan is None:
            if (args.approval_comment or args.confirm or args.audit_file):
                raise ValueError("Argumentos de escrita proibidos em dry-run")
            if not args.ch1_plan:
                raise ValueError("Informe --ch1-plan em modo de leitura")
            ch1 = json.loads(args.ch1_plan.read_text(encoding="utf-8"))
            if args.plan_output is None:
                validate_ch1(ch1)
                print("CH-1 homologado; MATRIZ APENAS CONSULTIVA; nenhuma chamada de escrita")
                return 0
            plan = make_apply_plan(ch1, live_reader())
            _write_unique(args.plan_output, plan)
            print("PLANO EXECUTÁVEL GERADO, NÃO AUTORIZADO PARA EXECUÇÃO")
            print("Digest SHA-256:", plan["digest_sha256"])
            return 0
        if (args.ch1_plan or args.plan_output or args.approval_comment is None
                or not args.confirm or args.audit_file is None):
            raise ValueError("Aplicação exige --apply-plan --confirm --approval-comment --audit-file")
        plan = json.loads(args.apply_plan.read_text(encoding="utf-8"))
        validate_apply_plan(plan)
        if args.confirm != plan["digest_sha256"]:
            raise ValueError("Digest completo incorreto")
        if not sys.stdin.isatty():
            raise ValueError("Aplicação exige TTY humano")
        with _audit_open(args.audit_file) as out:
            result = apply_plan(plan, args.approval_comment, reader=live_reader,
                                proof_reader=approval_reader, graphql_set=set_only,
                                audit=_audit_record(out, plan["digest_sha256"]),
                                interactive=True, prompt=input)
        print(f"LOTE VERIFICADO: {result} campos Autonomia CH")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"BLOQUEADO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())