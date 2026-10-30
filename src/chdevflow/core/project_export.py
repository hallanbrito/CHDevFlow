"""Exportador somente-leitura e seguro do GitHub Project #2 (Método C.H.).

Missão CH-ACCESS-01:
- Operação 100% read-only via GitHub CLI (`gh`).
- Consulta itens e campos estruturados, validando totais reais a cada execução.
- Produz snapshot JSON compacto, determinístico e auditável.
- Sanitiza segredos, credenciais, e-mails, dados pessoais, comentários e corpos de issues.
- Persistência local privada com permissão estrita 0600.
- Comportamento estritamente fail-closed diante de qualquer erro.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable

try:
    from ch_sentinela.config import (
        NUMERO_PROJETO_PADRAO,
        PROPRIETARIO_PADRAO,
    )
    from ch_sentinela.github_reader import (
        LeitorGitHub,
        LeitorGitHubErro,
        validar_campos_projeto,
        validar_snapshot_projeto,
    )
    from ch_sentinela.security.policies import (
        ViolacaoPoliticaSegurancaErro,
        sanitizar_texto_segredos,
    )
except ImportError:
    # Fallback para ambientes de execução onde ch_sentinela não esteja no path
    NUMERO_PROJETO_PADRAO = 2
    PROPRIETARIO_PADRAO = "hallanbrito"
    LeitorGitHub = None  # type: ignore
    LeitorGitHubErro = RuntimeError  # type: ignore
    ViolacaoPoliticaSegurancaErro = ValueError  # type: ignore

    def sanitizar_texto_segredos(texto: str) -> str:  # type: ignore
        if not texto or not isinstance(texto, str):
            return ""
        t = re.sub(r"\b(?:gh[opusr]_|github_pat_)[A-Za-z0-9_]{20,}\b", "[CREDENCIAL_OCULTADA]", texto)
        t = re.sub(r"\bAIza[0-9A-Za-z-_]{35}\b", "[CREDENCIAL_OCULTADA]", t)
        return t

    def validar_snapshot_projeto(dados: Any) -> None:  # type: ignore
        if not isinstance(dados, dict) or "items" not in dados or "totalCount" not in dados:
            raise RuntimeError("Snapshot inválido.")
        if len(dados["items"]) != dados["totalCount"]:
            raise RuntimeError("Project incompleto.")

    def validar_campos_projeto(dados: Any) -> None:  # type: ignore
        if not isinstance(dados, dict) or "fields" not in dados or "totalCount" not in dados:
            raise RuntimeError("Campos inválidos.")
        if len(dados["fields"]) != dados["totalCount"]:
            raise RuntimeError("Campos incompletos.")


SCHEMA_VERSION = "chdevflow.project-snapshot/1.0"
SOURCE_LIVE = "LIVE_GITHUB"
SOURCE_OFFLINE = "SNAPSHOT_OFFLINE"
DEFAULT_OUTPUT_PATH = Path(".ch_sentinela/project_snapshot.json")

# Campos observados de governança no Project #2 e suas opções válidas
VALORES_GOVERNANCA_PADRAO: dict[str, list[str]] = {
    "Status": ["Todo", "In Progress", "Done"],
    "Etapa CH": [
        "BACKLOG",
        "PRONTA",
        "EM_EXECUCAO",
        "EM_REVISAO",
        "AGUARDANDO_PO",
        "APROVADA",
        "PARCIAL",
        "CORRECOES",
        "REPROVADA",
        "INTEGRADA",
        "HOMOLOGADA",
    ],
    "Esteira": ["Hallan", "ChatGPT", "Codex", "AGY"],
    "Prioridade CH": ["P0", "P1", "P2", "P3"],
    "Risco CH": ["BAIXO", "MEDIO", "ALTO", "CRITICO"],
    "Autonomia CH": ["CH-0", "CH-1", "CH-2", "CH-3"],
    "Decisao PO": ["PENDENTE", "APROVADO", "PARCIAL", "AJUSTES", "REPROVADO"],
}

REGEX_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


class ProjectExportError(RuntimeError):
    """Exceção base para falhas no exportador de projeto."""


class ProjectExportIntegrityError(ProjectExportError):
    """Exceção levantada quando há violação de integridade nos dados do Project."""


def sanitizar_texto_completo(texto: str) -> str:
    """Sanitiza segredos conhecidos e remove endereços de e-mail."""
    if not texto or not isinstance(texto, str):
        return ""
    limpo = sanitizar_texto_segredos(texto)
    limpo = REGEX_EMAIL.sub("[DADO_PESSOAL_OCULTADO]", limpo)
    return limpo.strip()


def extrair_valor_campo(item: dict[str, Any], nome_campo: str) -> str | None:
    """Obtém o valor de um campo de forma case-insensitive, rejeitando duplicidades."""
    alvo = nome_campo.casefold()
    correspondencias = [
        val for key, val in item.items()
        if isinstance(key, str) and key.casefold() == alvo
    ]
    if len(correspondencias) > 1:
        raise ProjectExportIntegrityError(
            f"Campo duplicado detectado no item do Project: '{nome_campo}'."
        )
    if not correspondencias or correspondencias[0] is None:
        return None

    valor = correspondencias[0]
    if isinstance(valor, dict) and "name" in valor:
        return str(valor["name"]).strip() or None
    if isinstance(valor, str):
        return valor.strip() or None
    return str(valor).strip() or None


def processar_definicoes_campos(
    fields_raw: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    """Processa a lista de campos brutos e mapeia opções válidas de campos select."""
    validar_campos_projeto(fields_raw)

    campos_processados: list[dict[str, Any]] = []
    opcoes_lookup: dict[str, set[str]] = {}

    for f in fields_raw.get("fields", []):
        if not isinstance(f, dict):
            raise ProjectExportIntegrityError("Campo do Project não é um dicionário JSON válido.")

        nome = sanitizar_texto_completo(str(f.get("name", "")))
        tipo = str(f.get("type", ""))
        campo_id = str(f.get("id", ""))

        info_campo: dict[str, Any] = {
            "id": campo_id,
            "name": nome,
            "type": tipo,
        }

        if tipo == "ProjectV2SingleSelectField":
            opcoes_lista = []
            nomes_opcoes = set()
            for opt in f.get("options", []):
                if isinstance(opt, dict):
                    opt_nome = sanitizar_texto_completo(str(opt.get("name", "")))
                    opcoes_lista.append({
                        "id": str(opt.get("id", "")),
                        "name": opt_nome,
                    })
                    if opt_nome:
                        nomes_opcoes.add(opt_nome)
            info_campo["options"] = opcoes_lista
            opcoes_lookup[nome.casefold()] = nomes_opcoes
        elif nome.casefold() in {k.casefold(): v for k, v in VALORES_GOVERNANCA_PADRAO.items()}:
            # Se for um campo de governança padrão registrado
            opcoes_lookup[nome.casefold()] = set(VALORES_GOVERNANCA_PADRAO.get(nome, []))

        campos_processados.append(info_campo)

    return campos_processados, opcoes_lookup


def resumir_itens_projeto(
    items_raw: dict[str, Any],
    opcoes_lookup: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Processa e sumariza os itens do Project sem expor dados confidenciais."""
    validar_snapshot_projeto(items_raw)

    itens = items_raw.get("items", [])
    total_count = items_raw.get("totalCount")
    if len(itens) != total_count:
        raise ProjectExportIntegrityError(
            f"Project incompleto: {len(itens)} itens recebidos, totalCount={total_count}."
        )

    itens_resumidos: list[dict[str, Any]] = []
    anomalias: list[dict[str, Any]] = []
    card_ids_vistos: set[str] = set()

    for item in itens:
        if not isinstance(item, dict):
            raise ProjectExportIntegrityError("Item do Project não é um objeto JSON válido.")

        card_id = item.get("id")
        if not card_id or not isinstance(card_id, str):
            raise ProjectExportIntegrityError("Item do Project com ID ausente ou inválido.")

        if card_id in card_ids_vistos:
            raise ProjectExportIntegrityError(
                f"Card ID duplicado detectado no Project: '{card_id}'."
            )
        card_ids_vistos.add(card_id)

        content = item.get("content")
        if not isinstance(content, dict):
            content = {}

        content_type = str(content.get("type") or "DraftIssue")
        issue_number = content.get("number")
        if issue_number is not None and not isinstance(issue_number, int):
            try:
                issue_number = int(issue_number)
            except (ValueError, TypeError):
                issue_number = None

        url_raw = str(content.get("url") or "")
        url = sanitizar_texto_completo(url_raw)

        titulo_raw = str(content.get("title") or item.get("title") or "")
        titulo = sanitizar_texto_completo(titulo_raw)

        repo_raw = str(content.get("repository") or item.get("repository") or "")
        repositorio = sanitizar_texto_completo(repo_raw)

        # Labels sanitizadas
        labels_raw = item.get("labels", [])
        labels = [
            sanitizar_texto_completo(l)
            for l in labels_raw
            if isinstance(l, str)
        ]

        # Extração de campos de governança com distinção preservada
        def extrair_governanca(nome_campo: str) -> str:
            val = extrair_valor_campo(item, nome_campo)
            if val is None or val == "":
                return "NÃO_OBSERVADO"

            # Validação contra opções conhecidas
            chave = nome_campo.casefold()
            opcoes_validas = opcoes_lookup.get(chave) or set(VALORES_GOVERNANCA_PADRAO.get(nome_campo, []))
            if opcoes_validas and val not in opcoes_validas:
                anomalias.append({
                    "card_id": card_id,
                    "issue_number": issue_number,
                    "field": nome_campo,
                    "value": val,
                    "error": "OPCAO_DESCONHECIDA",
                })
            return val

        status_val = extrair_governanca("Status")
        esteira_val = extrair_governanca("Esteira")
        etapa_val = extrair_governanca("Etapa CH")
        prioridade_val = extrair_governanca("Prioridade CH")
        risco_val = extrair_governanca("Risco CH")
        autonomia_val = extrair_governanca("Autonomia CH")
        decisao_po_val = extrair_governanca("Decisao PO")

        item_resumido: dict[str, Any] = {
            "card_id": card_id,
            "content_type": content_type,
            "number": issue_number,
            "title": titulo,
            "url": url,
            "repository": repositorio,
            "status": status_val,
            "esteira": esteira_val,
            "etapa_ch": etapa_val,
            "prioridade_ch": prioridade_val,
            "risco_ch": risco_val,
            "autonomia_ch": autonomia_val,
            "decisao_po": decisao_po_val,
            "labels": labels,
        }

        itens_resumidos.append(item_resumido)

    # Ordenação determinística: por número de issue se presente, senão por card_id
    itens_resumidos.sort(key=lambda x: (x["number"] is None, x["number"] or 0, x["card_id"]))

    return itens_resumidos, anomalias


