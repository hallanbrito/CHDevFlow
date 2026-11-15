"""F7: publicacao de escalonamento com gate do PO; nenhuma escrita por default.

Publica somente comentario em Issue elegivel. Nao admite ou modifica Project #2.
Toda operacao remota exige plano pinado, autorizacao LIVE e readback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable

from chdevflow.core.intake import validate_issue
from chdevflow.core.po_escalation import (
    EVIDENCE_FILES, OWNER, PROJECT, REPO, SCHEMA, _safe_outbox,
    build_escalation_preview, write_receipt_once,
)

APPROVAL_ISSUE = 63
PLAN_SCHEMA = "CHDEVFLOW-F7-COMMENT-PLAN/1"
RECEIPT_SCHEMA = "CHDEVFLOW-F7-COMMENT-PENDING/1"
MAX_COMMENT_PAGES = 15
MARKER_PREFIX = "<!-- CHDEVFLOW-F7-EXECUTION:"
HEX32 = re.compile(r"^[0-9a-f]{32}$")


class PublicationError(ValueError):
    """Bloqueio seguro antes de escrever."""


class PublicationPending(RuntimeError):
    """Escrita pode ter ocorrido; nao repetir sem reconciliacao LIVE."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _gh_json(*args: str, expected_type: type = dict) -> Any:
    """Comunicacao GH por bytes UTF-8, sem locale cp1252 e sem expor stderr."""
    try:
        done = subprocess.run(
            ["gh", *args], capture_output=True, stdin=subprocess.DEVNULL,
            check=False, timeout=35)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError("GitHub CLI indisponivel; sem escrita") from exc
    if done.returncode:
        raise PublicationError("Consulta GitHub negada/indisponivel; sem escrita")
    try:
        parsed = json.loads(done.stdout.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, AttributeError) as exc:
        raise PublicationError("GitHub CLI retornou JSON/UTF-8 invalido") from exc
    if not isinstance(parsed, expected_type):
        raise PublicationError("GitHub CLI retornou formato inesperado")
    return parsed


def _issue_comments(issue: int) -> list[dict]:
    comments: list[dict] = []
    for page in range(1, MAX_COMMENT_PAGES + 1):
        page_data = _gh_json(
            "api",
            f"repos/{REPO}/issues/{issue}/comments?per_page=100&page={page}",
            expected_type=list)
        if len(page_data) > 100:
            raise PublicationError("Pagina de comentarios excessiva")
        comments.extend(page_data)
        if len(page_data) < 100:
            return comments
    raise PublicationError("Comentarios nao exaustivos; sem publicar")


def _live_context(issue: int, approval_comment: int) -> dict:
    if type(issue) is not int or issue < 1 or type(approval_comment) is not int or approval_comment < 1:
        raise PublicationError("Identificadores de consulta invalidos")
    who = _gh_json("api", "user")
    if who.get("login") != OWNER:
        raise PublicationError("Sessao gh nao pertence ao PO responsavel")
    repository = _gh_json("api", f"repos/{REPO}")
    perms = repository.get("permissions")
    if not isinstance(perms, dict) or not any(
        perms.get(k) is True for k in ("push", "maintain", "admin")
    ):
        raise PublicationError("Permissao LIVE de escrita na Issue nao comprovada")
    target = _gh_json(
        "issue", "view", str(issue), "-R", REPO,
        "--json", "id,number,title,body,labels,state,url")
    project = _gh_json(
        "project", "item-list", str(PROJECT), "--owner", OWNER,
        "--format", "json", "-L", "500")
    approval = _gh_json(
        "api", f"repos/{REPO}/issues/comments/{approval_comment}")
    return {
        "who": who, "repository": repository, "issue": target,
        "project": project, "approval": approval,
        "comments": _issue_comments(issue),
    }


def _expected_comment(outbox: dict, approval_id: int) -> str:
    marker = MARKER_PREFIX + outbox["execution_id"] + " -->"
    return (
        "CHDevFlow F7 — Escalonamento para decisao do PO\n\n"
        f"Execucao: {outbox['execution_id']}\n"
        f"Missao: {outbox['mission_id']}\n"
        f"Issue de origem: #{outbox['issue']}\n"
        "Estado: AGUARDANDO_PO (3 reprovacoes / 2 devolucoes)\n"
        f"SHA-256 do codigo: {outbox['code_sha256']}\n"
        f"Autorizacao especifica: comentario #{approval_id}\n\n"
        "Evidencias locais permanecem sob custodia do PO. "
        "Esta publicacao nao autoriza admissao no Project #2, "
        "merge, deploy, execucao de agentes nem alteracao de campos.\n\n"
        + marker
    )


