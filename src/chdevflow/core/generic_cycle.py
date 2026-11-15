"""F6 experimental: CCC-01 para missao Python definida em manifesto.

Somente worktree Git DESCARTAVEL (CH-Lab-*), uma alteracao Python autorizada.
Opt-in do operador obrigatorio; testes de codigo de IA executam no HOST, sem
sandbox de SO. Nunca faz merge, deploy, Project #2 ou chamadas pagas por chave.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

from chdevflow.core.manual_pipeline_runner import load_manifest, plan_manual_mission
from chdevflow.core.experimental_pilot import (
    _agy_response, _clean, _codex_final_message, _executables,
    _run_command, _write_process_log,
)

MAX_ATTEMPTS = 3


@dataclass
class GenericResult:
    status: str
    execution_id: str
    mission_id: str
    issue: int
    mission_digest: str
    attempts: list[dict] = field(default_factory=list)
    returns_used: int = 0
    findings: list[str] = field(default_factory=list)
    cost_verified: bool = False
    os_isolation_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=15, check=False)
    if proc.returncode:
        raise ValueError("Falha na verificacao Git da worktree")
    return proc.stdout.strip()


def _read_safe(root: Path, relative: str) -> bytes:
    p = root / relative
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 100000:
        raise ValueError("Arquivo independente invalido")
    return p.read_bytes()


def _preflight(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Manifesto ausente ou link simbolico")
    root = path.parent.resolve()
    mission = load_manifest(path)
    if Path(mission.worktree).resolve() != root:
        raise ValueError("Worktree nao corresponde ao manifesto")
    if not root.name.startswith("CH-Lab-"):
        raise ValueError("Use worktree Git DESCARTAVEL denominada CH-Lab-*")
    if len(mission.allowed_paths) != 1:
        raise ValueError("F6: uma alteracao Python por missao")
    target = mission.allowed_paths[0]
    if not target.endswith(".py") or target.startswith("tests/"):
        raise ValueError("F6: escopo precisa ser arquivo Python fora de tests")
    if target == mission.prompt_ref:
        raise ValueError("Prompt da missao nao pode ser artefato AGY")
    observed = _git(root, "rev-parse", "--verify", "HEAD")
    branch = _git(root, "branch", "--show-current")
    clean = _git(root, "status", "--porcelain", "--untracked-files=all") == ""
    plan = plan_manual_mission(
        mission, observed_sha=observed, observed_branch=branch, worktree_clean=clean)
    if plan.state != "PLANEJADO_AGUARDANDO_GATE":
        raise ValueError("Missao invalida: " + plan.reason)
    p = root / target
    if not p.parent.is_dir() or p.is_symlink():
        raise ValueError("Diretorio do arquivo nao existe ou e link")
    if p.exists() and (not p.is_file() or p.stat().st_size > 32000):
        raise ValueError("Arquivo de destino invalido")
    prompt = _read_safe(root, mission.prompt_ref).decode("utf-8")
    if not prompt.strip() or len(prompt) > 12000:
        raise ValueError("Prompt vazio ou excessivo")
    tests = root / "tests"
    if not tests.is_dir() or tests.is_symlink():
        raise ValueError("Testes independentes obrigatorios")
    snapshot = {mission.prompt_ref: _read_safe(root, mission.prompt_ref)}
    for test in tests.rglob("test_*.py"):
        relative = test.relative_to(root).as_posix()
        snapshot[relative] = _read_safe(root, relative)
    if len(snapshot) < 2 or len(snapshot) > 80 or target in snapshot:
        raise ValueError("Teste ausente, excessivo ou dentro da allowlist")
    return mission, root, target, prompt, snapshot


def _guard(root: Path, target: str, snapshot: dict, *, allow_target: bool):
    dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
    for line in dirty.splitlines():
        # Porcelain v1: prefixo XY e caminho relativo.
        if len(line) < 4 or line[0:2].strip() not in {"M", "??"}:
            raise ValueError("Status Git inseguro")
        if not allow_target or line[3:] != target:
            raise ValueError("Arquivo fora do escopo alterado")
    if any(_read_safe(root, name) != value for name, value in snapshot.items()):
        raise ValueError("Prompt ou teste independente adulterado")


def _extract(response: str) -> str:
    if not isinstance(response, str) or len(response) > 40000:
        raise ValueError("AGY respondeu conteudo invalido")
    fence = chr(96) * 3
    code = response.strip()
    prefix = fence + "python\n"
    if not (code.startswith(prefix) and code.endswith("\n" + fence)):
        raise ValueError("AGY deve fornecer somente bloco Markdown Python")
    source = code[len(prefix):-len(fence)].strip() + "\n"
    if len(source.encode("utf-8")) > 32000:
        raise ValueError("Arquivo Python excessivo")
    ast.parse(source)
    return source


def _persist(out: Path, result: GenericResult):
    state = out / "execucao.json"
    temp = out / "execucao.json.tmp"
    with temp.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, state)
    lines = [
        "# CH-PIPE-01/F6 — Missao Python CCC-01", "",
        f"Missao: {result.mission_id}, Issue #{result.issue}",
        f"Estado: {result.status}",
        f"Tentativas AGY: {len(result.attempts)}/3",
        f"Devolucoes: {result.returns_used}/2",
        "", "Custo e isolamento de SO nao comprovados.",
        "Sem merge, deploy, Project #2 ou automacao.",
        "", "## Rodadas"]
    for item in result.attempts:
        lines.append(
            f"- {item['number']}/3: {item['status']}, "
            f"Codex={item['codex_verdict']}, sha256={item.get('sha256')}")
    lines.extend(["", "## Achados", *["- " + x for x in result.findings]])
    (out / "RELATORIO_COMPLETO_CH1.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def run_generic_cycle(*, manifest_path: Path, evidence: Path,
                      accepted: bool, timeout: int = 480) -> GenericResult:
    """Execucao real opt-in. No maximo 3 AGY/2 devolucoes, tempo TOTAL."""
    if not accepted:
        raise PermissionError("Exige --i-accept-local-risk")
    if type(timeout) is not int or not 120 <= timeout <= 900:
        raise ValueError("Timeout total invalido (120..900)")
    manifest_path = manifest_path.expanduser().absolute()
    evidence = evidence.expanduser().absolute()
    if (evidence.exists() or evidence.is_symlink() or
            not evidence.parent.is_dir() or evidence.parent.is_symlink() or
            manifest_path.parent in evidence.parents or
            evidence in manifest_path.parent.parents):
        raise ValueError("Dossie deve ser pasta NOVA fora da worktree")
    mission, root, target, prompt, snapshot = _preflight(manifest_path)
    agy, codex = _executables()
    if not agy or not codex:
        raise ValueError("CLIs locais AGY e Codex ausentes")
    evidence.mkdir(mode=0o700)
    result = GenericResult(
        "INICIADO", uuid4().hex, mission.mission_id, mission.issue, mission.digest)
    deadline = time.monotonic() + min(timeout, mission.timeout_seconds)
    source_path = root / target
    previous = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
    feedback = ""
    _persist(evidence, result)
    for number in range(1, MAX_ATTEMPTS + 1):
        remaining = int(deadline - time.monotonic())
        if remaining < 120:
            result.status = "ORCAMENTO_ESGOTADO"
            result.findings.append("Sem tempo para outra tentativa")
            break
        directory = evidence / f"attempt-{number:02d}"
        directory.mkdir()
        row = {"number": number, "status": "AGY_EXECUTANDO",
               "codex_verdict": "NAO_EXECUTADO", "sha256": None}
        result.attempts.append(row)
        result.status = "EM_EXECUCAO"
        _persist(evidence, result)  # write-ahead: nunca cobrar AGY sem registrar
        stage = "AGY"
        try:
            _guard(root, target, snapshot, allow_target=number > 1)
            fence = chr(96) * 3
            request = (
                "Implemente APENAS o arquivo Python da missao abaixo. "
                "Sem ferramentas, terminal, rede, edicao direta, instalacao, "
                "GitHub ou agendamento. Responda um unico bloco Markdown python "
                "com o arquivo COMPLETO.\n"
                f"Missao {mission.mission_id} | issue {mission.issue} | arquivo {target}\n"
                f"Requisitos:\n{prompt}\n"
                f"Codigo anterior:\n{fence}python\n{previous}\n{fence}\n"
                + (f"Correcao obrigatoria:\n{feedback}\n" if feedback else ""))
            raw = _run_command(
                [*agy, "--sandbox", "--mode", "plan", "--disable-slash-commands",
                 "--output-format", "json", "--print", request],
                cwd=root, stdin=None, timeout=min(remaining, int(timeout * .65)))
            _write_process_log(directory / "agy.log", raw)
            if raw.code or raw.timed_out:
                raise ValueError("AGY indisponivel/timeout; nao repetir")
            candidate = _extract(_agy_response(raw))
            _guard(root, target, snapshot, allow_target=number > 1)
            source_path.write_text(candidate, encoding="utf-8", newline="\n")
            sha = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
            row["sha256"] = sha
            (directory / "codigo.py").write_text(candidate, encoding="utf-8")
            patch = "".join(difflib.unified_diff(
                previous.splitlines(keepends=True),
                candidate.splitlines(keepends=True),
                fromfile="a/" + target, tofile="b/" + target))
            (directory / "alteracoes.patch").write_text(_clean(patch), encoding="utf-8")
            _guard(root, target, snapshot, allow_target=True)
            stage = "TESTES"
            remaining = int(deadline - time.monotonic())
            if remaining < 30:
                raise ValueError("Orcamento sem tempo para testes/Codex")
            tests = _run_command(
                [sys.executable, "-I", "-B", "-m", "unittest", "discover",
                 "-s", "tests", "-p", "test_*.py", "-v"],
                cwd=root, stdin=None, timeout=min(60, remaining))
            _write_process_log(directory / "testes.log", tests)
            if tests.timed_out:
                raise ValueError("Timeout nos testes")
            test_output = tests.stdout + tests.stderr
            if not re.search(r"Ran [1-9][0-9]* tests?", test_output):
                raise ValueError("Suite nao reportou testes reais")
            _guard(root, target, snapshot, allow_target=True)
            if tests.code:
                row["status"] = "TESTES_REPROVADOS"
                feedback = _clean(test_output)[-6000:]
            else:
                stage = "CODEX"
                remaining = int(deadline - time.monotonic())
                if remaining < 20:
                    raise ValueError("Tempo restante insuficiente para Codex")
                codex_prompt = (
                    "Auditoria independente apenas textual. Nao edite nem use ferramentas. "
                    "Primeira linha OBRIGATORIA: VEREDITO: APROVAR_LAB ou "
                    "VEREDITO: BLOQUEADO. Em seguida achados e correcoes.\n"
                    f"Missao:\n{prompt}\nArquivo: {target}\n"
                    f"Patch:\n{patch}\nTestes:\n{test_output[-6000:]}")
                audit = _run_command(
                    [*codex, "-a", "never", "exec", "--sandbox", "read-only",
                     "--ephemeral", "--skip-git-repo-check", "--json", "-"],
                    cwd=root, stdin=codex_prompt, timeout=remaining)
                _write_process_log(directory / "codex.log", audit)
                if audit.timed_out or audit.code:
                    raise ValueError("Codex indisponivel/timeout; nao repetir")
                text = _codex_final_message(audit.stdout)
                (directory / "auditoria_codex.md").write_text(
                    _clean(text), encoding="utf-8")
                verdict = text.strip().splitlines()[0].strip()
                if verdict not in ("VEREDITO: APROVAR_LAB", "VEREDITO: BLOQUEADO"):
                    raise ValueError("Codex sem parecer final valido")
                row["codex_verdict"] = verdict.split(": ", 1)[1]
                _guard(root, target, snapshot, allow_target=True)
                if row["codex_verdict"] == "APROVAR_LAB":
                    row["status"] = "PASS"
                    result.status = "APROVADO_AGUARDANDO_CH1"
                    break
                row["status"] = "CODEX_REPROVOU"
                feedback = _clean(text)[-6000:]
            previous = candidate
            if number == MAX_ATTEMPTS:
                result.status = "AGUARDANDO_PO"
                result.findings.append("Tres reprovações; nenhuma quarta chamada")
                (evidence / "escalonamento_po.json").write_text(
                    json.dumps({
                        "execution_id": result.execution_id,
                        "mission_id": mission.mission_id, "issue": mission.issue,
                        "status": "AGUARDANDO_PO",
                        "publication_status": "PENDENTE_DE_AUTORIZACAO",
                        "attempts": 3, "returns": result.returns_used,
                    }, ensure_ascii=False, indent=2), encoding="utf-8")
                break
            (directory / "feedback_para_agy.md").write_text(
                _clean(feedback), encoding="utf-8")
            result.returns_used += 1
            result.status = "CORRECAO_PENDENTE"
        except (ValueError, OSError, UnicodeError, SyntaxError,
                subprocess.SubprocessError) as exc:
            row["status"] = "BLOQUEADO"
            result.status = "BLOQUEADO_INFRA_OU_ESCOPO"
            result.findings.append(stage + ": " + _clean(str(exc)))
            break
        finally:
            _persist(evidence, result)
    _persist(evidence, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CCC-01/F6 - missao Python local")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=480)
    parser.add_argument("--i-accept-local-risk", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_generic_cycle(
            manifest_path=args.manifest, evidence=args.evidence_dir,
            accepted=args.i_accept_local_risk, timeout=args.timeout)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status == "APROVADO_AGUARDANDO_CH1" else 1
    except (ValueError, PermissionError, OSError) as exc:
        print("CCC-01/F6 BLOQUEADO: " + _clean(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