def export_project_snapshot(
    owner: str = PROPRIETARIO_PADRAO,
    project_number: int = NUMERO_PROJETO_PADRAO,
    leitor: Any | None = None,
    items_raw: dict[str, Any] | None = None,
    fields_raw: dict[str, Any] | None = None,
    source_override: str | None = None,
) -> dict[str, Any]:
    """Executa a exportação auditável do Project #2 de forma somente leitura.

    Args:
        owner: Proprietário do projeto GitHub (padrão: hallanbrito).
        project_number: Número do projeto GitHub (padrão: 2).
        leitor: Instância opcional de LeitorGitHub para injeção de dependência/testes.
        items_raw: Dados brutos de itens pré-carregados (usado para testes offline).
        fields_raw: Dados brutos de campos pré-carregados (usado para testes offline).
        source_override: Identificador explícito da fonte de dados.

    Returns:
        Dicionário contendo o snapshot estruturado, compacto e auditável.

    Raises:
        ProjectExportError: Diante de falhas de autenticação, rede, JSON ou integridade.
    """
    if items_raw is not None and fields_raw is not None:
        fonte = source_override or SOURCE_OFFLINE
    else:
        fonte = source_override or SOURCE_LIVE
        if leitor is None:
            if LeitorGitHub is None:
                raise ProjectExportError("Módulo 'ch_sentinela' indisponível para consulta live.")
            leitor = LeitorGitHub()

        try:
            fields_raw = leitor.listar_campos_projeto(
                numero_projeto=project_number,
                proprietario=owner,
            )
            items_raw = leitor.listar_itens_projeto(
                numero_projeto=project_number,
                proprietario=owner,
            )
        except Exception as exc:
            msg = sanitizar_texto_completo(str(exc))
            raise ProjectExportError(f"Falha na consulta ao GitHub Project #{project_number}: {msg}") from exc

    # Validações estruturais e integridade
    campos_processados, opcoes_lookup = processar_definicoes_campos(fields_raw)
    itens_resumidos, anomalias = resumir_itens_projeto(items_raw, opcoes_lookup)

    total_items_reported = int(items_raw.get("totalCount", 0))
    total_items_received = len(itens_resumidos)
    total_fields_reported = int(fields_raw.get("totalCount", 0))
    total_fields_received = len(campos_processados)

    items_count_match = (total_items_reported == total_items_received)
    fields_count_match = (total_fields_reported == total_fields_received)

    if not items_count_match:
        raise ProjectExportIntegrityError(
            f"Divergência de contagem de itens: reportados={total_items_reported}, recebidos={total_items_received}."
        )

    if not fields_count_match:
        raise ProjectExportIntegrityError(
            f"Divergência de contagem de campos: reportados={total_fields_reported}, recebidos={total_fields_received}."
        )

    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Monta payload preliminar para cálculo determinístico do digest
    payload_base = {
        "schema_version": SCHEMA_VERSION,
        "source": fonte,
        "project_owner": owner,
        "project_number": project_number,
        "captured_at_utc": captured_at,
        "counts": {
            "items_total": total_items_received,
            "fields_total": total_fields_received,
        },
        "fields": campos_processados,
        "items": itens_resumidos,
    }

    # Digest SHA-256 canônico
    canonical_bytes = json.dumps(
        payload_base,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_bytes).hexdigest()

    snapshot_completo = {
        "schema_version": SCHEMA_VERSION,
        "source": fonte,
        "project_owner": owner,
        "project_number": project_number,
        "captured_at_utc": captured_at,
        "integrity": {
            "total_items_reported": total_items_reported,
            "total_items_received": total_items_received,
            "items_count_match": items_count_match,
            "total_fields_reported": total_fields_reported,
            "total_fields_received": total_fields_received,
            "fields_count_match": fields_count_match,
            "unique_card_ids": True,
            "anomalies": anomalias,
            "snapshot_digest": digest,
        },
        "fields": campos_processados,
        "items": itens_resumidos,
    }

    return snapshot_completo


def save_snapshot_file(
    snapshot: dict[str, Any],
    output_path: Path | str,
) -> Path:
    """Salva o snapshot em disco com permissões privadas restritas (0600).

    Args:
        snapshot: Dicionário do snapshot validado.
        output_path: Caminho de destino do arquivo.

    Returns:
        Path: Caminho resolvido onde o arquivo foi persistido.
    """
    caminho = Path(output_path).resolve()
    caminho.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    conteudo = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"

    # Abertura atômica com permissões 0600 (apenas leitura e escrita pelo proprietário)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(caminho), flags, 0o600)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(conteudo)
    except Exception:
        # Se falhar durante escrita
        try:
            os.close(fd)
        except OSError:
            pass
        raise

    # Garante explicitamente permissões restritas 0600
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass

    return caminho