def _approval_fingerprint(proof: dict, outbox: dict) -> dict:
    if not isinstance(proof, dict):
        raise PublicationError("Comentario PO invalido")
    approval_id = proof.get("id")
    if type(approval_id) is not int or approval_id < 1:
        raise PublicationError("ID de aprovacao invalido")
    if not isinstance(proof.get("user"), dict) or proof["user"].get("login") != OWNER:
        raise PublicationError("Autor da aprovacao nao e o PO")
    allowed_urls = {
        f"https://api.github.com/repos/{REPO}/issues/{outbox['issue']}",
        f"https://api.github.com/repos/{REPO}/issues/{APPROVAL_ISSUE}",
    }
    if proof.get("issue_url") not in allowed_urls:
        raise PublicationError("Aprovacao PO vinculada a Issue incorreta")
    statement = (
        f"CH-GOV-01 F7 PUBLICAR PROJECT#{PROJECT} ISSUE#{outbox['issue']} "
        f"EXECUTION#{outbox['execution_id']} SHA256={outbox['code_sha256']} "
        "ACTION=COMMENT_ONLY"
    )
    body = proof.get("body")
    if not isinstance(body, str) or statement not in body.splitlines():
        raise PublicationError("Autorizacao nao confere com execucao/acao/SHA")
    return {
        "id": approval_id, "updated_at": proof.get("updated_at"),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "issue_url": proof["issue_url"], "login": OWNER,
    }


def _comment_snapshot(comments: list[dict]) -> list[dict]:
    if not isinstance(comments, list) or len(comments) > MAX_COMMENT_PAGES * 100:
        raise PublicationError("Colecao de comentarios invalida")
    seen: set[int] = set()
    normalized: list[dict] = []
    for comment in comments:
        if not isinstance(comment, dict):
            raise PublicationError("Comentario malformado")
        ident = comment.get("id")
        if type(ident) is not int or ident <= 0 or ident in seen:
            raise PublicationError("Comentario duplicado ou sem ID")
        seen.add(ident)
        body = comment.get("body")
        author = comment.get("user")
        if not isinstance(body, str) or not isinstance(author, dict):
            raise PublicationError("Comentario com corpo/autor invalido")
        normalized.append({
            "id": ident, "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "author": author.get("login"), "updated_at": comment.get("updated_at"),
        })
    return sorted(normalized, key=lambda c: c["id"])


def _eligible_outbox(path: Path) -> dict:
    outbox = _safe_outbox(path)
    if (outbox.get("schema") != SCHEMA
            or not isinstance(outbox.get("code_sha256"), str)
            or outbox.get("evidence_files") != list(EVIDENCE_FILES)):
        raise PublicationError("Outbox legada/incompleta: somente preview F7")
    return outbox


