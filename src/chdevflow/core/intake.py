#!/usr/bin/env python3
"""CH-GOV-01: validação pura da entrada de Issues (somente leitura).

Não conecta ao GitHub, não altera etiquetas/Project e NÃO confere autorização do PO.
Exige metadados explícitos no corpo, tanto para issue forms quanto para a CLI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXECUTOR_LABELS = {
    "ch:po": "Hallan",
    "ch:chatgpt": "ChatGPT",
    "ch:codex": "Codex",
    "ch:agy": "AGY",
}
BAD_VALUES = {"", "_no response_", "não informado", "nao informado", "não_verificado",
              "nao_verificado", "pendente", "todo", "tbd", "n/a"}


def _fields(body: str) -> dict[str, str]:
    """Extrai títulos da Issue Form (não executa markdown nem código)."""
    headers = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", body))
    return {
        m.group(1).strip().casefold(): body[m.end():headers[i + 1].start()
                                         if i + 1 < len(headers) else len(body)].strip()
        for i, m in enumerate(headers)
    }


def _bold_field(body: str, key: str) -> str:
    pattern = r"(?im)^\s*[-*]\s+\*\*" + re.escape(key) + r"\*\*\s*:\s*(.*?)\s*$"
    found = re.search(pattern, body)
    return found.group(1).strip() if found else ""


def _get(body: str, fields: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = fields.get(key.casefold()) or _bold_field(body, key)
        if value:
            return value.strip()
    return ""


def _filled(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and stripped.casefold() not in BAD_VALUES and not stripped.startswith("<!--")


def validate_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Não aceita conteúdo/etiqueta como prova de aprovação executiva."""
    if not isinstance(issue, dict):
        raise ValueError("ISSUE_NOT_OBJECT")
    number = issue.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("INVALID_ISSUE_NUMBER")
    if "pull_request" in issue:
        return _result(number, "OUT_OF_SCOPE", ["PULL_REQUEST"])
    raw_labels = issue.get("labels", [])
    if not isinstance(raw_labels, list):
        raise ValueError("INVALID_LABELS")
    labels: list[str] = []
    for label in raw_labels:
        value = label.get("name") if isinstance(label, dict) else label
        if not isinstance(value, str):
            raise ValueError("INVALID_LABELS")
        labels.append(value)
    if "ch:workflow" not in labels:
        # A ausência da etiqueta é intencional no estágio de triagem.
        return _result(number, "OUT_OF_SCOPE", ["NOT_ENROLLED"])
    body = issue.get("body")
    title = issue.get("title")
    reasons: list[str] = []
    if not isinstance(title, str) or not _filled(title):
        reasons.append("TITLE_MISSING")
    if not isinstance(body, str) or len(body) > 65536:
        body = ""
        reasons.append("BODY_MISSING_OR_OVERSIZE")
    fields = _fields(body)
    executor = _get(body, fields, ("Esteira", "Executor declarado"))
    autonomy = _get(body, fields, ("Nível de autonomia", "Autonomia proposta"))
    objective = _get(body, fields, ("Objetivo e valor", "Objetivo / valor"))
    scope = _get(body, fields, ("Escopo, exclusões e critérios de aceite", "Escopo permitido"))
    baseline = _get(body, fields, ("Baseline Git (branch e SHA)", "Base SHA"))
    evidence = _get(body, fields, ("Verificações e evidências exigidas",))
    criteria = _get(body, fields, ("Escopo, exclusões e critérios de aceite", "Critérios de aceitação"))

    lane_labels = [lab for lab in labels if lab in EXECUTOR_LABELS]
    if len(lane_labels) != 1:
        reasons.append("EXECUTOR_LABEL_MISSING_OR_AMBIGUOUS")
    elif executor != EXECUTOR_LABELS[lane_labels[0]]:
        reasons.append("EXECUTOR_BODY_LABEL_CONFLICT")
    if not _filled(objective):
        reasons.append("OBJECTIVE_MISSING")
    if not re.search(r"\bCH-[0-3]\b", autonomy):
        reasons.append("PROPOSED_AUTONOMY_MISSING")
    if not _filled(scope) or not _filled(criteria):
        reasons.append("SCOPE_OR_ACCEPTANCE_MISSING")
    if (not _filled(baseline) or not re.search(r"\b[0-9a-fA-F]{7,40}\b", baseline)):
        reasons.append("BASELINE_SHA_MISSING")
    if not _filled(evidence):
        reasons.append("EVIDENCE_PLAN_MISSING")
    if "ch:admitted" in labels:
        # Este rótulo não é ativo na F1. Nunca confiar na mera presença dele.
        reasons.append("ADMISSION_LABEL_UNVERIFIED")
    return _result(number, "BLOCKED" if reasons else "CONTENT_VALID", reasons)


def _result(number: int, status: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "issue_number": number,
        "content_status": status,
        "reasons": reasons,
        "project_fields_verified": False,
        "po_authorized": False,
        "execution_allowed": False,
        "project_registration": "NOT_CHECKED",
        "mutation_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-json", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="Saída JSON sem conteúdo da Issue")
    parser.add_argument("--enforce", action="store_true", help="Exit 2 quando o conteúdo estiver bloqueado")
    args = parser.parse_args(argv)
    try:
        if not args.event_json.is_file() or args.event_json.stat().st_size > 1024 * 1024:
            raise ValueError("EVENT_MISSING_OR_OVERSIZE")
        raw = json.loads(args.event_json.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("issue"), dict):
            raise ValueError("INVALID_EVENT_PAYLOAD")
        result = validate_issue(raw["issue"])
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[A-Z_]+", str(exc)) else "INVALID_EVENT"
        print(json.dumps({"content_status": "ERROR", "reason": code}, sort_keys=True))
        return 3
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"CH Intake #{result['issue_number']} — {result['content_status']}; "
              f"motivos: {', '.join(result['reasons']) or '(nenhum)'}; "
              "Project NÃO verificado; execução NÃO autorizada.")
    return 2 if args.enforce and result["content_status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
