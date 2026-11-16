"""F7: proveniencia local das tres tentativas (sem assinaturas externas).

Hash de TODOS os artefatos obrigatorios; nao prova autoria criptografica se
atacante pode reescrever o dossie completo. Nesse caso, gate externo adicional.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from chdevflow.core.manual_pipeline_runner import Mission
from chdevflow.core.po_escalation import _safe_file_within

SCHEMA = "CHDEVFLOW-F7-PROVENANCE/1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATES = ("CODEX_REPROVOU", "TESTES_REPROVADOS")


def _expected_files(run: dict) -> list[str]:
    rows = run.get("attempts")
    if (run.get("status") != "AGUARDANDO_PO" or
            run.get("returns_used") != 2 or
            not isinstance(rows, list) or len(rows) != 3):
        raise ValueError("Execucao sem tres tentativas e duas devolucoes")
    paths = ["manifesto_missao.json", "execucao.json",
             "RELATORIO_COMPLETO_CH1.md"]
    for i, row in enumerate(rows, 1):
        if (not isinstance(row, dict) or row.get("number") != i or
                row.get("status") not in STATES or
                not isinstance(row.get("sha256"), str) or
                not SHA256.fullmatch(row["sha256"])):
            raise ValueError("Tentativa incompleta ou estado invalido")
        folder = f"attempt-{i:02d}/"
        paths.extend(folder + file for file in (
            "agy.log", "codigo.py", "alteracoes.patch", "testes.log"))
        if row["status"] == "CODEX_REPROVOU":
            paths.extend(folder + file for file in (
                "codex.log", "auditoria_codex.md"))
    return paths


def _read_text(root: Path, relative: str) -> str:
    return _safe_file_within(root, relative).read_text(encoding="utf-8")


def _artifact_hashes(root: Path, paths: list[str]) -> dict[str, str]:
    # Limite para dossie pequeno; cap do leitor bloqueia arquivo excessivo.
    return {relative: hashlib.sha256(
        _safe_file_within(root, relative).read_bytes()).hexdigest()
        for relative in paths}


def _state(root: Path) -> tuple[Mission, dict]:
    mission_data = json.loads(_read_text(root, "manifesto_missao.json"))
    mission = Mission.from_dict(mission_data)
    state = json.loads(_read_text(root, "execucao.json"))
    if not isinstance(state, dict):
        raise ValueError("Registro de execucao invalido")
    if (mission.repository != "hallanbrito/CHDevFlow" or
            state.get("mission_digest") != mission.digest or
            state.get("mission_id") != mission.mission_id or
            state.get("issue") != mission.issue or
            state.get("status") != "AGUARDANDO_PO"):
        raise ValueError("Registro, repositorio e manifesto da missao divergentes")
    _expected_files(state)  # valida tipos, indices e estados antes de iterar
    if not SHA40.fullmatch(mission.base_sha):
        raise ValueError("Base Git da missao invalida")
    for i, row in enumerate(state.get("attempts", []), 1):
        code = _read_text(root, f"attempt-{i:02d}/codigo.py")
        if hashlib.sha256(code.encode("utf-8")).hexdigest() != row.get("sha256"):
            raise ValueError("SHA do codigo difere do registro da tentativa")
    return mission, state


def create_provenance(root: Path) -> dict:
    """Somente na emissao do terceiro veto; manifesto e estado ja persistidos."""
    mission, state = _state(root)
    files = _expected_files(state)
    return {
        "schema": SCHEMA,
        "mission_digest": mission.digest,
        "base_sha": mission.base_sha,
        "files_sha256": _artifact_hashes(root, files),
    }


def verify_provenance(root: Path, outbox: dict) -> dict:
    proof = outbox.get("provenance")
    if not isinstance(proof, dict) or set(proof) != {
        "schema", "mission_digest", "base_sha", "files_sha256"}:
        raise ValueError("Outbox sem prova completa de proveniencia")
    if proof["schema"] != SCHEMA:
        raise ValueError("Schema de proveniencia invalido")
    mission, state = _state(root)
    if (proof["mission_digest"] != mission.digest or
            proof["base_sha"] != mission.base_sha or
            outbox.get("mission_id") != mission.mission_id or
            outbox.get("issue") != mission.issue or
            outbox.get("execution_id") != state.get("execution_id") or
            outbox.get("attempts") != 3 or
            outbox.get("returns") != 2 or
            outbox.get("third_attempt_status") != state["attempts"][2]["status"] or
            outbox.get("code_sha256") != state["attempts"][2]["sha256"]):
        raise ValueError("Outbox, manifesto e execucao nao correspondem")
    expected = _artifact_hashes(root, _expected_files(state))
    hashes = proof["files_sha256"]
    if (not isinstance(hashes, dict) or set(hashes) != set(expected) or
            any(not isinstance(v, str) or not SHA256.fullmatch(v)
                for v in hashes.values()) or hashes != expected):
        raise ValueError("Hashes de evidencias do dossie divergentes")
    return proof
