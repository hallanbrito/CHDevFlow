#!/usr/bin/env python3
"""Criador conservador de GitHub Projects para o CHDevFlow.

Sem --apply, apenas exibe a prévia (sem rede ou credenciais).
Com --apply, usa GitHub CLI autenticado com o escopo 'project'.
"""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys

TITLE = "C.H. DevFlow - Esteiras"
FIELDS = {
    "Etapa CH": ["BACKLOG", "PRONTA", "EM_EXECUCAO", "EM_REVISAO",
                 "AGUARDANDO_PO", "APROVADA", "PARCIAL", "CORRECOES",
                 "REPROVADA", "INTEGRADA", "HOMOLOGADA"],
    "Esteira": ["Hallan", "ChatGPT", "Codex", "AGY"],
    "Prioridade CH": ["P0", "P1", "P2", "P3"],
    "Risco CH": ["BAIXO", "MEDIO", "ALTO", "CRITICO"],
    "Autonomia CH": ["CH-0", "CH-1", "CH-2", "CH-3"],
    "Decisao PO": ["PENDENTE", "APROVADO", "PARCIAL", "AJUSTES", "REPROVADO"],
}
VIEWS = {
    "00 Geral": "",
    "01 Hallan": "Esteira:Hallan",
    "02 ChatGPT": "Esteira:ChatGPT",
    "03 Codex": "Esteira:Codex",
    "04 AGY": "Esteira:AGY",
    "05 Aguardando PO": "Etapa CH:AGUARDANDO_PO",
}
LABELS = {
    "ch:workflow": ("4078C0", "Fatia W do CHDevFlow"),
    "ch:po": ("B60205", "Decisao do Product Owner"),
    "ch:codex": ("5319E7", "Execucao Codex"),
    "ch:agy": ("0052CC", "Execucao AGY"),
    "ch:chatgpt": ("0E8A16", "Coordenacao ChatGPT"),
    "ch:bloqueada": ("D93F0B", "Bloqueio ou dependencia"),
}


def gh(*args: str) -> dict:
    done = subprocess.run(["gh", *args], capture_output=True, text=True)
    if done.returncode:
        message = done.stderr.strip() or done.stdout.strip()
        raise RuntimeError("Falha no GitHub CLI: " + message)
    if not done.stdout.strip():
        return {}
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Resposta JSON invalida do GitHub CLI") from error


def graphql(query: str, **vars: object) -> dict:
    args = ["api", "graphql", "-f", "query=" + query]
    for key, value in vars.items():
        args.extend(["-F" if isinstance(value, int) else "-f", f"{key}={value}"])
    result = gh(*args)
    if result.get("errors"):
        raise RuntimeError("GraphQL: " + json.dumps(result["errors"]))
    return result.get("data") or {}


def ensure_views(owner: str, number: int) -> None:
    data = graphql("""query($login:String!, $number:Int!){
      user(login:$login){projectV2(number:$number){
        id views(first:100){nodes{id name}}
      }}
    }""", login=owner, number=number)
    project = (data.get("user") or {}).get("projectV2")
    if not project:
        raise RuntimeError("Project inacessivel na API GraphQL.")
    names = {view["name"] for view in project["views"]["nodes"]}
    for name, filter_value in VIEWS.items():
        if name in names:
            print("Preservando view:", name)
            continue
        made = graphql("""mutation($p:ID!, $n:String!){
          createProjectV2View(input:{projectId:$p,name:$n,layout:BOARD}){
            projectV2View{id}
          }
        }""", p=project["id"], n=name)
        view_id = made["createProjectV2View"]["projectV2View"]["id"]
        if filter_value:
            graphql("""mutation($id:ID!, $filter:String!){
              updateProjectV2View(input:{viewId:$id,filter:$filter}){
                projectV2View{id}
              }
            }""", id=view_id, filter=filter_value)
        print("Criada view:", name)


