"""Exportador somente-leitura e seguro do GitHub Project #2 (Método C.H.).

Missão CH-ACCESS-01:
- Operação 100% read-only via GitHub CLI (`gh`).
- Consulta itens e campos estruturados, validando totais reais a cada execução.
- Produz snapshot JSON compacto, determinístico e auditável.
- Sanitiza segredos, credenciais, e-mails, dados pessoais, comentários e corpos de issues.
- Persistência local privada com atomicidade estrita (tempfile + fchmod 0600 + fsync + os.replace).
- Bloqueio rigoroso de links simbólicos e destinos não autorizados.
- Comportamento estritamente fail-closed diante de qualquer erro (sem degradação silenciosa).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable

# AUD-03: Importação estrita de ch_sentinela sem substituição por validadores degradados
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
except ImportError as exc:
    raise ImportError(
        "Dependência obrigatória 'ch_sentinela' ausente ou inacessível. "
        "O exportador de governança exige 'ch_sentinela' integralmente para garantir "
        "as políticas centrais de segurança e sanitização do Método C.H. sem degradação."
    ) from exc


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

REGEX_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
REGEX_GITHUB_TOKEN = re.compile(r"(?:gh[opusr]_|github_pat_)[A-Za-z0-9_]{20,}")


class ProjectExportError(RuntimeError):
    """Exceção base para falhas no exportador de projeto."""


class ProjectExportIntegrityError(ProjectExportError):
    """Exceção levantada quando há violação de integridade nos dados do Project."""


def sanitizar_texto_completo(texto: str) -> str:
    """Sanitiza segredos conhecidos e remove endereços de e-mail de qualquer string.

    Aplica as políticas centrais da Sentinela e mascara dados pessoais.
    """
    if not texto or not isinstance(texto, str):
        return ""
    limpo = sanitizar_texto_segredos(texto)
    limpo = REGEX_GITHUB_TOKEN.sub("[CREDENCIAL_OCULTADA]", limpo)
    limpo = REGEX_EMAIL.sub("[DADO_PESSOAL_OCULTADO]", limpo)
    return limpo.strip()


def extrair_valor_campo(item: dict[str, Any], nome_campo: str) -> str | None:
    """Obtém o valor de um campo de forma case-insensitive e sanitizada, rejeitando duplicidades.

    AUD-02: Garante que todo retorno de extração seja imediatamente sanitizado.
    """
    alvo = nome_campo.casefold()
    correspondencias = [
        val for key, val in item.items()
        if isinstance(key, str) and key.casefold() == alvo
    ]
    if len(correspondencias) > 1:
        raise ProjectExportIntegrityError(
            f"Campo duplicado detectado no item do Project: '{sanitizar_texto_completo(nome_campo)}'."
        )
    if not correspondencias or correspondencias[0] is None:
        return None

    valor = correspondencias[0]
    texto_extraido: str | None = None
    if isinstance(valor, dict) and "name" in valor:
        texto_extraido = str(valor["name"]).strip() or None
    elif isinstance(valor, str):
        texto_extraido = valor.strip() or None
    else:
        texto_extraido = str(valor).strip() or None

    if texto_extraido is None:
        return None

    # AUD-02: Sanitização imediata do valor bruto
    return sanitizar_texto_completo(texto_extraido) or None


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
        tipo = sanitizar_texto_completo(str(f.get("type", "")))
        campo_id = sanitizar_texto_completo(str(f.get("id", "")))

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
                        "id": sanitizar_texto_completo(str(opt.get("id", ""))),
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

        card_id_raw = item.get("id")
        if not card_id_raw or not isinstance(card_id_raw, str):
            raise ProjectExportIntegrityError("Item do Project com ID ausente ou inválido.")

        card_id = sanitizar_texto_completo(card_id_raw)

        if card_id in card_ids_vistos:
            raise ProjectExportIntegrityError(
                f"Card ID duplicado detectado no Project: '{card_id}'."
            )
        card_ids_vistos.add(card_id)

        content = item.get("content")
        if not isinstance(content, dict):
            content = {}

        content_type = sanitizar_texto_completo(str(content.get("type") or "DraftIssue"))
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

        # AUD-02: Extração de governança com sanitização estrita e detecção segura de anomalias
        def extrair_governanca(nome_campo: str) -> str:
            val = extrair_valor_campo(item, nome_campo)
            if val is None or val == "":
                return "NÃO_OBSERVADO"

            val_sanitizado = sanitizar_texto_completo(val)

            # Validação contra opções conhecidas
            chave = nome_campo.casefold()
            opcoes_validas = opcoes_lookup.get(chave) or set(VALORES_GOVERNANCA_PADRAO.get(nome_campo, []))
            if opcoes_validas and val_sanitizado not in opcoes_validas:
                # Opção desconhecida sanitizada e sinalizada como anomalia
                # Nunca serializa dado cru e nunca declara aprovação humana
                anomalias.append({
                    "card_id": card_id,
                    "issue_number": issue_number,
                    "field": sanitizar_texto_completo(nome_campo),
                    "value": val_sanitizado,
                    "error": "OPCAO_DESCONHECIDA",
                })
            return val_sanitizado

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
    """Salva o snapshot em disco com garantia de atomicidade e permissões estritas (0600).

    Medidas de segurança e contenção (AUD-01):
    1. Bloqueio incondicional de links simbólicos no destino ou no diretório pai (fail-closed).
    2. Gravação atômica em arquivo temporário privado exclusivo (0600) no mesmo diretório pai.
    3. fsync obrigatório antes da substituição atômica via os.replace.
    4. Garantia estrita de que o arquivo resultante terá permissão 0600 (-rw-------),
       mesmo que o arquivo preexistente possuísse permissões permissivas (ex.: 0644).
    5. Preservação do arquivo de destino original caso ocorra falha de escrita ou I/O.
    """
    caminho = Path(output_path)

    # 1. Bloqueio estrito de links simbólicos (fail-closed, sem seguir links)
    if caminho.is_symlink() or os.path.islink(str(caminho)):
        raise ProjectExportError(
            f"Caminho de destino é um link simbólico proibido: '{output_path}'. Operação abortada."
        )

    diretorio_pai = caminho.parent
    if diretorio_pai.is_symlink() or os.path.islink(str(diretorio_pai)):
        raise ProjectExportError(
            f"Diretório pai é um link simbólico proibido: '{diretorio_pai}'. Operação abortada."
        )

    diretorio_pai.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(diretorio_pai, 0o700)
    except OSError as exc:
        raise ProjectExportError(
            f"Falha ao assegurar permissões 0700 no diretório pai '{diretorio_pai}': {exc}"
        ) from exc

    conteudo = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"

    # 2. Criação do arquivo temporário exclusivo no mesmo diretório
    try:
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            prefix=".tmp_snapshot_",
            suffix=".json",
            dir=str(diretorio_pai),
        )
    except OSError as exc:
        raise ProjectExportError(
            f"Falha ao criar arquivo temporário seguro em '{diretorio_pai}': {exc}"
        ) from exc

    tmp_path = Path(tmp_path_str)

    try:
        # Garante fchmod 0600 no descritor de arquivo aberto antes de escrever dados
        try:
            os.fchmod(tmp_fd, 0o600)
        except OSError as exc:
            raise ProjectExportError(
                f"Falha ao aplicar fchmod(0600) no arquivo temporário: {exc}"
            ) from exc

        with open(tmp_fd, "w", encoding="utf-8", closefd=False) as f:
            f.write(conteudo)
            f.flush()
        os.fsync(tmp_fd)
    except Exception as exc:
        try:
            os.close(tmp_fd)
        except OSError:
            pass
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise ProjectExportError(
            f"Falha durante gravação/sincronização do snapshot temporário: {exc}"
        ) from exc
    else:
        try:
            os.close(tmp_fd)
        except OSError:
            pass

    # 3. Verificação de permissões do temporário antes do replace
    try:
        tmp_perm = stat.S_IMODE(os.stat(tmp_path).st_mode)
        if tmp_perm != 0o600:
            tmp_path.unlink(missing_ok=True)
            raise ProjectExportError(
                f"Permissão do temporário inconsistente: esperado 0600, obtido {oct(tmp_perm)}."
            )

        # Checagem final contra link simbólico concorrente no destino
        if caminho.is_symlink() or os.path.islink(str(caminho)):
            tmp_path.unlink(missing_ok=True)
            raise ProjectExportError(
                f"Link simbólico concorrente detectado no destino: '{caminho}'. Operação abortada."
            )

        # Substituição atômica no mesmo sistema de arquivos
        os.replace(tmp_path, caminho)

        # 4. Aplicação estrita e verificação de 0600 no destino final
        os.chmod(caminho, 0o600)
        final_perm = stat.S_IMODE(os.stat(caminho).st_mode)
        if final_perm != 0o600:
            raise ProjectExportError(
                f"Permissão final do snapshot divergente: esperado 0600, obtido {oct(final_perm)}."
            )
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return caminho.resolve()