def build_publication_plan(outbox: dict, context: dict) -> dict:
    """Plano puro: bloqueia Intake invalido, duplicidade e autorizacao implicita."""
    if not isinstance(context, dict):
        raise PublicationError("Contexto LIVE ausente")
    if (context.get("who", {}).get("login") != OWNER or
            not isinstance(context.get("repository", {}).get("permissions"), dict)
            or not any(context["repository"]["permissions"].get(k) is True
                       for k in ("push", "maintain", "admin"))):
        raise PublicationError("Identidade/ACL LIVE de publicacao ausente")
    if outbox.get("schema") != SCHEMA:
        raise PublicationError("Apenas outbox completa pode ser publicada")
    if not HEX32.fullmatch(outbox.get("execution_id", "")):
        raise PublicationError("Execution ID invalido")
    issue = context.get("issue")
    if (not isinstance(issue, dict) or issue.get("number") != outbox["issue"]
            or issue.get("state") != "OPEN"
            or issue.get("url") != f"https://github.com/{REPO}/issues/{outbox['issue']}"):
        raise PublicationError("Identidade/estado da Issue LIVE divergente")
    diagnosis = validate_issue(issue)
    if diagnosis["content_status"] != "CONTENT_VALID":
        raise PublicationError(
            "Intake F1 bloqueou publicacao: " + diagnosis["content_status"]
            + " " + ", ".join(diagnosis["reasons"]))
    preview = build_escalation_preview(
        outbox, context.get("project"), intake_issue=issue)
    approval = _approval_fingerprint(context.get("approval"), outbox)
    comment_text = _expected_comment(outbox, approval["id"])
    marker = MARKER_PREFIX + outbox["execution_id"] + " -->"
    normalized = _comment_snapshot(context.get("comments"))
    matches = [c for c in context["comments"] if marker in c["body"]]
    if len(matches) > 1:
        raise PublicationError("Colisao de comentarios de mesma execucao")
    found_id = None
    if matches:
        only = matches[0]
        if (only.get("body") != comment_text or
                only.get("user", {}).get("login") != OWNER):
            raise PublicationError("Marcador de execucao reutilizado sem autenticidade")
        found_id = only["id"]
    snapshot = {
        "issue": _digest({
            "id": issue.get("id"), "number": issue["number"], "body": issue.get("body"),
            "title": issue.get("title"), "labels": issue.get("labels"),
            "state": issue["state"], "url": issue["url"],
        }),
        "project": _digest(context["project"]),
        "comments": _digest(normalized),
        "approval": _digest(approval),
        "identity": _digest({
            "who": context["who"].get("login"),
            "permissions": context["repository"].get("permissions"),
        }),
    }
    data = {
        "schema": PLAN_SCHEMA, "repo": REPO, "project": PROJECT,
        "issue": outbox["issue"], "execution_id": outbox["execution_id"],
        "mission_id": outbox["mission_id"], "code_sha256": outbox["code_sha256"],
        "approval_comment": approval["id"],
        "project_state": preview["state"],
        "action": "ALREADY_PUBLISHED" if found_id else "POST_COMMENT",
        "published_comment_id": found_id,
        "body": comment_text, "snapshot": snapshot,
        "remote_project_writes": 0,
    }
    return {**data, "digest": _digest(data)}


def _post_comment(issue: int, body: str) -> dict:
    """Unica escrita permitida: um comentario na Issue; sem retry."""
    return _gh_json(
        "api", "-X", "POST", f"repos/{REPO}/issues/{issue}/comments",
        "-f", "body=" + body)


def apply_publication_plan(
    outbox_path: Path, plan: dict, confirmation: str, *,
    reader: Callable[[int, int], dict] = _live_context,
    poster: Callable[[int, str], dict] = _post_comment,
    audit: Callable[[dict], None],
    human_prompt: Callable[[str], str] = input,
) -> dict:
    """Uma tentativa, guardada por digest, frase PO e duplo snapshot LIVE."""
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise PublicationError("Plano F7 invalido")
    supplied_digest = plan.get("digest")
    if (not isinstance(supplied_digest, str)
            or supplied_digest != _digest({k: v for k, v in plan.items() if k != "digest"})
            or confirmation != supplied_digest):
        raise PublicationError("Plano/digest nao confirmado")
    outbox = _eligible_outbox(outbox_path)
    if (plan.get("issue") != outbox["issue"]
            or plan.get("execution_id") != outbox["execution_id"]
            or plan.get("code_sha256") != outbox["code_sha256"]
            or type(plan.get("approval_comment")) is not int):
        raise PublicationError("Plano nao pertence a outbox")
    def current_plan() -> dict:
        return build_publication_plan(
            outbox, reader(outbox["issue"], plan["approval_comment"]))
    if current_plan() != plan:
        raise PublicationError("Snapshot LIVE mudou: recriar plano, zero escrita")
    phrase = "APROVO F7 PUBLICAR " + supplied_digest[:12]
    if human_prompt(f"Digite exatamente {phrase}: ") != phrase:
        raise PublicationError("Confirmacao humana individual negada")
    if plan["action"] == "ALREADY_PUBLISHED":
        audit({"event": "ALREADY_PUBLISHED", "comment_id": plan["published_comment_id"]})
        return {"status": "JA_PUBLICADO", "comment_id": plan["published_comment_id"],
                "remote_writes": 0}
    if plan["action"] != "POST_COMMENT" or plan.get("published_comment_id") is not None:
        raise PublicationError("Acao de publicacao fora do escopo")
    if current_plan() != plan:
        raise PublicationError("Corrida detectada antes de publicar; zero escrita")
    audit({"event": "ATTEMPT_POST", "execution_id": outbox["execution_id"],
           "issue": outbox["issue"], "digest": supplied_digest})
    try:
        posted = poster(outbox["issue"], plan["body"])
    except Exception as exc:
        audit({"event": "PENDENTE_PUBLICACAO", "reason": "POST_INCONCLUSIVO"})
        raise PublicationPending(
            "Envio inconclusivo; reconciliar comentarios LIVE antes de tentar novamente") from exc
    try:
        if not isinstance(posted, dict) or type(posted.get("id")) is not int:
            raise PublicationError("Resposta de POST sem ID de comentario")
        ctx = reader(outbox["issue"], plan["approval_comment"])
        observed = build_publication_plan(outbox, ctx)
        if (observed["action"] != "ALREADY_PUBLISHED"
                or observed["published_comment_id"] != posted["id"]
                or observed["body"] != plan["body"]
                or observed["snapshot"]["issue"] != plan["snapshot"]["issue"]
                or observed["snapshot"]["project"] != plan["snapshot"]["project"]
                or observed["snapshot"]["approval"] != plan["snapshot"]["approval"]):
            raise PublicationError("Readback nao confirmou comentario unico")
    except Exception as exc:
        audit({"event": "PENDENTE_PUBLICACAO", "reason": "READBACK_INCONCLUSIVO"})
        raise PublicationPending(
            "Escrita possivel/realizada; reconciliar LIVE, nao repetir automaticamente") from exc
    audit({"event": "PUBLICADO_VERIFICADO", "comment_id": posted["id"]})
    return {"status": "PUBLICADO_VERIFICADO", "comment_id": posted["id"],
            "remote_writes": 1}