def apply(owner: str, repo: str, title: str) -> None:
    if not shutil.which("gh"):
        raise RuntimeError("Instale o GitHub CLI (gh) antes de --apply.")
    gh("auth", "status", "--json", "hosts")
    projects = gh("project", "list", "--owner", owner, "--format", "json", "--limit", "100")
    matches = [x for x in projects.get("projects", []) if x.get("title") == title]
    if len(matches) > 1:
        raise RuntimeError("Projects duplicados; escolha um manualmente antes.")
    is_new = not matches
    item = (gh("project", "create", "--owner", owner, "--title", title, "--format", "json")
            if is_new else matches[0])
    number = int(item["number"])
    link = str(item.get("url") or f"https://github.com/users/{owner}/projects/{number}")
    print("Project:", link)
    if is_new:
        gh("project", "edit", str(number), "--owner", owner, "--visibility", "PRIVATE")
    try:
        gh("project", "link", str(number), "--owner", owner, "--repo", repo)
    except RuntimeError as error:
        if not any(x in str(error).lower() for x in ("already", "exists", "existe")):
            raise
    fields = gh("project", "field-list", str(number), "--owner", owner,
                "--format", "json", "--limit", "100")
    existing = {f["name"] for f in fields.get("fields", [])}
    for name, options in FIELDS.items():
        if name in existing:
            print("Preservando campo:", name)
            continue
        gh("project", "field-create", str(number), "--owner", owner,
           "--name", name, "--data-type", "SINGLE_SELECT",
           "--single-select-options", ",".join(options), "--format", "json")
        print("Criado campo:", name)
    ensure_views(owner, number)

    labels = gh("label", "list", "--repo", repo, "--json", "name", "--limit", "100")
    existing_labels = {l["name"] for l in labels}
    for name, (color, description) in LABELS.items():
        if name not in existing_labels:
            gh("label", "create", name, "--repo", repo,
               "--color", color, "--description", description)
            print("Criada label:", name)

    issue_url = f"https://github.com/{repo}/issues/2"
    items = gh("project", "item-list", str(number), "--owner", owner,
               "--format", "json", "--limit", "500")
    urls = {str((i.get("content") or {}).get("url") or i.get("url") or "")
            for i in items.get("items", [])}
    if issue_url not in urls:
        gh("project", "item-add", str(number), "--owner", owner,
           "--url", issue_url, "--format", "json")
        print("W1 adicionada ao Project.")
    for field, value in (("Esteira", "ChatGPT"), ("Etapa CH", "EM_REVISAO"),
                         ("Autonomia CH", "CH-2")):
        gh("project", "item-edit", str(number), "--owner", owner,
           "--url", issue_url, "--field", field, "--value", value)
    gh("issue", "edit", "2", "--repo", repo,
       "--add-label", "ch:workflow", "--add-label", "ch:chatgpt")
    print("Configuração finalizada. Confira agrupamento por Etapa CH:", link)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="hallanbrito")
    parser.add_argument("--repo", default="hallanbrito/CHDevFlow")
    parser.add_argument("--title", default=TITLE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.repo.startswith(args.owner + "/"):
        parser.error("O repositório deve pertencer ao owner escolhido.")
    if not args.apply:
        print("PRÉVIA APENAS - sem ações remotas.")
        print("Project:", args.title, "| owner:", args.owner, "| repo:", args.repo)
        print("Visibilidade inicial: PRIVATE (apenas se for novo).")
        for field, values in FIELDS.items():
            print("Campo:", field, "|", ", ".join(values))
        for view, filt in VIEWS.items():
            print("View BOARD:", view, "| filtro:", filt or "(sem filtro)")
        print("Labels:", ", ".join(LABELS))
        print("W1:", f"https://github.com/{args.repo}/issues/2")
        print("Para executar: python scripts/w1_github_project.py --apply")
        return 0
    try:
        apply(args.owner, args.repo, args.title)
        return 0
    except (RuntimeError, ValueError, KeyError) as error:
        print("EXECUÇÃO PARCIAL OU BLOQUEADA:", error, file=sys.stderr)
        print("Não apague o Project. Ajuste e repita --apply de modo idempotente.", file=sys.stderr)
        print("Escopo necessário: gh auth refresh -s project", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
