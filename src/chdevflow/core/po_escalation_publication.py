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

from chdevflow.core.intake import validate_issue, _fields, _get
from chdevflow.core.po_escalation_attestation import (verify_external_attestation, validate_trusted_key)
from chdevflow.core.experimental_pilot import _is_link
from chdevflow.core.po_escalation_provenance import verify_provenance
from chdevflow.core.po_escalation_runtime import verify_loaded_f7_modules, RuntimeIdentityError
from chdevflow.core.po_escalation_origin import verify_v1_producer_origin, ProducerOriginError
from chdevflow.core.po_escalation_reservation import (
    GitReservationStore, NAMESPACE, SCHEMA as RESERVATION_SCHEMA, ReservationError,
)
from chdevflow.core.po_escalation import (
    _evidence_text, _read_evidence_bytes,
    EVIDENCE_FILES, EVIDENCE_FILES_TESTS_REPROVADOS,
    OWNER, PROJECT, REPO, SCHEMA, _safe_outbox, _assert_no_link_ancestors,
    _json_unique,
    build_escalation_preview, write_receipt_once,
)

APPROVAL_ISSUE = 63
PLAN_SCHEMA = "CHDEVFLOW-F7-COMMENT-PLAN/1"
RECEIPT_SCHEMA = "CHDEVFLOW-F7-COMMENT-PENDING/1"
MAX_COMMENT_PAGES = 15
MARKER_PREFIX = "<!-- CHDEVFLOW-F7-EXECUTION:"
# A bloqueio definitivo e proposital ate prova externa de custodia,
# serializacao entre hosts e reauditoria. Nao habilitar apenas por env.
REMOTE_PUBLICATION_ENABLED = False
HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
F7_AUDIT_VARIABLE = "CH_F7_AUDITED_COMMIT_SHA"
F7_REPOSITORY_ID = 1424359000
# Pin versionado, intencionalmente nao provisionado. Exige auditoria do SHA
# e decisao explicita PO antes de confiar em qualquer pubkey remota.
F7_TRUST_KEY_FINGERPRINT_PIN = ""
F7_TRUSTED_PRODUCER_SHA_PIN = ""
F7_TRUSTED_V1_WORKFLOW_ID_PIN = 0
F7_TRUST_VARIABLES = (
    "CH_F7_TRUSTED_RUNNER_PUBKEY",
    "CH_F7_TRUSTED_RUNNER_SHA",
    "CH_F7_REVOKED_RUNNER_FINGERPRINTS",
    "CH_F7_PRODUCER_WORKFLOW_ID",
    "CH_F7_V1_PRODUCER_WORKFLOW_ID",
)


class PublicationError(ValueError):
    """Bloqueio seguro antes de escrever."""


