"""KSYNC-03.1: evidências verificáveis de trabalho em Issue via timeline GitHub.

Somente leitura. Nunca deduz etapa/homologação. Falha fechada para a etapa.
"""
from __future__ import annotations

import json
import re

REPO = "hallanbrito/CHDevFlow"
MAX_PAGES = 30
MAX_EVENTS = 3000
PR_API = f"https://api.github.com/repos/{REPO}/pulls/"
ISSUE_API = f"https://api.github.com/repos/{REPO}"
SHA = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(ValueError):
    """Consulta incompleta, incorreta ou não confiável."""


def probe(repo: str, issue: int, gh_call) -> dict:
    """Retorna {status: CLEAR|WORK_FOUND, references:[...]}.

    Eventos cross-referenced de PR no mesmo repositório são indícios
    de trabalho, NÃO provam que o PR implementa/encerra toda a Issue.
    """
    if repo != REPO or type(issue) is not int or issue < 1:
        raise EvidenceError("Repositório ou Issue fora de escopo.")
    # Limitar a coleta ANTES de continuar para a próxima página.
    # Cada chamada recebe no máximo 100 eventos; não usar --slurp,
    # que transferiria todas as páginas antes de impor limites.
    seen = set()
    evidence = []
    total = 0
    complete = False
    for page_number in range(1, MAX_PAGES + 1):
        raw = gh_call(
            "api", "-H", "Accept: application/vnd.github+json",
            f"repos/{repo}/issues/{issue}/timeline?per_page=100&page={page_number}"
        )
        try:
            page = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise EvidenceError(f"Timeline página {page_number}: JSON inválido.") from exc
        if not isinstance(page, list) or len(page) > 100:
            raise EvidenceError("Página da timeline com estrutura/tamanho inválido.")
        total += len(page)
        if total > MAX_EVENTS:
            raise EvidenceError("Timeline excede limite seguro de eventos.")
        for event in page:
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                raise EvidenceError("Evento da timeline inválido.")
            kind = event["event"]
            if kind == "cross-referenced":
                source = event.get("source")
                linked = source.get("issue") if isinstance(source, dict) else None
                if not isinstance(linked, dict):
                    continue
                pr = linked.get("pull_request")
                if not isinstance(pr, dict):
                    continue
                num = linked.get("number")
                if (type(num) is not int or num < 1
                        or linked.get("repository_url") != ISSUE_API
                        or pr.get("url") != PR_API + str(num)):
                    # URL de PR externa ou identidade inconsistente:
                    # não considerar a ausência de evidência como CLEAR.
                    raise EvidenceError("Referência de PR externa ou inconsistente.")
                key = ("PR", num)
                if key not in seen:
                    seen.add(key)
                    evidence.append({
                        "kind": "PR", "number": num,
                        "url": f"https://github.com/{repo}/pull/{num}",
                        "merged_at": pr.get("merged_at")
                    })
            elif kind in ("referenced", "committed"):
                commit = event.get("commit_id")
                if commit is None and event.get("commit_url") is None:
                    continue
                if not isinstance(commit, str) or not SHA.fullmatch(commit):
                    raise EvidenceError("Referência de commit com SHA inválido.")
                expected_url = f"https://api.github.com/repos/{repo}/commits/{commit}"
                if event.get("commit_url") != expected_url:
                    # Não construir uma URL deste repositório com SHA alheio.
                    raise EvidenceError("Procedência da referência de commit não confirmada.")
                key = ("COMMIT", commit)
                if key not in seen:
                    seen.add(key)
                    evidence.append({
                        "kind": "COMMIT", "sha": commit,
                        "url": f"https://github.com/{repo}/commit/{commit}"
                    })
        if len(page) < 100:
            complete = True
            break
    if not complete:
        # A página 30 cheia não prova que não existe uma página 31.
        # Em vez de concluir CLEAR/WORK_FOUND com consulta incompleta, bloquear.
        raise EvidenceError("Timeline atingiu limite de páginas sem comprovar fim.")
    return {"status": "WORK_FOUND" if evidence else "CLEAR",
            "references": evidence}


def format_refs(evidence: dict) -> str:
    if evidence.get("status") != "WORK_FOUND":
        return "sem referências verificadas"
    output = []
    for ref in evidence.get("references", [])[:8]:
        if ref["kind"] == "PR":
            output.append(f"PR #{ref['number']}" +
                          (" MERGED" if ref.get("merged_at") else " (estado de merge não confirmado)"))
        else:
            output.append(f"commit {ref['sha'][:10]}")
    return ", ".join(output)
