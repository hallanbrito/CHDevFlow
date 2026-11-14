"""Piloto CHDevFlow F5. Manual, descartável, com opt-in. NÃO é sandbox de SO."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

SOURCE = "src/estoque.py"
ALLOWED = frozenset(("mission.txt", "tests/test_acceptance.py", SOURCE))
MISSION = """Laboratório CHDevFlow F5. Crie SOMENTE src/estoque.py. Implemente:
movimentar(saldo: int, tipo: str, quantidade: int) -> int: saldo e
quantidade inteiros >= 0 sem bool; tipo 'entrada' soma e 'saida' subtrai;
saida insuficiente ou argumento inválido => ValueError.
pode_separar(saldo: int, quantidade: int) -> bool: inteiros >= 0 sem bool,
retorna saldo >= quantidade; inválidos => ValueError.
Sem bibliotecas externas; não altere tests, mission.txt nem outros arquivos.
Sem rede, GitHub, install, deploy, agendamento ou segredos.
"""
AGY_OUTPUT_PROMPT = MISSION + """
IMPORTANTE PARA MODO HEADLESS: não dependa de escrever arquivos no disco.
Responda apenas com UM único bloco Markdown contendo código Python para
as duas funções. Sem explicações antes ou depois; não use ferramentas,
terminal, rede, imports, arquivos externos nem dependências.
Use formato Markdown com abertura de bloco python e fechamento de bloco.
O dispatcher gravará apenas src/estoque.py depois de validar seu código.
"""

ACCEPTANCE = '''import importlib.util
import unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location(
    "estoque", Path(__file__).resolve().parents[1] / "src" / "estoque.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class Acceptance(unittest.TestCase):
    def test_entrada(self): self.assertEqual(mod.movimentar(3,"entrada",2),5)
    def test_saida(self): self.assertEqual(mod.movimentar(3,"saida",2),1)
    def test_zero(self): self.assertEqual(mod.movimentar(0,"entrada",0),0)
    def test_falta(self):
        with self.assertRaises(ValueError): mod.movimentar(1,"saida",2)
    def test_tipo(self):
        with self.assertRaises(ValueError): mod.movimentar(3,"outro",1)
    def test_negativo(self):
        with self.assertRaises(ValueError): mod.movimentar(3,"entrada",-1)
    def test_bool(self):
        with self.assertRaises(ValueError): mod.movimentar(True,"entrada",1)
    def test_separar(self):
        self.assertTrue(mod.pode_separar(5,5))
        self.assertFalse(mod.pode_separar(3,4))
    def test_separar_bool(self):
        with self.assertRaises(ValueError): mod.pode_separar(4,True)
'''
_SECRET = re.compile(
    r"(?i)(?:github_pat_[a-z0-9_]{14,}|gh[opsur]_[a-z0-9_]{16,}"
    r"|sk-[a-z0-9_-]{18,}|(?:token|api[_-]?key|password)\s*[:=]\s*\S+)"
)
_DROP = ("OPENAI_API_KEY", "CODEX_API_KEY", "GOOGLE_API_KEY",
         "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_API_KEY")


@dataclass(frozen=True)
class ProcessResult:
    code: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass
class LabResult:
    status: str = "INICIADO"
    stages: dict[str, str] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    agent_calls: list[str] = field(default_factory=list)
    code_sha256: str | None = None
    codex_verdict: str = "NAO_EXECUTADO"
    workspace: str = ""
    evidence_dir: str = ""
    cost_verified: bool = False
    os_isolation_verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)[:50000]


def _agent_environment() -> dict[str, str]:
    result = dict(os.environ)
    for key in _DROP:
        result.pop(key, None)
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["NO_COLOR"] = "1"
    return result


def _executables() -> tuple[list[str], list[str]]:
    agy = shutil.which("agy.exe") or shutil.which("agy")
    if sys.platform == "win32":
        codex = shutil.which("codex.cmd") or shutil.which("codex.exe")
        if not codex:
            ps = shutil.which("codex.ps1")
            shell = shutil.which("powershell.exe")
            if ps and shell:
                return ([agy] if agy else []), [
                    shell, "-NoProfile", "-NonInteractive", "-File", ps]
    else:
        codex = shutil.which("codex")
    return ([agy] if agy else []), ([codex] if codex else [])


def _kill(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _run_command(command: list[str], *, cwd: Path,
                 stdin: str | None, timeout: int) -> ProcessResult:
    """Processo sem shell=True; timeout tenta matar a árvore toda."""
    process = subprocess.Popen(
        command, cwd=cwd, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_agent_environment(),
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                       if sys.platform == "win32" else 0),
        start_new_session=(sys.platform != "win32"),
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout)
        return ProcessResult(process.returncode, _clean(stdout or ""), _clean(stderr or ""))
    except subprocess.TimeoutExpired:
        _kill(process)
        return ProcessResult(-1, "", "TIMEOUT: processo interrompido", True)
    except BaseException:
        _kill(process)
        raise


def _files(workspace: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for base, dirs, names in os.walk(workspace, followlinks=False):
        for name in dirs + names:
            if (Path(base) / name).is_symlink():
                raise ValueError("Symlink criado no laboratório")
        for name in names:
            path = Path(base) / name
            relative = path.relative_to(workspace).as_posix()
            if relative not in ALLOWED:
                raise ValueError(f"Arquivo extra: {relative}")
            if path.stat().st_size > 100_000:
                raise ValueError("Arquivo excedeu 100KiB")
            found[relative] = path.read_bytes()
    return found



def diagnose_existing_lab(*, workspace: Path, evidence: Path) -> dict:
    """Inspeciona as pastas do piloto antigo SEM executar modelos/processos.

    Retorna apenas metadados/nomes relativos; nunca lê ou imprime o texto
    da resposta AGY, que pode conter dados que precisam de revisão local.
    """
    workspace = workspace.expanduser().absolute()
    evidence = evidence.expanduser().absolute()
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("Workspace do piloto não encontrada ou simbólica")
    if not evidence.is_dir() or evidence.is_symlink():
        raise ValueError("Pasta de evidências não encontrada ou simbólica")
    files: list[str] = []
    dirs: list[str] = []
    symlinks: list[str] = []
    for base, directories, names in os.walk(workspace, followlinks=False):
        for name in directories + names:
            path = Path(base) / name
            relative = path.relative_to(workspace).as_posix()
            if path.is_symlink():
                symlinks.append(relative)
            elif path.is_dir():
                dirs.append(relative)
            else:
                files.append(relative)
    present = set(files)
    expected = ALLOWED
    # Os nomes são locais, mas não devolver estrutura ilimitada de um diretório
    # potencialmente contaminado por uma ferramenta externa.
    return {
        "status": "DIAGNOSTICO_SOMENTE_LEITURA",
        "workspace": str(workspace),
        "evidence_dir": str(evidence),
        "expected_files": sorted(expected),
        "present_files": sorted(files)[:50],
        "missing_files": sorted(expected - present),
        "extra_files": sorted(present - expected)[:50],
        "extra_directories": sorted(set(dirs) - {"src", "tests"})[:50],
        "symlinks": sorted(symlinks)[:50],
        "agy_log_exists": (evidence / "resposta_agy.md").is_file(),
        "agy_log_bytes": (
            (evidence / "resposta_agy.md").stat().st_size
            if (evidence / "resposta_agy.md").is_file() else None
        ),
        "files_truncated": len(files) > 50,
    }


def _validate_estoque_ast(source: str) -> None:
    """Validação estrutural mínima; NÃO comprova sandbox de SO."""
    tree = ast.parse(source)
    if len(tree.body) != 2 or not all(isinstance(node, ast.FunctionDef) for node in tree.body):
        raise ValueError("Módulo deve conter exatamente duas funções")
    if {node.name for node in tree.body} != {"movimentar", "pode_separar"}:
        raise ValueError("Funções do contrato ausentes ou inesperadas")
    dangerous = {"exec", "eval", "__import__", "open", "compile", "input",
                 "globals", "locals", "getattr", "setattr", "delattr", "breakpoint"}
    blocked = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
               ast.ClassDef, ast.AsyncFunctionDef, ast.Lambda, ast.With,
               ast.AsyncWith, ast.Try)
    for node in ast.walk(tree):
        if isinstance(node, blocked):
            raise ValueError("Construção Python proibida no laboratório")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in dangerous:
                raise ValueError("Chamada proibida")
            if isinstance(node.func, ast.Attribute):
                raise ValueError("Chamada dinâmica a atributo proibida")
        if isinstance(node, ast.Attribute):
            raise ValueError("Acesso a atributo proibido")


def _extract_agy_source(response: str) -> str:
    """Aceita somente um bloco Python ou código puro, nunca prosa misturada."""
    if not isinstance(response, str) or len(response) > 30000:
        raise ValueError("Resposta AGY ausente ou excessiva")
    pattern = r"(?s)```(?:python|py)?[ \t]*\r?\n(.*?)\r?\n```"
    blocks = re.findall(pattern, response, flags=re.I)
    if len(blocks) == 1:
        code = blocks[0].strip() + "\n"
    elif not blocks and response.lstrip().startswith(("def movimentar(", "def pode_separar(")):
        code = response.strip() + "\n"
    else:
        raise ValueError("AGY não devolveu um bloco Python único")
    if len(code.encode("utf-8")) > 16000:
        raise ValueError("Resposta Python excede 16 KiB")
    _validate_estoque_ast(code)
    return code


def _recover_source_from_response(workspace: Path, response: str,
                                  original: dict[str, bytes]) -> bool:
    """Aplica resposta textual SOMENTE se original está inalterado e src ausente."""
    generated = _files(workspace)
    if SOURCE in generated:
        return False
    if set(generated) != set(original) or any(
        generated[name] != original[name] for name in original
    ):
        return False
    code = _extract_agy_source(response)
    target = workspace / SOURCE
    if target.is_symlink() or target.exists():
        raise ValueError("Destino do código não está vazio")
    target.write_text(code, encoding="utf-8")
    return True


def _report(folder: Path, data: LabResult) -> None:
    (folder / "execucao.json").write_text(
        json.dumps(data.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# CHDevFlow F5 — laboratório manual", "",
             f"Estado: {data.status}",
             f"Workspace: {data.workspace}",
             f"Agentes chamados: {', '.join(data.agent_calls) or 'nenhum'}",
             f"SHA256: {data.code_sha256 or 'não gerado'}",
             f"Veredito: {data.codex_verdict}", "", "## Etapas"]
    lines.extend(f"- {k}: {v}" for k, v in data.stages.items())
    lines.extend(["", "## Achados"])
    lines.extend(f"- {x}" for x in data.findings)
    lines.extend(["", "Somente laboratório local voluntário. Custo e sandbox não atestados.",
                  "Sem push, merge, deploy, Project #2 ou agendamento."])
    (folder / "RELATORIO_COMPLETO_CH1.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def run_local_pilot(*, workspace: Path, evidence: Path,
                    accepted: bool, timeout: int = 480) -> LabResult:
    """Aciona agentes somente depois de confirmação manual expressa na CLI."""
    if not accepted:
        raise PermissionError("Aceite --i-accept-local-risk obrigatório")
    if type(timeout) is not int or not 120 <= timeout <= 900:
        raise ValueError("Timeout permitido: 120 a 900 segundos")
    workspace, evidence = workspace.expanduser().absolute(), evidence.expanduser().absolute()
    if workspace.exists() or evidence.exists():
        raise ValueError("Workspace e evidência precisam ser pastas NOVAS")
    if workspace == evidence or workspace in evidence.parents or evidence in workspace.parents:
        raise ValueError("Workspace e dossiê não podem ser aninhados")
    for path in (workspace, evidence):
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise ValueError("Diretório pai inseguro/inexistente")
    agy, codex = _executables()
    if not agy or not codex:
        raise ValueError("CLIs AGY e Codex devem estar instaladas no PATH")
    data = LabResult(workspace=str(workspace), evidence_dir=str(evidence))
    workspace.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()
    (workspace / "mission.txt").write_text(MISSION, encoding="utf-8")
    (workspace / "tests" / "test_acceptance.py").write_text(ACCEPTANCE, encoding="utf-8")
    original = _files(workspace)
    start = time.monotonic()
    remaining = lambda: max(1, timeout - int(time.monotonic() - start))
    try:
        data.stages["AGY"] = "EM_EXECUCAO"
        data.agent_calls.append("agy")
        agy_result = _run_command(
            [*agy, "--sandbox", "--mode", "accept-edits", "--print", AGY_OUTPUT_PROMPT],
            cwd=workspace, stdin=None, timeout=max(1, min(remaining(), int(timeout * .65))))
        (evidence / "resposta_agy.md").write_text(
            agy_result.stdout + "\n" + agy_result.stderr, encoding="utf-8")
        if agy_result.code or agy_result.timed_out:
            raise ValueError("AGY falhou ou excedeu timeout")
        recovered_from_text = _recover_source_from_response(
            workspace, agy_result.stdout, original
        )
        if recovered_from_text:
            data.stages["AGY_TEXT_ADAPTER"] = "PASS"
            data.findings.append("CHDevFlow aplicou o código da resposta AGY em src/estoque.py")
        generated = _files(workspace)
        expected = set(original) | {SOURCE}
        missing = sorted(expected - set(generated))
        extra_files = sorted(set(generated) - expected)
        if missing or extra_files:
            data.stages["AGY"] = "BLOQUEADO"
            data.stages["ESCOPO"] = "BLOQUEADO"
            raise ValueError(
                f"Arquivos inconsistentes: ausentes={missing[:15]}; "
                f"extras={extra_files[:15]}"
            )
        if any(generated[key] != original[key] for key in original):
            raise ValueError("AGY alterou mission ou teste independente")
        content = generated[SOURCE].decode("utf-8")
        _validate_estoque_ast(content)
        data.code_sha256 = hashlib.sha256(generated[SOURCE]).hexdigest()
        data.stages["AGY"] = "PASS"
        data.stages["ESCOPO"] = "PASS"
        patch = "".join(difflib.unified_diff(
            [], content.splitlines(keepends=True),
            fromfile="/dev/null", tofile=SOURCE))
        (evidence / "alteracoes.patch").write_text(patch, encoding="utf-8")
        acceptance = _run_command(
            [sys.executable, "-B", "-m", "unittest", "discover",
             "-s", "tests", "-p", "test_acceptance.py", "-v"],
            cwd=workspace, stdin=None, timeout=min(60, remaining()))
        (evidence / "logs_testes.txt").write_text(
            acceptance.stdout + "\n" + acceptance.stderr, encoding="utf-8")
        if acceptance.code or acceptance.timed_out:
            raise ValueError("Testes de aceite não passaram")
        data.stages["TESTES"] = "PASS"
        if remaining() < 20:
            raise ValueError("Tempo restante insuficiente para Codex")
        prompt = (
            "Auditoria somente leitura. Não edite arquivos.\n"
            "Revise o patch e testes. Primeira linha da resposta deve ser "
            "'VEREDITO: APROVAR_LAB' ou 'VEREDITO: BLOQUEADO'.\n"
            f"Requisitos:\n{MISSION}\nPatch:\n{patch[:12000]}\n"
            f"Testes:\n{(acceptance.stdout + acceptance.stderr)[-6000:]}")
        data.agent_calls.append("codex")
        reviewed = _run_command(
            [*codex, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"],
            cwd=workspace, stdin=prompt, timeout=remaining())
        (evidence / "auditoria_codex.md").write_text(
            reviewed.stdout + "\n" + reviewed.stderr, encoding="utf-8")
        verdict = re.search(
            r"(?im)^VEREDITO:\s*(APROVAR_LAB|BLOQUEADO)\b", reviewed.stdout)
        data.codex_verdict = verdict.group(1) if verdict else "INDETERMINADO"
        if reviewed.code or reviewed.timed_out or data.codex_verdict != "APROVAR_LAB":
            raise ValueError("Codex não aprovou")
        data.stages["CODEX"] = "PASS"
        data.status = "LAB_APROVADO_AGUARDANDO_CH1"
    except (ValueError, OSError, UnicodeError, SyntaxError, subprocess.SubprocessError) as exc:
        # Uma chamada que terminou mas deixou arquivos insuficientes não deve
        # ficar com status EM_EXECUCAO no relatório final.
        for stage, value in tuple(data.stages.items()):
            if value == "EM_EXECUCAO":
                data.stages[stage] = "BLOQUEADO"
        data.findings.append(_clean(str(exc)))
        data.status = "LAB_BLOQUEADO"
    finally:
        _report(evidence, data)
    return data
