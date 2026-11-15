"""F7: ponte de escalonamento CCC-01 -> esteira PO / GitHub Project #2.

APENAS LEITURA/PLANEJAMENTO. Para escrita, o fluxo oficial
scripts/ch_project_assist.py exige aprovacao live do PO, digest e readback.
Nao transforma reprovação de IA em autorizacao de escrita remota.
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

from chdevflow.core.experimental_pilot import _is_link

OWNER = "hallanbrito"
REPO = "hallanbrito/CHDevFlow"
PROJECT = 2
MAX_ITEMS = 500
SCHEMA = "CHDEVFLOW-F7-OUTBOX/1"
EVIDENCE_FILES = (
    "attempt-03/codigo.py",
    "attempt-03/alteracoes.patch",
    "attempt-03/testes.log",
    "attempt-03/auditoria_codex.md",
    "RELATORIO_COMPLETO_CH1.md",
)
EVIDENCE_FILES_TESTS_REPROVADOS = tuple(
    path for path in EVIDENCE_FILES if path != "attempt-03/auditoria_codex.md"
)
_HEX = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MISSION = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")
_ISSUE_URL = re.compile(
    r"^https://github\.com/hallanbrito/CHDevFlow/issues/([1-9][0-9]*)$")


def _safe_file_within(root: Path, relative: str) -> Path:
    """Rejeita symlink/reparse Windows em TODOS os componentes da evidência."""
    target = root / relative
    if not target.is_relative_to(root):
        raise ValueError("Evidencia fora do dossie")
    node = target
    while True:
        if _is_link(node):
            raise ValueError("Link/reparse point no caminho de evidencias")
        if node == root:
            break
        node = node.parent
    if not target.is_file() or target.stat().st_size > 100000:
        raise ValueError("Evidencia ausente ou excessiva")
    return target


def _safe_outbox(path: Path) -> dict:
    if (_is_link(path) or _is_link(path.parent) or not path.is_file()
            or path.stat().st_size > 15000):
        raise ValueError("Outbox local ausente, link ou maior que limite")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Outbox JSON invalido")
    if data.get("status") != "AGUARDANDO_PO":
        raise ValueError("Somente terceira reprovação gera escalonamento")
    if data.get("publication_status") != "PENDENTE_DE_AUTORIZACAO":
        raise ValueError("Outbox ja processado ou estado inconclusivo")
    if data.get("attempts") != 3 or data.get("returns") != 2:
        raise ValueError("Contadores CCC-01 divergentes")
    execution = data.get("execution_id")
    if not isinstance(execution, str) or not _HEX.fullmatch(execution):
        raise ValueError("Execution ID invalido")
    mission = data.get("mission_id") or data.get("mission")
    if not isinstance(mission, str) or not _MISSION.fullmatch(mission):
        raise ValueError("Mission ID invalido")
    issue = data.get("issue")
    if isinstance(issue, str):
        match = _ISSUE_URL.fullmatch(issue)
        issue = int(match.group(1)) if match else None
    if type(issue) is not int or issue < 1:
        raise ValueError("Issue de escalonamento invalida")
    code_sha = None
    evidence_files = []
    if "schema" in data:
        if data["schema"] != SCHEMA:
            raise ValueError("Schema da outbox F7 desconhecido")
        code_sha = data.get("code_sha256")
        if not isinstance(code_sha, str) or not _SHA256.fullmatch(code_sha):
            raise ValueError("SHA256 da implementacao invalido")
        evidence_files = data.get("evidence_files")
        third_attempt_status = data.get("third_attempt_status")
        if third_attempt_status == "TESTES_REPROVADOS":
            expected_files = EVIDENCE_FILES_TESTS_REPROVADOS
        elif third_attempt_status in ("CODEX_REPROVOU", None):
            expected_files = EVIDENCE_FILES
        else:
            raise ValueError("Estado da terceira tentativa invalido")
        if evidence_files != list(expected_files):
            raise ValueError("Evidencias da outbox nao foram sanitizadas")
        for relative in expected_files:
            _safe_file_within(path.parent, relative)
        # Arquivo codigo.py pode usar CRLF no host Windows; read_text()
        # normaliza as quebras para validar o SHA logico do candidato AGY.
        source_text = _safe_file_within(
            path.parent, EVIDENCE_FILES[0]).read_text(encoding="utf-8")
        if hashlib.sha256(source_text.encode("utf-8")).hexdigest() != code_sha:
            raise ValueError("Evidencia AGY nao confere com code_sha256")
    return {"execution_id": execution, "mission_id": mission,
            "issue": issue, "attempts": 3, "returns": 2,
            "status": "AGUARDANDO_PO", "schema": data.get("schema"),
            "code_sha256": code_sha, "evidence_files": evidence_files,
            "third_attempt_status": data.get("third_attempt_status"),
            "provenance": data.get("provenance")}


def _project_snapshot() -> dict:
    """Somente gh project item-list; nenhuma mutacao GitHub."""
    try:
        result = subprocess.run(
            ["gh", "project", "item-list", str(PROJECT), "--owner", OWNER,
             "--format", "json", "-L", str(MAX_ITEMS)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Projeto indisponivel, sem efetuar escrita") from exc
    if result.returncode:
        raise ValueError("Nao foi possivel obter Project LIVE; sem escrita")
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("Resposta Project nao e JSON valido") from exc


def _issue_snapshot(number: int) -> dict:
    """Consulta a Issue real somente em modo leitura; texto UTF-8 estrito."""
    if type(number) is not int or number < 1:
        raise ValueError("Issue de consulta invalida")
    try:
        process = subprocess.run(
            ["gh", "issue", "view", str(number), "-R", REPO,
             "--json", "id,number,title,body,labels,state,url"],
            capture_output=True, stdin=subprocess.DEVNULL,
            timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Intake LIVE indisponivel; sem admissao") from exc
    if process.returncode:
        raise ValueError("Issue LIVE indisponivel; sem admissao")
    try:
        raw = process.stdout.decode("utf-8", errors="strict")
        issue = json.loads(raw)
    except (UnicodeError, ValueError, AttributeError) as exc:
        raise ValueError("Issue LIVE retornou JSON/UTF-8 invalido") from exc
    if not isinstance(issue, dict):
        raise ValueError("Resposta de Issue LIVE invalida")
    return issue


def build_escalation_preview(outbox: dict, project: dict,
                             intake_issue: dict | None = None) -> dict:
    """Valida estado total e detecta duplicidade antes de sugerir admissao."""
    if (not isinstance(project, dict) or
            not isinstance(project.get("items"), list) or
            type(project.get("totalCount")) is not int or
            project["totalCount"] != len(project["items"]) or
            project["totalCount"] > MAX_ITEMS):
        raise ValueError("Snapshot Project incompleto ou truncado")
    issue = outbox["issue"]
    items = []
    found = set()
    for item in project["items"]:
        if not isinstance(item, dict):
            raise ValueError("Cartao malformado")
        content = item.get("content")
        if not isinstance(content, dict) or content.get("type") != "Issue":
            continue
        if content.get("repository") != REPO:
            continue
        number = content.get("number")
        if type(number) is not int or number <= 0 or number in found:
            raise ValueError("Issue duplicada/malformada no Project")
        found.add(number)
        if content.get("url") != f"https://github.com/{REPO}/issues/{number}":
            raise ValueError("URL de Issue divergiu do Project")
        if number == issue:
            if not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("Item existe sem ID valido")
            items.append(item["id"])
    if len(items) > 1:
        raise ValueError("Issue aparece mais de uma vez no Project")
    state = "JA_EXISTE_NO_PROJECT" if items else "EXIGE_ADMISSAO_PO"
    base = {
        "schema": "CHDEVFLOW-F7-ESCALATION-PREVIEW/1",
        "execution_id": outbox["execution_id"],
        "mission_id": outbox["mission_id"],
        "issue": issue,
        "status": "AGUARDANDO_PO",
        "code_sha256": outbox.get("code_sha256"),
        "evidence_files": outbox.get("evidence_files", []),
        "project_owner": OWNER, "project_number": PROJECT,
        "project_item_id": items[0] if items else None,
        "state": state, "writes": 0,
        "next_step": (
            "Preservar cartao e consultar PO, sem alterar campos"
            if items else
            "Solicitar aprovacao PO real; executar o fluxo KSYNC-03 admit com "
            "plano digest e readback, nunca publicar automaticamente"
        )
    }
    if intake_issue is not None and not items:
        if (not isinstance(intake_issue, dict) or
                intake_issue.get("number") != issue or
                intake_issue.get("url") != f"https://github.com/{REPO}/issues/{issue}" or
                intake_issue.get("state") != "OPEN"):
            raise ValueError("Intake Issue LIVE fora do escopo ou identidade divergente")
        # Usa a MESMA regra pura que KSYNC-03 usa em make_admit_plan().
        from chdevflow.core.intake import validate_issue
        diagnosis = validate_issue(intake_issue)
        base["intake_status"] = diagnosis["content_status"]
        base["intake_reasons"] = diagnosis["reasons"]
        if diagnosis["content_status"] != "CONTENT_VALID":
            base["state"] = "EXIGE_TRIAGEM_INTAKE"
            base["next_step"] = (
                "Issue nao elegivel ao KSYNC-03: triagem de escopo/conteudo "
                "e decisao PO necessarias; nao adicionar labels por inferencia "
                "nem admitir automaticamente"
            )
        else:
            base["next_step"] = (
                "Intake elegivel; KSYNC-03 ainda deve verificar historico CLEAR, "
                "aprovacao PO autenticada, plano digest pinado e readback"
            )
    base["digest"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    return base


def preview(outbox_path: Path, *, reader=_project_snapshot,
            issue_reader=None) -> dict:
    outbox = _safe_outbox(outbox_path)
    project = reader()
    plan = build_escalation_preview(outbox, project)
    if plan["state"] == "EXIGE_ADMISSAO_PO" and issue_reader is not None:
        return build_escalation_preview(
            outbox, project, intake_issue=issue_reader(outbox["issue"]))
    return plan


def pending_publication_receipt(outbox_path: Path, *, reason: str) -> dict:
    """Recibo LOCAL de falha GitHub; sem qualquer escrita ou retry remoto."""
    outbox = _safe_outbox(outbox_path)
    return {
        "schema": "CHDEVFLOW-F7-PENDING-RECEIPT/1",
        "execution_id": outbox["execution_id"],
        "mission_id": outbox["mission_id"],
        "issue": outbox["issue"],
        "code_sha256": outbox.get("code_sha256"),
        "publication_status": "PENDENTE_PUBLICACAO",
        "reason": reason,
        "remote_writes": 0,
        "retry_agents": False,
        "requires_live_po_approval": True,
    }


def write_receipt_once(path: Path, payload: dict) -> None:
    """Grava um unico recibo local; nao apaga arquivos existentes."""
    if (path.exists() or _is_link(path) or not path.parent.is_dir() or
            _is_link(path.parent)):
        raise ValueError("Recibo ja existe ou destino invalido")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="F7 - leitura/preview de escalonamento Project #2, SEM escrita")
    parser.add_argument("--outbox", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--receipt", type=Path,
        help="Somente em falha de Project: recibo local novo e exclusivo")
    args = parser.parse_args(argv)
    try:
        plan = preview(args.outbox, issue_reader=_issue_snapshot)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        if args.receipt is not None:
            try:
                write_receipt_once(
                    args.receipt,
                    pending_publication_receipt(
                        args.outbox, reason="PROJECT_INDISPONIVEL_OU_INCONCLUSIVO"))
            except (ValueError, OSError, UnicodeError) as receipt_exc:
                print("F7 RECIBO BLOQUEADO: " + str(receipt_exc)[:200],
                      file=sys.stderr)
        print("F7 BLOQUEADO: " + str(exc)[:400], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
