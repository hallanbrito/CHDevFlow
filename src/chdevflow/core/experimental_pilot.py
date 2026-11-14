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
import stat
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
Entregue o conteúdo de src/estoque.py somente na resposta. O CHDevFlow
gravará o arquivo. Não use ferramentas, terminal, rede ou arquivos.
Retorne um único bloco Markdown Python com exatamente as duas funções.
Use condicionais e operações simples, sem imports, decorators, valores
padrão, funções auxiliares ou loops. Use type(x) is int para inteiros.
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
        codex = shutil.which("codex.exe")
        wrapper = shutil.which("codex.cmd")
        if not codex and wrapper:
            npm_dir = Path(wrapper).parent
            entry = npm_dir / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            bundled_node = npm_dir / "node.exe"
            node = str(bundled_node) if bundled_node.is_file() else shutil.which("node.exe")
            if node and entry.is_file():
                return ([agy] if agy else []), [node, str(entry)]
            codex = wrapper
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
            pass
        if process.poll() is None:
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
        return ProcessResult(process.returncode, stdout or "", stderr or "")
    except subprocess.TimeoutExpired as exc:
        _kill(process)
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        return ProcessResult(-1, stdout, stderr + "\nTIMEOUT: processo interrompido", True)
    except BaseException:
        _kill(process)
        raise


def _is_link(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _raise_walk_error(error: OSError) -> None:
    raise error


def _files(workspace: Path) -> dict[str, bytes]:
    if _is_link(workspace):
        raise ValueError("Workspace foi substituído por um link")
    found: dict[str, bytes] = {}
    for root, dirs, names in os.walk(workspace, followlinks=False, onerror=_raise_walk_error):
        base = Path(root)
        for name in dirs + names:
            path = base / name
            if _is_link(path):
                raise ValueError("Link ou junction criado no laboratório")
        for name in dirs:
            if (base / name).relative_to(workspace).as_posix() not in {"src", "tests"}:
                raise ValueError(f"Diretório extra: {(base / name).relative_to(workspace)}")
        for name in names:
            path = Path(base) / name
            relative = path.relative_to(workspace).as_posix()
            if relative not in ALLOWED:
                raise ValueError(f"Arquivo extra: {relative}")
            if not path.is_file():
                raise ValueError(f"Artefato não é arquivo regular: {relative}")
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
    """Limita o módulo ao subconjunto necessário para a tarefa de estoque."""
    tree = ast.parse(source)
    signatures = {"movimentar": ("saldo", "tipo", "quantidade"),
                  "pode_separar": ("saldo", "quantidade")}
    if len(tree.body) != 2 or any(not isinstance(node, ast.FunctionDef) for node in tree.body):
        raise ValueError("Módulo deve conter exatamente duas funções")
    if {node.name for node in tree.body} != signatures.keys():
        raise ValueError("Funções do contrato ausentes ou inesperadas")
    allowed = (
        ast.If, ast.Return, ast.Raise, ast.Assign, ast.Expr, ast.Constant,
        ast.Name, ast.Load, ast.Store, ast.BoolOp, ast.And, ast.Or,
        ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub,
        ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.Tuple, ast.Call,
        ast.IfExp, ast.Pass,
    )
    safe_names = {"type", "isinstance", "ValueError", "int", "str", "bool"}
    for fn in tree.body:
        args = fn.args
        annotations = [fn.returns, *(arg.annotation for arg in args.args)]
        if (fn.decorator_list or getattr(fn, "type_params", ()) or args.defaults or args.posonlyargs
                or args.kwonlyargs or args.vararg or args.kwarg
                or tuple(arg.arg for arg in args.args) != signatures[fn.name]
                or any(node is not None and (
                    not isinstance(node, ast.Name) or node.id not in {"int", "str", "bool"}
                ) for node in annotations)):
            raise ValueError("Assinatura do contrato inválida")
        body = [node for statement in fn.body for node in ast.walk(statement)]
        local_names = set(signatures[fn.name])
        local_names.update(node.id for node in body if isinstance(node, ast.Name)
                           and isinstance(node.ctx, ast.Store))
        for node in body:
            if not isinstance(node, allowed):
                raise ValueError(f"Construção Python proibida: {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id not in local_names | safe_names:
                raise ValueError("Nome não permitido no laboratório")
            if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name)
                or node.func.id not in {"type", "isinstance", "ValueError"}
                or node.func.id in local_names
                or (node.func.id == "type" and len(node.args) != 1)
            ):
                raise ValueError("Chamada proibida")
    compile(tree, SOURCE, "exec")