def _write_json_once(path: Path, payload: dict) -> None:
    if (path.exists() or path.is_symlink() or not path.parent.is_dir()
            or path.parent.is_symlink()):
        raise PublicationError("Plano ja existe ou destino inseguro")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _audit_writer(path: Path):
    if (path.exists() or path.is_symlink() or not path.parent.is_dir()
            or path.parent.is_symlink()):
        raise PublicationError("Auditoria existe ou destino invalido")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    handle = os.fdopen(fd, "w", encoding="utf-8")
    def record(data: dict) -> None:
        handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return handle, record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="F7 publicacao por comentario: preview por padrao, sem escrita")
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--approval-comment", type=int)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--confirm")
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.apply_plan:
            if (args.plan_file or args.approval_comment or
                    not args.confirm or args.audit_file is None):
                raise PublicationError(
                    "Aplicacao exige somente --apply-plan, --confirm e --audit-file")
            plan = json.loads(args.apply_plan.read_text(encoding="utf-8"))
            handle, audit = _audit_writer(args.audit_file)
            with handle:
                try:
                    result = apply_publication_plan(
                        args.outbox, plan, args.confirm, audit=audit)
                except PublicationPending:
                    receipt = {
                        "schema": RECEIPT_SCHEMA, "publication_status": "PENDENTE_PUBLICACAO",
                        "issue": plan.get("issue"), "execution_id": plan.get("execution_id"),
                        "remote_effect": "INDETERMINADO", "retry_agents": False,
                        "requires_reconciliation": True,
                    }
                    receipt_path = args.audit_file.with_suffix(".pending.json")
                    write_receipt_once(receipt_path, receipt)
                    raise
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.confirm or args.audit_file:
            raise PublicationError("Confirmacao somente no modo --apply-plan")
        if args.approval_comment is None:
            if args.plan_file:
                raise PublicationError("Plano exige autorizacao PO autenticada")
            print("F7 AGUARDANDO_AUTORIZACAO_PO; writes=0")
            return 0
        outbox = _eligible_outbox(args.outbox)
        plan = build_publication_plan(
            outbox, _live_context(outbox["issue"], args.approval_comment))
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        if args.plan_file:
            _write_json_once(args.plan_file, plan)
        return 0
    except (PublicationError, PublicationPending, ValueError, OSError,
            UnicodeError, subprocess.SubprocessError) as exc:
        # Nunca imprimir conteudo do GitHub CLI, secrets nem body de erro remoto.
        print("F7 PUBLICACAO BLOQUEADA: " + str(exc)[:250], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
