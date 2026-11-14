"""Ponte de evidências POC-03 para o CHDevFlow; nunca inicia agentes.

Este módulo integra o dossiê AGY→testes→Codex ao supervisor de despacho
sem transformar o DryRunDispatcher W2-B em executor real. O gate de execução
de agentes CLI permanece reservado à Issue #69.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "chdevflow-poc03/v1"
MAX_FILE_BYTES = 1_000_000
ARTIFACTS = (
    "execucao.json", "resposta_agy.md", "auditoria_codex.md",
    "alteracoes.patch", "logs_testes.txt", "RELATORIO_COMPLETO_CH1.md",
)
REQUIRED_STAGES = ("escopo", "ast", "testes_agy", "aceite_independente")


@dataclass(frozen=True)
class AgentCLIInterface:
    """Contrato declarativo: os comandos são documentados, NÃO invocados."""

    agent: str
    purpose: str
    read_only: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


INTERFACES = (
    AgentCLIInterface("agy", "Implementação em laboratório isolado", False),
    AgentCLIInterface("codex", "Auditoria read-only de diff e testes", True),
)


@dataclass(frozen=True)
class EvidenceInspection:
    run_id: str
    state: str
    checks: dict[str, str]
    findings: tuple[str, ...]
    hashes: dict[str, str]
    interfaces: tuple[str, ...] = ("agy", "codex")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = list(self.findings)
        return data


def _read(root: Path, name: str) -> tuple[str, bytes]:
    """Lê um artefato com limite e proteção básica contra symlinks."""
    if name not in ARTIFACTS:
        raise ValueError("Artefato não permitido")
    p = root / name
    if p.is_symlink() or not p.is_file():
        raise ValueError("Artefato ausente ou symlink")
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError("Artefato fora do diretório")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Artefato excede limite de tamanho")
    raw = p.read_bytes()
    return raw.decode("utf-8-sig"), raw


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_test_block(logs: str, heading: str) -> bool:
    found = re.search(
        rf"(?ms)^=== {re.escape(heading)} ===\s*(.*?)(?=^=== |\Z)", logs
    )
    if not found:
        return False
    block = found.group(1)
    return bool(
        re.search(r"(?m)^Ran [1-9][0-9]* tests? in [^\n]+$", block)
        and re.search(r"(?m)^OK\s*$", block)
        and not re.search(r"(?im)^(FAILED|ERROR|FAIL):", block)
    )


def inspect_lab_dossier(directory: Path) -> EvidenceInspection:
    """Validação offline e fail-closed da evidência local da POC-03.

    Não autentica o GitHub, a identidade dos agentes, nem concede autorização.
    A integridade é interna ao conjunto de arquivos enviado pelo operador.
    """
    root = directory.expanduser()
    findings: list[str] = []
    checks: dict[str, str] = {}
    hashes: dict[str, str] = {}
    content: dict[str, str] = {}
    run_id = "NAO_VERIFICADO"

    if root.is_symlink() or not root.is_dir():
        return EvidenceInspection(run_id, "BLOQUEADO", {}, ("Pasta ausente ou symlink",), {})
    try:
        for name in ARTIFACTS:
            txt, raw = _read(root, name)
            content[name] = txt
            hashes[name] = hashlib.sha256(raw).hexdigest()
        data = json.loads(content["execucao.json"])
        if not isinstance(data, dict):
            raise ValueError("JSON de execução inválido")
        run_id = str(data.get("run_id", "NAO_VERIFICADO"))[:128]
        if data.get("schema") != SCHEMA or data.get("simulate") is not False:
            findings.append("Schema inválido ou origem simulada")
        if data.get("erros") or data.get("escopo_extra"):
            findings.append("Execução registra erros ou arquivos fora do escopo")
        steps = data.get("etapas")
        if not isinstance(steps, dict):
            raise ValueError("Etapas ausentes")
        for key in REQUIRED_STAGES:
            ok = isinstance(steps.get(key), dict) and steps[key].get("status") == "PASS"
            checks[key] = "PASS" if ok else "BLOQUEADO"
            if not ok:
                findings.append(f"Etapa {key} não passou")
        codex = steps.get("codex") if isinstance(steps.get("codex"), dict) else {}
        codex_ok = (
            codex.get("status") == "SUCESSO" and codex.get("ok") is True
            and codex.get("exit_code") == 0
            and data.get("veredito_codex") == "APROVAR_LAB"
            and bool(re.search(r"(?i)VEREDITO\s*:\s*\**APROVAR_LAB\b",
                               content["auditoria_codex.md"]))
        )
        checks["codex"] = "PASS" if codex_ok else "BLOQUEADO"
        if not codex_ok:
            findings.append("Codex não aprovou ou não há parecer comprovável")
        for key in ("testes_agy", "aceite_independente"):
            meta = steps.get(key) if isinstance(steps.get(key), dict) else {}
            verified = meta.get("ok") is True and meta.get("exit_code") == 0
            verified &= _assert_test_block(content["logs_testes.txt"], key)
            checks[f"log_{key}"] = "PASS" if verified else "BLOQUEADO"
            if not verified:
                findings.append(f"Logs não comprovam sucesso: {key}")
        if not content["alteracoes.patch"].strip() or not content["resposta_agy.md"].strip():
            findings.append("Código ou resposta AGY ausente")
        # Hashes são publicados pelo gerador ANTES de adicionar a quebra de linha.
        for name, heading in (
            ("alteracoes.patch", "diff"),
            ("resposta_agy.md", "AGY"),
            ("auditoria_codex.md", "Codex"),
        ):
            claimed = re.search(
                rf"(?m)^- SHA256 {re.escape(heading)}: \`([a-f0-9]{{64}})\`",
                content["RELATORIO_COMPLETO_CH1.md"],
            )
            verified = bool(
                claimed and _digest(content[name].replace("\r\n", "\n").removesuffix("\n"))
                == claimed.group(1)
            )
            checks[f"hash_{heading}"] = "PASS" if verified else "BLOQUEADO"
            if not verified:
                findings.append(f"Digest {heading} inconsistente com dossiê")
        if "recheck_source_run" in data:
            # Não seguir recheck_original_dir do JSON: o caminho é dado não confiável.
            original = root.parent
            try:
                orig_text, _ = _read(original, "execucao.json")
                previous = json.loads(orig_text)
                src = str(data["recheck_source_run"])
                source_ok = (
                    previous.get("run_id") == src
                    and previous.get("simulate") is False
                    and previous.get("etapas", {}).get("agy", {}).get("status") == "SUCESSO"
                    and previous.get("etapas", {}).get("agy", {}).get("exit_code") == 0
                    and previous.get("etapas", {}).get("github", {}).get("status") == "SUCESSO"
                )
            except (ValueError, OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError):
                source_ok = False
            checks["origem_agy"] = "PASS" if source_ok else "BLOQUEADO"
            if not source_ok:
                findings.append("Execução original AGY não reconciliada")
        else:
            agy = steps.get("agy") if isinstance(steps.get("agy"), dict) else {}
            agy_ok = agy.get("status") == "SUCESSO" and agy.get("exit_code") == 0
            checks["origem_agy"] = "PASS" if agy_ok else "BLOQUEADO"
            if not agy_ok:
                findings.append("Etapa AGY real não comprovada")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            json.JSONDecodeError, AttributeError) as exc:
        findings.append(f"Artefatos inválidos ({type(exc).__name__})")
    state = "LAB_CONSISTENTE_AGUARDANDO_CH1" if not findings else "BLOQUEADO"
    return EvidenceInspection(run_id, state, checks, tuple(findings), hashes)


def render_inspection(result: EvidenceInspection) -> str:
    lines = [
        f"CHDevFlow pipeline / inspeção local: {result.run_id}",
        f"ESTADO: {result.state}",
    ]
    lines.extend(f"  {name}: {state}" for name, state in result.checks.items())
    lines.extend(f"  ACHADO: {finding}" for finding in result.findings)
    lines.extend([
        "AVISO: apenas consistência offline dos artefatos.",
        "Nenhuma autorização, agente real, merge, deploy ou agendamento foi acionado.",
    ])
    return "\n".join(lines)