class PublicationPending(RuntimeError):
    """Escrita pode ter ocorrido; nao repetir sem reconciliacao LIVE."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _read_local_json(path: Path, *, cap: int = 100000) -> Any:
    """Leitura estrita de plano/recibo, sem JSON excessivo ou chaves duplicadas."""
    _assert_no_link_ancestors(path)
    if not path.is_file() or path.stat().st_size > cap:
        raise PublicationError("JSON local ausente ou excessivo")
    return _json_unique(_evidence_text(_read_evidence_bytes(path, cap=cap)))


def _gh_json(*args: str, expected_type: type = dict) -> Any:
    """Comunicacao GH por bytes UTF-8, sem locale cp1252 e sem expor stderr."""
    if args and args[0] == "api":
        args = ("api", "--hostname", "github.com", *args[1:])
    try:
        done = subprocess.run(
            ["gh", *args], capture_output=True, stdin=subprocess.DEVNULL,
            check=False, timeout=35)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError("GitHub CLI indisponivel; sem escrita") from exc
    if done.returncode:
        raise PublicationError("Consulta GitHub negada/indisponivel; sem escrita")
    if not isinstance(done.stdout, bytes) or len(done.stdout) > 4_000_000:
        raise PublicationError("Resposta GitHub ausente ou excessiva")
    try:
        parsed = _json_unique(done.stdout.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, AttributeError) as exc:
        raise PublicationError("GitHub CLI retornou JSON/UTF-8 invalido") from exc
    if not isinstance(parsed, expected_type):
        raise PublicationError("GitHub CLI retornou formato inesperado")
    return parsed


def _gh_archive(endpoint: str) -> bytes:
    """Bytes do artefato via GitHub API autenticada, com limite de tamanho."""
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", endpoint],
            capture_output=True, stdin=subprocess.DEVNULL,
            check=False, timeout=35,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError("ZIP GitHub V1 indisponivel") from exc
    if (result.returncode != 0 or not isinstance(result.stdout, bytes)
            or not 0 < len(result.stdout) <= 2_000_000):
        raise PublicationError("ZIP GitHub V1 ausente ou excessivo")
    return result.stdout


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


def _live_issue(issue: int) -> dict:
    return _gh_json(
        "issue", "view", str(issue), "-R", REPO,
        "--json", "id,number,title,body,labels,state,url")


def _reconciliation_context(issue: int, _approval_comment: int) -> dict:
    # A consulta de um efeito existente independe de a aprovacao ainda existir.
    return {"who": _gh_json("api", "user"), "issue": _live_issue(issue),
            "comments": _issue_comments(issue)}


def _reservation_store() -> GitReservationStore:
    return GitReservationStore(f"https://github.com/{REPO}.git", github_cli_credentials=True)


def _f7_remote_trust_policy() -> dict:
    """Consulta LIVE uma politica no repositorio GitHub, nunca no env local.

    Este controle so elimina injeção de CH_F7_TRUSTED_RUNNER_* via host.
    Variaveis de repositorio podem ser modificadas pelo administrador Solo;
    politica remota ainda nao equivale a raiz imutavel nem a runner atestado.
    """
    repository = _gh_json("api", f"repos/{REPO}")
    if (not isinstance(repository, dict)
            or repository.get("full_name") != REPO
            or type(repository.get("id")) is not int
            or repository["id"] != F7_REPOSITORY_ID):
        raise PublicationError("Identidade do repositorio da politica F7 diverge")
    values: dict[str, str] = {}
    for name in F7_TRUST_VARIABLES:
        variable = _gh_json("api", f"repos/{REPO}/actions/variables/{name}")
        if (not isinstance(variable, dict) or variable.get("name") != name
                or not isinstance(variable.get("value"), str)
                or not variable["value"].isascii()
                or not 0 < len(variable["value"]) <= 4096):
            raise PublicationError("Variavel de politica F7 LIVE ausente ou invalida")
        values[name] = variable["value"].strip()
    try:
        key = values["CH_F7_TRUSTED_RUNNER_PUBKEY"]
        revocations = values["CH_F7_REVOKED_RUNNER_FINGERPRINTS"]
        fingerprint = validate_trusted_key(key, revocations)
        if (not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}",
                             F7_TRUST_KEY_FINGERPRINT_PIN)
                or fingerprint != F7_TRUST_KEY_FINGERPRINT_PIN):
            raise ValueError("Chave remota nao corresponde ao pin versionado")
        sha = values["CH_F7_TRUSTED_RUNNER_SHA"]
        workflow = values["CH_F7_PRODUCER_WORKFLOW_ID"]
        v1_workflow = values["CH_F7_V1_PRODUCER_WORKFLOW_ID"]
        if (not HEX40.fullmatch(sha)
                or not re.fullmatch(r"[1-9][0-9]{0,19}", workflow)
                or not re.fullmatch(r"[1-9][0-9]{0,19}", v1_workflow)
                or sha != F7_TRUSTED_PRODUCER_SHA_PIN
                or int(v1_workflow) != F7_TRUSTED_V1_WORKFLOW_ID_PIN):
            raise ValueError("SHA/workflow V1 nao corresponde ao pin revisado")
    except (ValueError, KeyError) as exc:
        raise PublicationError("Politica F7 remota invalida ou revogada") from exc
    return {
        "producer_sha": sha, "producer_workflow_id": int(workflow),
        "v1_workflow_id": int(v1_workflow),
        "trusted_key": key, "revocations": revocations,
        "key_fingerprint": fingerprint,
        "source_repo_id": F7_REPOSITORY_ID,
    }


def _verify_attestation(outbox_path: Path, outbox: dict) -> dict:
    policy = _f7_remote_trust_policy()
    proof = verify_external_attestation(
        outbox_path.parent / "f7-attestation.json", outbox,
        trusted_key=policy["trusted_key"],
        trusted_producer_sha=policy["producer_sha"],
        revoked_fingerprints=policy["revocations"],
    )
    try:
        origin = verify_v1_producer_origin(
            proof["producer_run"],
            producer_sha=policy["producer_sha"],
            workflow_id=policy["v1_workflow_id"],
            api=lambda endpoint: _gh_json("api", endpoint),
            archive=_gh_archive,
        )
    except (ProducerOriginError, KeyError) as exc:
        raise PublicationError("Atestacao V1 nao vinculada ao run/artefato GH LIVE") from exc
    return {
        **proof, "v1_origin": origin,
        "trust_policy": {
            "source_repo_id": policy["source_repo_id"],
            "producer_workflow_id": policy["producer_workflow_id"],
            "v1_workflow_id": policy["v1_workflow_id"],
            "producer_sha": policy["producer_sha"],
            "key_fingerprint": policy["key_fingerprint"],
        },
    }


RESERVATION_RULESET_ID = 27322425
PO_GITHUB_ID = 113695320


def _verify_reservation_protection() -> dict:
    """Confirma a politica imutavel e a identidade do mesmo cliente Git/REST."""
    rule = _gh_json("api", f"repos/{REPO}/rulesets/{RESERVATION_RULESET_ID}")
    if (not isinstance(rule, dict) or rule.get("id") != RESERVATION_RULESET_ID
            or rule.get("source_type") != "Repository" or rule.get("source") != REPO
            or rule.get("target") != "tag" or rule.get("enforcement") != "active"
            or rule.get("bypass_actors") != [] or rule.get("current_user_can_bypass") != "never"
            or rule.get("conditions") != {
                "ref_name": {"include": [NAMESPACE + "*"], "exclude": []}}
            or not isinstance(rule.get("rules"), list)
            or {item.get("type") for item in rule["rules"] if isinstance(item, dict)}
            != {"update", "deletion"}):
        raise PublicationError("Namespace de reservas Git sem regra ativa de imutabilidade")
    who = _gh_json("api", "user")
    repo = _gh_json("api", f"repos/{REPO}")
    perms = repo.get("permissions")
    if (who.get("id") != PO_GITHUB_ID or who.get("login") != OWNER
            or repo.get("full_name") != REPO
            or not isinstance(perms, dict) or perms.get("push") is not True):
        raise PublicationError("Identidade/permissao Git LIVE para reserva nao comprovada")
    return {"ruleset_id": RESERVATION_RULESET_ID, "actor_id": PO_GITHUB_ID,
            "namespace": NAMESPACE, "can_bypass": False}



def _local_f7_checkout_sha() -> str:
    """Identifica o checkout que efetivamente executa o publicador F7.

    Nunca confia em SHA fornecido por outbox ou argumento CLI. O checkout deve
    ser o HEAD auditado, sem alteracoes rastreadas ou arquivos nao rastreados.
    """
    root = Path(__file__).resolve().parents[3]
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=False)
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError("Commit F7 local nao verificavel; sem escrita") from exc
    if (head.returncode != 0 or status.returncode != 0 or status.stdout
            or not isinstance(head.stdout, bytes)):
        raise PublicationError("Worktree F7 suja ou Git indisponivel; sem escrita")
    try:
        sha = head.stdout.decode("ascii").strip()
    except UnicodeError as exc:
        raise PublicationError("SHA Git F7 invalido") from exc
    if not HEX40.fullmatch(sha):
        raise PublicationError("SHA Git F7 invalido")
    return sha


def _f7_audit_context() -> dict:
    """Consulta o pin cadastrado pelo PO na API LIVE, nao na outbox local."""
    variable = _gh_json("api", f"repos/{REPO}/actions/variables/{F7_AUDIT_VARIABLE}")
    if not isinstance(variable, dict) or variable.get("name") != F7_AUDIT_VARIABLE:
        raise PublicationError("Politica externa de commit F7 auditado ausente")
    sha = variable.get("value")
    if not isinstance(sha, str) or not HEX40.fullmatch(sha):
        raise PublicationError("Pin do commit F7 auditado ausente ou invalido")
    local = _local_f7_checkout_sha()
    if local != sha:
        raise PublicationError("Checkout F7 nao corresponde ao commit auditado")
    try:
        runtime_digest = verify_loaded_f7_modules(
            Path(__file__).resolve().parents[3], sha)
    except RuntimeIdentityError as exc:
        raise PublicationError("Codigo carregado F7 diverge do commit auditado") from exc
    return {
        "policy_sha": sha,
        "local_sha": local,
        "git_commit": _gh_json("api", f"repos/{REPO}/git/commits/{sha}"),
        "runtime_digest": runtime_digest,
    }


def _validated_f7_audited_commit(context: dict) -> tuple[str, str]:
    """Exige o MESMO SHA no pin do PO, no checkout e no objeto Git remoto."""
    audited = context.get("f7_commit")
    if not isinstance(audited, dict):
        raise PublicationError("Evidencia do commit F7 auditado ausente")
    pinned, local, remote = (
        audited.get("policy_sha"), audited.get("local_sha"), audited.get("git_commit"))
    if (not isinstance(pinned, str) or not HEX40.fullmatch(pinned)
            or local != pinned or not isinstance(remote, dict)
            or remote.get("sha") != pinned):
        raise PublicationError("SHA do commit F7 auditado divergente ou ausente")
    tree = remote.get("tree")
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str) or not HEX40.fullmatch(tree_sha):
        raise PublicationError("Arvore do commit F7 auditado nao verificavel")
    runtime_digest = audited.get("runtime_digest")
    if not isinstance(runtime_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", runtime_digest):
        raise PublicationError("Comprovante de codigo executado F7 ausente")
    return pinned, tree_sha, runtime_digest


def _live_context(issue: int, approval_comment: int) -> dict:
    if type(issue) is not int or issue < 1 or type(approval_comment) is not int or approval_comment < 1:
        raise PublicationError("Identificadores de consulta invalidos")
    who = _gh_json("api", "user")
    if (who.get("login") != OWNER or type(who.get("id")) is not int
            or who["id"] != PO_GITHUB_ID):
        raise PublicationError("Sessao gh nao pertence ao PO responsavel")
    repository = _gh_json("api", f"repos/{REPO}")
    perms = repository.get("permissions")
    if not isinstance(perms, dict) or not any(
        perms.get(k) is True for k in ("push", "maintain", "admin")
    ):
        raise PublicationError("Permissao LIVE de escrita na Issue nao comprovada")
    target = _live_issue(issue)
    base_commit = _gh_json("api", f"repos/{REPO}/git/commits/{_issue_baseline_sha(target)}")
    f7_commit = _f7_audit_context()
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
    # Revogacoes podem ser feitas tanto na Issue de origem como na Issue
    # de governanca. Somar ambos os historicos para nao ignorar retirada.
    approval_history = (comments if approval_thread_number == issue
                        else [*_issue_comments(approval_thread_number), *comments])
    return {
        "who": who, "repository": repository, "issue": target, "base_commit": base_commit,
        "f7_commit": f7_commit, "project": project, "approval": approval,
        "comments": comments, "approval_history": approval_history,
    }


def _expected_comment(outbox: dict, approval_id: int, f7_sha: str) -> str:
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
        f"Autorizacao especifica: comentario #{approval_id}\n"
        f"SHA Git F7 auditado/autorizado: {f7_sha}\n\n"
        "Evidencias locais permanecem sob custodia do PO. "
        "Esta publicacao nao autoriza admissao no Project #2, "
        "merge, deploy, execucao de agentes nem alteracao de campos.\n\n"
        + marker
    )


def _approval_fingerprint(proof: dict, outbox: dict,
                          history: list[dict], f7_sha: str) -> dict:
    if not isinstance(proof, dict):
        raise PublicationError("Comentario PO invalido")
    approval_id = proof.get("id")
    if type(approval_id) is not int or approval_id < 1:
        raise PublicationError("ID de aprovacao invalido")
    if (not isinstance(proof.get("user"), dict)
            or proof["user"].get("login") != OWNER
            or type(proof["user"].get("id")) is not int
            or proof["user"]["id"] != PO_GITHUB_ID):
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
        f"F7_AUDITED_SHA={f7_sha} "
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
            or type(matching[0].get("user", {}).get("id")) is not int
            or matching[0]["user"]["id"] != PO_GITHUB_ID
            or matching[0].get("updated_at") != proof.get("updated_at")):
        raise PublicationError("Aprovacao nao confirmada no historico LIVE")
    revoke_prefix = (
        f"CH-GOV-01 F7 REVOGAR PROJECT#{PROJECT} ISSUE#{outbox['issue']} "
        f"EXECUTION#{outbox['execution_id']}"
    )
    for comment in history:
        # Revogacao editada em comentario anterior tambem bloqueia.
        # Uma nova autorizacao para esta mesma execucao nao a reabilita.
        if comment["user"].get("login") == OWNER:
            if (type(comment["user"].get("id")) is not int
                    or comment["user"]["id"] != PO_GITHUB_ID):
                raise PublicationError("Identidade numerica PO divergente no historico")
            if (isinstance(comment.get("body"), str)
                    and any(line.strip().startswith(revoke_prefix)
                            for line in comment["body"].splitlines())):
                raise PublicationError("Aprovacao do PO revogada em comentario posterior")
    return {
        "id": approval_id, "updated_at": proof.get("updated_at"),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "issue_url": proof["issue_url"], "login": OWNER, "user_id": PO_GITHUB_ID,
        "f7_audited_sha": f7_sha,
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
            "author": author.get("login"), "author_id": author.get("id"),
            "updated_at": comment.get("updated_at"),
        })
    return sorted(normalized, key=lambda c: c["id"])


def _eligible_outbox(path: Path) -> dict:
    outbox = _safe_outbox(path)
    allowed = {
        "CODEX_REPROVOU": EVIDENCE_FILES,
        "TESTES_REPROVADOS": EVIDENCE_FILES_TESTS_REPROVADOS,
    }
    # Diferenciar o preview legado da V1 antes das validacoes de publicacao.
    # Nenhuma outbox sem schema V1 pode alcancar proveniencia ou chamadas LIVE.
    if outbox.get("schema") != SCHEMA:
        raise PublicationError("Outbox legada nao publicavel: somente preview F7")
    status = outbox.get("third_attempt_status")
    if (not isinstance(outbox.get("code_sha256"), str)
            or status not in allowed
            or outbox.get("evidence_files") != list(allowed[status])):
        raise PublicationError("Outbox sem causa da terceira reprovacao: somente preview F7")
    # No modo publicacao, a V1 precisa comprovar toda a linha de producao.
    # Preview legado continua permitido em po_escalation.py.
    verify_provenance(path.parent, outbox, require_isolation=True)
    return outbox


def _issue_baseline_sha(issue: dict) -> str:
    body = issue.get("body")
    if not isinstance(body, str):
        raise PublicationError("Baseline Git da Issue LIVE ausente")
    baseline = _get(body, _fields(body), ("Baseline Git (branch e SHA)", "Base SHA"))
    hashes = re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])",
                        baseline)
    if len(hashes) != 1:
        raise PublicationError("Baseline Git da Issue LIVE deve ter um SHA completo")
    return hashes[0].lower()


def _validate_issue_baseline(issue: dict, expected_sha: str, commit: Any) -> str:
    """Vincula a Issue e o manifesto ao objeto Git consultado no repositorio."""
    if _issue_baseline_sha(issue) != expected_sha:
        raise PublicationError("Baseline Git da Issue LIVE diverge do manifesto")
    if not isinstance(commit, dict) or commit.get("sha") != expected_sha:
        raise PublicationError("Objeto do commit base Git ausente ou divergente")
    tree = commit.get("tree")
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        raise PublicationError("Objeto da arvore base Git ausente ou invalido")
    return tree_sha


def build_publication_plan(outbox: dict, context: dict) -> dict:
    """Plano puro: bloqueia Intake invalido, duplicidade e autorizacao implicita."""
    if not isinstance(context, dict):
        raise PublicationError("Contexto LIVE ausente")
    if (context.get("who", {}).get("login") != OWNER
            or type(context.get("who", {}).get("id")) is not int
            or context["who"]["id"] != PO_GITHUB_ID
            or not isinstance(context.get("repository", {}).get("permissions"), dict)
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
    base_tree = _validate_issue_baseline(
        issue, outbox["provenance"]["base_sha"], context.get("base_commit"))
    f7_sha, f7_tree, f7_runtime = _validated_f7_audited_commit(context)
    preview = build_escalation_preview(
        outbox, context.get("project"), intake_issue=issue)
    approval = _approval_fingerprint(
        context.get("approval"), outbox, context.get("approval_history"), f7_sha)
    comment_text = _expected_comment(outbox, approval["id"], f7_sha)
    marker = MARKER_PREFIX + outbox["execution_id"] + " -->"
    normalized = _comment_snapshot(context.get("comments"))
    matches = [c for c in context["comments"] if marker in c["body"]]
    if len(matches) > 1:
        raise PublicationError("Colisao de comentarios de mesma execucao")
    found_id = None
    if matches:
        only = matches[0]
        if (only.get("body") != comment_text
                or not isinstance(only.get("user"), dict)
                or only["user"].get("login") != OWNER
                or type(only["user"].get("id")) is not int
                or only["user"]["id"] != PO_GITHUB_ID):
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
        "f7_audited_commit": _digest({"sha": f7_sha, "tree": f7_tree,
                                       "runtime": f7_runtime}),
        "identity": _digest({
            "who": context["who"].get("login"), "user_id": context["who"].get("id"),
            "permissions": context["repository"].get("permissions"),
        }),
    }
    data = {
        "schema": PLAN_SCHEMA, "repo": REPO, "project": PROJECT,
        "issue": outbox["issue"], "execution_id": outbox["execution_id"],
        "mission_id": outbox["mission_id"], "code_sha256": outbox["code_sha256"],
        "mission_digest": outbox["provenance"]["mission_digest"],
        "base_sha": outbox["provenance"]["base_sha"],
        "base_tree": base_tree,
        "f7_audited_sha": f7_sha, "f7_audited_tree": f7_tree,
        "f7_runtime_digest": f7_runtime,
        "approval_comment": approval["id"],
        "project_state": preview["state"],
        "action": "ALREADY_PUBLISHED" if found_id else "POST_COMMENT",
        "published_comment_id": found_id,
        "body": comment_text, "snapshot": snapshot,
        "reservation_protocol": RESERVATION_SCHEMA,
        "remote_project_writes": 0,
    }
    return {**data, "digest": _digest(data)}


def _post_comment(issue: int, body: str) -> dict:
    """Nenhum POST real ate reauditoria de autenticidade e serializacao."""
    if not REMOTE_PUBLICATION_ENABLED:
        raise PublicationError("POST F7 desativado: custodia e executor unico pendentes")
    posted = _gh_json(
        "api", "-X", "POST", f"repos/{REPO}/issues/{issue}/comments",
        "-f", "body=" + body)
    if (not isinstance(posted, dict)
            or type(posted.get("id")) is not int
            or not isinstance(posted.get("user"), dict)
            or posted["user"].get("login") != OWNER
            or type(posted["user"].get("id")) is not int
            or posted["user"]["id"] != PO_GITHUB_ID):
        # O POST pode ter ocorrido mesmo com resposta inesperada.
        # O chamador mantem PENDENTE_PUBLICACAO, nunca retry automatico.
        raise PublicationError("Resposta POST sem autoria numerica PO confiavel")
    return posted


def _claim_publication(outbox_path: Path, execution_id: str, digest: str) -> Path:
    """Journal local complementar; a exclusao entre executores fica no Git."""
    if not HEX32.fullmatch(execution_id):
        raise PublicationError("Execution ID do lock invalido")
    lock = outbox_path.parent / ("f7-publicacao-" + execution_id + ".lock")
    _assert_no_link_ancestors(lock)
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
    record = _read_local_json(lock, cap=10000)
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


def reconcile_pending_publication(
    outbox_path: Path, plan: dict, *,
    reader: Callable[[int, int], dict] | None = None,
) -> dict:
    """Reconciliacao LIVE somente leitura; NUNCA libera repeticao de POST."""
    if (not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA
            or plan.get("digest") != _digest({
                k: v for k, v in plan.items() if k != "digest"
            })):
        raise PublicationError("Plano de reconciliacao invalido")
    outbox = _eligible_outbox(outbox_path)
    execution = outbox["execution_id"]
    if (plan.get("execution_id") != execution
            or plan.get("issue") != outbox["issue"]
            or plan.get("code_sha256") != outbox["code_sha256"]
            or plan.get("mission_digest") != outbox["provenance"]["mission_digest"]
            or type(plan.get("approval_comment")) is not int):
        raise PublicationError("Plano de reconciliacao nao pertence a outbox")
    reservation_sha = None
    if plan.get("reservation_protocol") == RESERVATION_SCHEMA:
        reservation_sha = _reservation_store().read(plan)
        journal_status = "RESERVA_REMOTA_CONFIRMADA"
    elif "reservation_protocol" not in plan:
        lock = outbox_path.parent / ("f7-publicacao-" + execution + ".lock")
        _assert_no_link_ancestors(lock)
        if not lock.is_file() or lock.stat().st_size > 10000:
            raise PublicationError("Journal de publicacao ausente/invalido")
        record = _read_local_json(lock, cap=10000)
        if (not isinstance(record, dict)
                or record.get("schema") != RECEIPT_SCHEMA
                or record.get("execution_id") != execution
                or record.get("digest") != plan["digest"]
                or record.get("publication_status") not in (
                    "PENDENTE_PUBLICACAO", "PUBLICADO_VERIFICADO"
                )):
            raise PublicationError("Journal divergente; reconciliacao bloqueada")
        journal_status = record["publication_status"]
    else:
        raise PublicationError("Protocolo de reserva desconhecido")
    if reader is None:
        reader = _reconciliation_context
    context = reader(outbox["issue"], plan["approval_comment"])
    # Readback de publicacao e diferente de NOVA autorizacao. Deve funcionar
    # inclusive apos Issue CLOSED/revogacao, sem consultar permissoes de POST.
    if (not isinstance(context, dict)
            or not isinstance(context.get("who"), dict)
            or context["who"].get("login") != OWNER
            or type(context["who"].get("id")) is not int
            or context["who"]["id"] != PO_GITHUB_ID
            or not isinstance(context.get("issue"), dict)
            or context["issue"].get("number") != outbox["issue"]
            or context["issue"].get("url") !=
                f"https://github.com/{REPO}/issues/{outbox['issue']}"):
        raise PublicationError("Identidade LIVE de reconciliacao invalida")
    comments = context.get("comments")
    _comment_snapshot(comments)
    marker = MARKER_PREFIX + execution + " -->"
    matches = [item for item in comments if marker in item["body"]]
    if len(matches) > 1:
        raise PublicationError("Colisao de publicacoes remotas; bloquear retry")
    if matches:
        item = matches[0]
        if (item.get("body") != plan.get("body")
                or not isinstance(item.get("user"), dict)
                or item["user"].get("login") != OWNER
                or type(item["user"].get("id")) is not int
                or item["user"]["id"] != PO_GITHUB_ID):
            raise PublicationError("Marcador remoto nao autentico; bloquear retry")
        status = "COMENTARIO_REMOTO_ENCONTRADO"
        comment_id = item["id"]
    else:
        status = "COMENTARIO_NAO_OBSERVADO"
        comment_id = None
    receipt = {
        "status": status, "execution_id": execution,
        "comment_id": comment_id, "journal_status": journal_status,
        "remote_writes": 0, "retry_allowed": False,
        "requires_po_decision": True,
    }
    if reservation_sha is not None:
        receipt["reservation_sha"] = reservation_sha
    return receipt


def apply_publication_plan(
    outbox_path: Path, plan: dict, confirmation: str, *,
    reader: Callable[[int, int], dict] | None = None,
    poster: Callable[[int, str], dict] | None = None,
    audit: Callable[[dict], None],
    human_prompt: Callable[[str], str] | None = None,
) -> dict:
    """Uma tentativa, guardada por digest, frase PO e duplo snapshot LIVE."""
    # Gate na API publica, nao apenas CLI/adapter HTTP. Sem ele, qualquer
    # chamador pode injetar um "poster" remoto e contornar _post_comment().
    # A suite offline pode habilitar este gate apenas sob mock isolado.
    if not REMOTE_PUBLICATION_ENABLED:
        raise PublicationError(
            "Aplicacao F7 desativada: custodia externa e executor unico pendentes")
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
            or not isinstance(plan.get("f7_audited_sha"), str)
            or not HEX40.fullmatch(plan["f7_audited_sha"])
            or not isinstance(plan.get("f7_audited_tree"), str)
            or not HEX40.fullmatch(plan["f7_audited_tree"])
            or not isinstance(plan.get("f7_runtime_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", plan["f7_runtime_digest"])
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
    custody = _verify_attestation(outbox_path, outbox)
    if (outbox["mission_id"] == "F7-CUSTODY-PROBE"
            or custody["producer_run"].startswith(("github-actions:probe:", "github-actions:custody:"))):
        raise PublicationError("Atestacao de sonda F7 somente para verificacao")
    _verify_reservation_protection()
    journal = _claim_publication(
        outbox_path, outbox["execution_id"], supplied_digest)
    try:
        reservation_sha = _reservation_store().claim(plan)
    except ReservationError as exc:
        audit({"event": "PENDENTE_PUBLICACAO", "reason": "RESERVA_REMOTA_INCONCLUSIVA"})
        raise PublicationPending(
            "Reserva remota nao confirmada; nenhum POST autorizado") from exc
    # Terceira leitura LIVE imediatamente antes do POST, inclusive revogacao.
    # Se falhar, manter journal pendente para reconciliacao humana.
    try:
        _verify_reservation_protection()
        if current_plan() != plan:
            raise PublicationError("Estado LIVE alterado depois do lock")
    except Exception as exc:
        raise PublicationPending(
            "Revalidacao apos lock inconclusiva; nenhuma repeticao automatica"
        ) from exc
    audit({"event": "ATTEMPT_POST", "execution_id": outbox["execution_id"],
           "f7_audited_sha": plan["f7_audited_sha"],
           "f7_runtime_digest": plan["f7_runtime_digest"],
           "reservation_sha": reservation_sha,
           "producer": custody,
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
                or observed["snapshot"]["approval"] != plan["snapshot"]["approval"]
                or observed["f7_audited_sha"] != plan["f7_audited_sha"]
                or observed["f7_audited_tree"] != plan["f7_audited_tree"]
                or observed["f7_runtime_digest"] != plan["f7_runtime_digest"]
                or observed["snapshot"]["f7_audited_commit"] !=
                   plan["snapshot"]["f7_audited_commit"]):
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
            "reservation_sha": reservation_sha,
            "remote_writes": 1}


def _write_json_once(path: Path, payload: dict) -> None:
    _assert_no_link_ancestors(path)
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
    _assert_no_link_ancestors(path)
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
    parser.add_argument("--outbox", type=Path)
    parser.add_argument("--verify-reservation-policy", action="store_true")
    parser.add_argument("--approval-comment", type=int)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--reconcile-plan", type=Path)
    parser.add_argument("--verify-attestation", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_reservation_policy:
            if any(value is not None and value is not False
                   for name, value in vars(args).items() if name != "verify_reservation_policy"):
                raise PublicationError("Preflight Git aceita somente --verify-reservation-policy")
            policy = _verify_reservation_protection()
            print(json.dumps({"status": "POLITICA_DE_RESERVA_VERIFICADA", **policy}))
            return 0
        if args.outbox is None:
            raise PublicationError("Outbox obrigatoria")
        if args.verify_attestation:
            if (args.apply_plan or args.reconcile_plan or args.plan_file or args.approval_comment
                    or args.confirm or args.audit_file):
                raise PublicationError("Validacao externa aceita somente --verify-attestation")
            outbox = _eligible_outbox(args.outbox)
            proof = _verify_attestation(args.outbox, outbox)
            print(json.dumps({"status": "ATESTACAO_VERIFICADA", **proof}))
            return 0
        if args.reconcile_plan:
            if (args.apply_plan or args.plan_file or args.approval_comment
                    or args.confirm or args.audit_file):
                raise PublicationError("Reconciliacao aceita somente --reconcile-plan")
            _assert_no_link_ancestors(args.reconcile_plan)
            plan = _read_local_json(args.reconcile_plan)
            result = reconcile_pending_publication(args.outbox, plan)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.apply_plan:
            if (args.plan_file or args.approval_comment or
                    not args.confirm or args.audit_file is None):
                raise PublicationError(
                    "Aplicacao exige somente --apply-plan, --confirm e --audit-file")
            # Modo producao intencionalmente desligado antes de criar
            # journal/lock. CLI offline pode ser testada com mocks explicitos.
            if not REMOTE_PUBLICATION_ENABLED:
                raise PublicationError(
                    "POST F7 desativado ate autenticidade externa, "
                    "executor unico e isolamento comprovado")
            _assert_no_link_ancestors(args.apply_plan)
            plan = _read_local_json(args.apply_plan)
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