def _agy_response(result: ProcessResult) -> str:
    try:
        envelope = json.loads(result.stdout.lstrip("\ufeff"))
    except ValueError as exc:
        raise ValueError("AGY não devolveu um envelope JSON válido") from exc
    if not isinstance(envelope, dict):
        raise ValueError("Envelope AGY inválido")
    status = envelope.get("status")
    if result.code or status != "SUCCESS":
        detail = envelope.get("error") or result.stderr.strip() or "sem detalhe"
        raise ValueError(f"AGY falhou (exit={result.code}, status={status}): {_clean(str(detail))[:1000]}")
    response = envelope.get("response")
    if not isinstance(response, str):
        raise ValueError("Envelope AGY sem resposta textual")
    return response


def _codex_final_message(stdout: str) -> str:
    message = ""
    completed = False
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise ValueError("Codex não devolveu eventos JSONL válidos") from exc
        if not isinstance(event, dict):
            raise ValueError("Evento Codex inválido")
        event_type = event.get("type")
        if event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                message = item.get("text", "")
        elif event_type == "turn.completed":
            completed = True
        elif event_type == "turn.failed":
            raise ValueError("Turno de auditoria Codex falhou")
    if not completed or not isinstance(message, str) or not message.strip():
        raise ValueError("Codex terminou sem parecer final")
    return message


def _write_process_log(path: Path, result: ProcessResult) -> None:
    path.write_text(
        f"exit={result.code} timeout={result.timed_out}\n"
        f"\n[stdout]\n{_clean(result.stdout)}\n[stderr]\n{_clean(result.stderr)}\n",
        encoding="utf-8",
    )


