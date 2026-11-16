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
from chdevflow.core.attested_executor import IMAGE_ID as ATTESTED_IMAGE_ID
from chdevflow.core.po_escalation_runtime_receipt import verify_runtime_receipt
from chdevflow.core.po_escalation import (
    _evidence_text, _json_unique, _read_evidence_bytes, _safe_file_within,
)

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


def _snapshot(root: Path) -> tuple[Mission, dict, dict[str, bytes]]:
    files = {}
    for relative in ("manifesto_missao.json", "execucao.json"):
        files[relative] = _read_evidence_bytes(_safe_file_within(root, relative))
    mission_data = _json_unique(_evidence_text(files["manifesto_missao.json"]))
    mission = Mission.from_dict(mission_data)
    state = _json_unique(_evidence_text(files["execucao.json"]))
    if not isinstance(state, dict):
        raise ValueError("Registro de execucao invalido")
    if (mission.repository != "hallanbrito/CHDevFlow" or
            state.get("mission_digest") != mission.digest or
            state.get("mission_id") != mission.mission_id or
            state.get("issue") != mission.issue or
            state.get("status") != "AGUARDANDO_PO"):
        raise ValueError("Registro, repositorio e manifesto da missao divergentes")
    expected = _expected_files(state)
    if not SHA40.fullmatch(mission.base_sha):
        raise ValueError("Base Git da missao invalida")
    for relative in expected:
        if relative not in files:
            files[relative] = _read_evidence_bytes(_safe_file_within(root, relative))
    for i, row in enumerate(state["attempts"], 1):
        code = _evidence_text(files[f"attempt-{i:02d}/codigo.py"])
        if hashlib.sha256(code.encode("utf-8")).hexdigest() != row.get("sha256"):
            raise ValueError("SHA do codigo difere do registro da tentativa")
    return mission, state, files


def _artifact_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {relative: hashlib.sha256(content).hexdigest()
            for relative, content in files.items()}


def create_provenance(root: Path) -> dict:
    """Somente na emissao do terceiro veto; manifesto e estado ja persistidos."""
    mission, _, files = _snapshot(root)
    return {
        "schema": SCHEMA,
        "mission_digest": mission.digest,
        "base_sha": mission.base_sha,
        "files_sha256": _artifact_hashes(files),
    }


def verify_provenance(root: Path, outbox: dict, *,
                      require_isolation: bool = False) -> dict:
    """Valida integridade local F6; isolamento e gate adicional apenas na F7."""

    proof = outbox.get("provenance")
    if not isinstance(proof, dict) or set(proof) != {
        "schema", "mission_digest", "base_sha", "files_sha256"}:
        raise ValueError("Outbox sem prova completa de proveniencia")
    if proof["schema"] != SCHEMA:
        raise ValueError("Schema de proveniencia invalido")
    mission, state, files = _snapshot(root)
    # F7 nao pode aceitar a string LEGADA como prova: ela e forjavel
    # sem identidade de build/consumo. F6 local continua admitindo
    # proveniencia por hash quando require_isolation=False.
    needs_external_runtime_receipt = False
    if require_isolation:
        isolated = state.get("test_execution")
        attested = (isolated ==
                    "docker-attested-e3b-sigstore:" + ATTESTED_IMAGE_ID)
        if (state.get("os_isolation_verified") is not True
                or not attested):
            raise ValueError(
                "Evidencia F7 sem execucao de testes Docker isolada comprovada: executor E3-B atestado necessario")
        needs_external_runtime_receipt = True
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
    expected = _artifact_hashes(files)
    hashes = proof["files_sha256"]
    if (not isinstance(hashes, dict) or set(hashes) != set(expected) or
            any(not isinstance(v, str) or not SHA256.fullmatch(v)
                for v in hashes.values()) or hashes != expected):
        raise ValueError("Hashes de evidencias do dossie divergentes")
    if needs_external_runtime_receipt:
        # Fica DEPOIS de validar todos os hashes locais. Na ausencia do
        # atestador V1, pins ainda vazios impedem validacao remota.
        verify_runtime_receipt(root, outbox, proof)
    return proof
