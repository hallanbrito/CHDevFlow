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
from chdevflow.core.experimental_pilot import _is_link
from chdevflow.core.po_escalation_provenance import verify_provenance
from chdevflow.core.po_escalation import (
    EVIDENCE_FILES, EVIDENCE_FILES_TESTS_REPROVADOS,
    OWNER, PROJECT, REPO, SCHEMA, _safe_outbox,
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
    issue_url = approval.get("issue_url")
    allow = {
        f"https://api.github.com/repos/{REPO}/issues/{issue}",
        f"https://api.github.com/repos/{REPO}/issues/{APPROVAL_ISSUE}",
    }
    if issue_url not in allow:
        raise PublicationError("Comentario PO vinculado a Issue inesperada")
    approval_thread_number = int(issue_url.rsplit("/", 1)[1])
    comments = _issue_comments(issue)
    approval_history = (comments if approval_thread_number == issue
                        else _issue_comments(approval_thread_number))
    return {
        "who": who, "repository": repository, "issue": target,
        "project": project, "approval": approval,
        "comments": comments, "approval_history": approval_history,
    }


def _expected_comment(outbox: dict, approval_id: int) -> str:
    marker = MARKER_PREFIX + outbox["execution_id"] + " -->"
    return (
        "CHDevFlow F7 — Escalonamento para decisao do PO\n\n"
        f"Execucao: {outbox['execution_id']}\n"
        f"Missao: {outbox['mission_id']}\n"
        f"Issue de origem: #{outbox['issue']}\n"
        "Estado: AGUARDANDO_PO (3 reprovacoes / 2 devolucoes)\n"
        f"SHA-256 do codigo AGY: {outbox['code_sha256']}\n"
        f"SHA Git base da missao: {outbox['provenance']['base_sha']}\n"
        f"Digest do manifesto: {outbox['provenance']['mission_digest']}\n"
        f"Autorizacao especifica: comentario #{approval_id}\n\n"
        "Evidencias locais permanecem sob custodia do PO. "
        "Esta publicacao nao autoriza admissao no Project #2, "
        "merge, deploy, execucao de agentes nem alteracao de campos.\n\n"
        + marker
    )


def _approval_fingerprint(proof: dict, outbox: dict,
                          history: list[dict]) -> dict:
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
        f"EXECUTION#{outbox['execution_id']} "
        f"CODE_SHA256={outbox['code_sha256']} "
        f"BASE_SHA={outbox['provenance']['base_sha']} "
        f"MISSION_DIGEST={outbox['provenance']['mission_digest']} "
        "ACTION=COMMENT_ONLY"
    )
    body = proof.get("body")
    # Uma declaracao isolada: rejeita linhas contraditorias ou edicoes que
    # mantenham a autorizacao mas acrescentem texto de revogacao.
    if not isinstance(body, str) or body.strip() != statement:
        raise PublicationError("Autorizacao nao confere ou foi alterada/revogada")
    if not isinstance(history, list):
        raise PublicationError("Historico de revogacao do PO indisponivel")
    _comment_snapshot(history)  # fail-closed em paginacao/itens invalidos
    matching = [comment for comment in history
                if comment.get("id") == approval_id]
    if (len(matching) != 1 or matching[0].get("body") != body
            or matching[0].get("user", {}).get("login") != OWNER
            or matching[0].get("updated_at") != proof.get("updated_at")):
        raise PublicationError("Aprovacao nao confirmada no historico LIVE")
    revoke_prefix = (
        f"CH-GOV-01 F7 REVOGAR PROJECT#{PROJECT} ISSUE#{outbox['issue']} "
        f"EXECUTION#{outbox['execution_id']}"
    )
    for comment in history:
        if (comment["id"] > approval_id
                and comment["user"].get("login") == OWNER
                and isinstance(comment.get("body"), str)
                and any(line.strip().startswith(revoke_prefix)
                        for line in comment["body"].splitlines())):
            raise PublicationError("Aprovacao do PO revogada em comentario posterior")
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
    allowed = {
        "CODEX_REPROVOU": EVIDENCE_FILES,
        "TESTES_REPROVADOS": EVIDENCE_FILES_TESTS_REPROVADOS,
    }
    status = outbox.get("third_attempt_status")
    if (outbox.get("schema") != SCHEMA
            or not isinstance(outbox.get("code_sha256"), str)
            or status not in allowed
            or outbox.get("evidence_files") != list(allowed[status])):
        raise PublicationError("Outbox sem causa da terceira reprovacao: somente preview F7")
    # No modo publicacao, a V1 precisa comprovar toda a linha de producao.
    # Preview legado continua permitido em po_escalation.py.
    verify_provenance(path.parent, outbox)
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
    approval = _approval_fingerprint(
        context.get("approval"), outbox, context.get("approval_history"))
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
        "approval_history": _digest(_comment_snapshot(context["approval_history"])),
        "identity": _digest({
            "who": context["who"].get("login"),
            "permissions": context["repository"].get("permissions"),
        }),
    }
    data = {
        "schema": PLAN_SCHEMA, "repo": REPO, "project": PROJECT,
        "issue": outbox["issue"], "execution_id": outbox["execution_id"],
        "mission_id": outbox["mission_id"], "code_sha256": outbox["code_sha256"],
        "mission_digest": outbox["provenance"]["mission_digest"],
        "base_sha": outbox["provenance"]["base_sha"],
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


def _claim_publication(outbox_path: Path, execution_id: str, digest: str) -> Path:
    """Lock local permanente: evita POST concorrente/repetido no mesmo dossie.

    Em erro inconclusivo NAO remover o lock automaticamente. Reconciliacao
    externa e aprovacao humana novas sao obrigatorias para uma segunda tentativa.
    """
    if not HEX32.fullmatch(execution_id):
        raise PublicationError("Execution ID do lock invalido")
    lock = outbox_path.parent / ("f7-publicacao-" + execution_id + ".lock")
    if _is_link(lock) or _is_link(lock.parent) or lock.exists():
        raise PublicationError("Publicacao anterior existe; reconciliar antes de repetir")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PublicationError("Outro executor possui o lock de publicacao") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({
            "schema": RECEIPT_SCHEMA, "execution_id": execution_id,
            "digest": digest, "publication_status": "PENDENTE_PUBLICACAO",
            "remote_effect": "INDETERMINADO",
            "requires_reconciliation": True, "retry_agents": False,
        }, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return lock


def _mark_verified(lock: Path, *, comment_id: int) -> None:
    """Atualiza journal somente DEPOIS do readback confirmado."""
    if type(comment_id) is not int or comment_id <= 0:
        raise PublicationError("Comentario verificado sem ID valido")
    record = json.loads(lock.read_text(encoding="utf-8"))
    if record.get("publication_status") != "PENDENTE_PUBLICACAO":
        raise PublicationError("Estado da tentativa de publicacao divergente")
    record.update({
        "publication_status": "PUBLICADO_VERIFICADO",
        "remote_effect": "CONFIRMADO", "comment_id": comment_id,
        "requires_reconciliation": False,
    })
    temp = lock.with_suffix(".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, lock)


def apply_publication_plan(
    outbox_path: Path, plan: dict, confirmation: str, *,
    reader: Callable[[int, int], dict] | None = None,
    poster: Callable[[int, str], dict] | None = None,
    audit: Callable[[dict], None],
    human_prompt: Callable[[str], str] | None = None,
) -> dict:
    """Uma tentativa, guardada por digest, frase PO e duplo snapshot LIVE."""
    # Callbacks resolvidos em tempo de execucao para simular GitHub no teste
    # da CLI, sem executar qualquer chamada remota verdadeira.
    if reader is None:
        reader = _live_context
    if poster is None:
        poster = _post_comment
    if human_prompt is None:
        human_prompt = input
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
            or plan.get("mission_id") != outbox["mission_id"]
            or plan.get("mission_digest") != outbox["provenance"]["mission_digest"]
            or plan.get("base_sha") != outbox["provenance"]["base_sha"]
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
    journal = _claim_publication(
        outbox_path, outbox["execution_id"], supplied_digest)
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
    try:
        _mark_verified(journal, comment_id=posted["id"])
        audit({"event": "PUBLICADO_VERIFICADO", "comment_id": posted["id"]})
    except Exception as exc:
        # Journal permanece PENDENTE_PUBLICACAO em queda/erro local.
        raise PublicationPending(
            "Readback OK, mas comprovante local inconclusivo; reconciliar LIVE"
        ) from exc
    return {"status": "PUBLICADO_VERIFICADO", "comment_id": posted["id"],
            "remote_writes": 1}


def _write_json_once(path: Path, payload: dict) -> None:
    if (path.exists() or _is_link(path) or not path.parent.is_dir()
            or _is_link(path.parent)):
        raise PublicationError("Plano ja existe ou destino inseguro")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _audit_writer(path: Path):
    if (path.exists() or _is_link(path) or not path.parent.is_dir()
            or _is_link(path.parent)):
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
            outbox = _safe_outbox(args.outbox)
            state = ("AGUARDANDO_AUTORIZACAO_PO" if outbox.get("schema") == SCHEMA
                     else "OUTBOX_LEGADA_NAO_PUBLICAVEL")
            print(json.dumps({
                "status": state, "issue": outbox["issue"],
                "execution_id": outbox["execution_id"], "writes": 0,
                "requires_po_approval": True,
            }, ensure_ascii=False, indent=2))
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