def _extract_agy_source(response: str) -> str:
    """Aceita somente um bloco Python ou código puro, nunca prosa misturada."""
    if not isinstance(response, str) or len(response) > 30000:
        raise ValueError("Resposta AGY ausente ou excessiva")
    pattern = r"(?s)```(?:python|py)?[ \t]*\r?\n(.*?)\r?\n```"
    block = re.fullmatch(pattern, response.strip(), flags=re.I)
    if block:
        code = block.group(1).strip() + "\n"
    elif response.lstrip().startswith(("def movimentar(", "def pode_separar(")):
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
    with target.open("x", encoding="utf-8", newline="\n") as out:
        out.write(code)
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
    workspace, evidence = workspace.expanduser(), evidence.expanduser()
    if any(_is_link(path) for path in (workspace, evidence)):
        raise ValueError("Workspace e evidência não podem ser links")
    workspace, evidence = workspace.resolve(), evidence.resolve()
    if workspace.exists() or evidence.exists():
        raise ValueError("Workspace e evidência precisam ser pastas NOVAS")
    if workspace == evidence or workspace in evidence.parents or evidence in workspace.parents:
        raise ValueError("Workspace e dossiê não podem ser aninhados")
    for path in (workspace, evidence):
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise ValueError("Diretório pai inseguro/inexistente")
    data = LabResult(workspace=str(workspace), evidence_dir=str(evidence))
    data.stages.update(dict.fromkeys(("AGY", "ESCOPO", "TESTES", "CODEX"), "NAO_EXECUTADO"))
    evidence.mkdir(mode=0o700)
    deadline = time.monotonic() + timeout

    def remaining() -> int:
        seconds = int(deadline - time.monotonic())
        if seconds < 1:
            raise ValueError("Tempo total do laboratório esgotado")
        return seconds

    try:
        workspace.mkdir(mode=0o700)
        (workspace / "src").mkdir()
        (workspace / "tests").mkdir()
        (workspace / "mission.txt").write_text(MISSION, encoding="utf-8")
        (workspace / "tests" / "test_acceptance.py").write_text(ACCEPTANCE, encoding="utf-8")
        original = _files(workspace)
        agy, codex = _executables()
        if not agy or not codex:
            raise ValueError("CLIs AGY e Codex devem estar instaladas no PATH")
        data.stages["AGY"] = "EM_EXECUCAO"
        data.agent_calls.append("agy")
        agy_result = _run_command(
            [*agy, "--sandbox", "--mode", "plan", "--disable-slash-commands",
             "--output-format", "json", "--print", AGY_OUTPUT_PROMPT],
            cwd=workspace, stdin=None, timeout=min(remaining(), int(timeout * .65)))
        _write_process_log(evidence / "resposta_agy.md", agy_result)
        if agy_result.timed_out:
            raise ValueError("AGY excedeu timeout")
        if agy_result.code and not agy_result.stdout.strip():
            raise ValueError(f"AGY falhou (exit={agy_result.code}): {_clean(agy_result.stderr)[:1000]}")
        response = _agy_response(agy_result)
        data.stages["ESCOPO"] = "EM_EXECUCAO"
        try:
            recovered_from_text = _recover_source_from_response(workspace, response, original)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"AGY não entregou artefato válido {SOURCE}: {exc}") from exc
        if recovered_from_text:
            data.stages["AGY_TEXT_ADAPTER"] = "PASS"
        generated = _files(workspace)
        if set(generated) != set(original) | {SOURCE}:
            raise ValueError(f"Arquivos esperados ausentes: {sorted((set(original) | {SOURCE}) - set(generated))}")
        if any(generated[key] != original[key] for key in original):
            raise ValueError("AGY alterou mission ou teste independente")
        if len(generated[SOURCE]) > 16000:
            raise ValueError("Módulo Python excede 16 KiB")
        content = generated[SOURCE].decode("utf-8")
        _validate_estoque_ast(content)
        data.code_sha256 = hashlib.sha256(generated[SOURCE]).hexdigest()
        data.stages["AGY"] = "PASS"
        data.stages["ESCOPO"] = "PASS"
        patch = "".join(difflib.unified_diff(
            [], content.splitlines(keepends=True),
            fromfile="/dev/null", tofile=SOURCE))
        (evidence / "alteracoes.patch").write_text(patch, encoding="utf-8")
        data.stages["TESTES"] = "EM_EXECUCAO"
        acceptance = _run_command(
            [sys.executable, "-I", "-B", "-m", "unittest", "discover",
             "-s", "tests", "-p", "test_acceptance.py", "-v"],
            cwd=workspace, stdin=None, timeout=min(60, remaining()))
        _write_process_log(evidence / "logs_testes.txt", acceptance)
        if acceptance.code or acceptance.timed_out:
            raise ValueError("Testes de aceite não passaram")
        if _files(workspace) != generated:
            raise ValueError("Workspace alterado durante os testes")
        data.stages["TESTES"] = "PASS"
        if remaining() < 20:
            raise ValueError("Tempo restante insuficiente para Codex")
        prompt = (
            "Auditoria somente leitura. Não edite arquivos.\n"
            "Revise apenas os dados a seguir, sem chamar ferramentas. "
            "Primeira linha da resposta deve ser "
            "'VEREDITO: APROVAR_LAB' ou 'VEREDITO: BLOQUEADO'.\n"
            f"Requisitos:\n{MISSION}\nPatch:\n{patch}\n"
            f"Testes:\n{(acceptance.stdout + acceptance.stderr)[-6000:]}")
        data.stages["CODEX"] = "EM_EXECUCAO"
        data.agent_calls.append("codex")
        reviewed = _run_command(
            [*codex, "-a", "never", "exec", "--sandbox", "read-only", "--ephemeral",
             "--ignore-user-config", "--skip-git-repo-check", "--json", "-"],
            cwd=workspace, stdin=prompt, timeout=remaining())
        _write_process_log(evidence / "codex_processo.log", reviewed)
        data.codex_verdict = "INDETERMINADO"
        if reviewed.timed_out:
            raise ValueError("Codex excedeu timeout")
        if reviewed.code:
            raise ValueError(f"Codex falhou (exit={reviewed.code}); consulte codex_processo.log")
        message = _codex_final_message(reviewed.stdout)
        (evidence / "auditoria_codex.md").write_text(_clean(message), encoding="utf-8")
        verdict = re.fullmatch(
            r"VEREDITO: (APROVAR_LAB|BLOQUEADO)", message.strip().splitlines()[0].strip())
        if verdict:
            data.codex_verdict = verdict.group(1)
        if data.codex_verdict != "APROVAR_LAB":
            raise ValueError("Codex não emitiu veredito de aprovação")
        if _files(workspace) != generated:
            raise ValueError("Workspace alterado durante a auditoria")
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
