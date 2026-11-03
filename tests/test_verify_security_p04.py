"""Suíte de testes de segurança para AUD-GERAL-P0-04 (Issue #51, Épico #40).

Cobre a matriz de testes positivos e negativos (TP-01 a TP-10, TN-01 a TN-30),
incluindo allowlists, sanitização de ambiente e PATH, política de confiança (Project Trust),
bloqueio fail-closed de manifestos, limites reais de memória no streaming e contenção de timeout.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

# Garante acesso a src mesmo sem instalação global
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chdevflow.cli import main as cli_main
from chdevflow.core.config import (
    create_manifest_data,
    load_manifest,
    save_manifest,
    ManifestError,
    ManifestSecurityError,
)
from chdevflow.core.evidence import (
    execute_single_command,
    parse_and_validate_command,
    run_verification,
    safe_resolve_executable,
    sanitize_subprocess_env,
    VerificationSecurityError,
    MAX_OUTPUT_BYTES,
)
from chdevflow.core.init import run_init
from chdevflow.core.project import create_project
from chdevflow.core.tree import generate as generate_tree
from chdevflow.core.submit import validate_and_submit, SubmitError
from chdevflow.core.trust import (
    check_trust,
    compute_project_fingerprint,
    grant_trust,
    invalidate_trust,
    TRUST_FILE_REL,
    TrustIntegrityError,
    _extract_explicit_targets,
)


class TestVerifySecurityP04(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name).resolve()

        # Configura projeto mínimo C.H.
        run_init(self.root, apply=True)
        generate_tree(self.root)
        self.manifest_file = self.root / "chdevflow.yaml"
        self.manifest = create_manifest_data(self.root.name)
        self.manifest["verification"]["commands"] = ["echo 'validacao ok'"]
        save_manifest(self.manifest_file, self.manifest)

        # Configura Git básico em branch de fatia autorizada
        subprocess.run(["git", "-C", str(self.root), "init", "-b", "agy/teste-seguranca"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "tester@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "init"], check=True, capture_output=True)

        # Concede confiança inicial explícita
        grant_trust(self.root)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # TESTES POSITIVOS (TP-01 a TP-10)
    # -------------------------------------------------------------------------

    def test_tp01_simple_direct_command(self) -> None:
        """TP-01: Comando direto simples permitido pela allowlist executa sem shell."""
        res = execute_single_command("echo 'validacao ok'", cwd=self.root)
        self.assertEqual(res.state, "PASS")
        self.assertEqual(res.exit_code, 0)
        self.assertIn("validacao ok", res.stdout)

    def test_tp02_safe_ch_resolution(self) -> None:
        """TP-02: 'ch status --strict' resolve via sys.executable sem depender do PATH."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        tokens = parse_and_validate_command("ch status --strict", self.root, sanitized_path)
        self.assertEqual(tokens[0], sys.executable)
        self.assertEqual(tokens[1:4], ["-m", "chdevflow.cli", "status"])
        self.assertIn("--strict", tokens)

    def test_tp03_python_unittest_module(self) -> None:
        """TP-03: Python com módulo de teste unittest autorizado executa sem shell."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        tokens = parse_and_validate_command("python3 -m unittest", self.root, sanitized_path)
        self.assertIn("-m", tokens)
        self.assertIn("unittest", tokens)

    def test_tp04_python_internal_script(self) -> None:
        """TP-04: Python com script interno ao projeto permitido."""
        script = self.root / "tests" / "test_smoke.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        tokens = parse_and_validate_command("python3 tests/test_smoke.py", self.root, sanitized_path)
        self.assertTrue(Path(tokens[0]).is_file())
        self.assertEqual(tokens[1], "tests/test_smoke.py")

    def test_tp05_node_npm_allowed(self) -> None:
        """TP-05: Adaptadores Node/npm com subcomandos de teste e lifecycle scripts autorizados."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        echo_bin = shutil.which("echo") or "/bin/echo"
        with patch("shutil.which", return_value=echo_bin):
            tokens_test = parse_and_validate_command("npm test", self.root, sanitized_path)
            self.assertEqual(tokens_test[0], echo_bin)
            self.assertEqual(tokens_test[1:], ["test"])

            tokens_run = parse_and_validate_command("npm run test:ci", self.root, sanitized_path)
            self.assertEqual(tokens_run[0], echo_bin)
            self.assertEqual(tokens_run[1:], ["run", "test:ci"])

    def test_tp06_fail_fast_behavior(self) -> None:
        """TP-06: Fail-fast preservado: ao falhar primeiro comando, próximos são SKIPPED."""
        self.manifest["verification"]["commands"] = ["exit 1", "echo 'segundo'"]
        save_manifest(self.manifest_file, self.manifest)
        ev = run_verification(self.root, fail_fast=True, trust=True)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertEqual(len(ev.commands), 3)  # ch status --strict, exit 1, echo segundo
        # ch status --strict -> PASS
        self.assertEqual(ev.commands[0].state, "PASS")
        # exit 1 -> FAIL
        self.assertEqual(ev.commands[1].state, "FAIL")
        # echo segundo -> SKIPPED
        self.assertEqual(ev.commands[2].state, "SKIPPED")

    def test_tp07_dry_run_inspection(self) -> None:
        """TP-07: Inspecao via --dry-run valida comandos sem executar subprocessos."""
        self.manifest["verification"]["commands"] = ["echo 'ok'"]
        save_manifest(self.manifest_file, self.manifest)
        ev = run_verification(self.root, dry_run=True)
        self.assertEqual(ev.overall_state, "PASS")
        for cmd in ev.commands:
            self.assertEqual(cmd.state, "NOT_RUN")
            self.assertIn("Modo dry-run", cmd.stderr)

    def test_tp08_adapter_subcommands_allowed(self) -> None:
        """TP-08: Subcomandos de adaptadores permitidos (dotnet, cargo, go)."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        # /usr/bin/echo é um binário executável garantido no sistema Linux
        echo_bin = "/usr/bin/echo"
        with patch("shutil.which", return_value=echo_bin):
            tokens_dotnet = parse_and_validate_command("dotnet test", self.root, sanitized_path)
            self.assertEqual(tokens_dotnet[0], echo_bin)
            self.assertEqual(tokens_dotnet[1:], ["test"])

            tokens_cargo = parse_and_validate_command("cargo test", self.root, sanitized_path)
            self.assertEqual(tokens_cargo[0], echo_bin)
            self.assertEqual(tokens_cargo[1:], ["test"])

            tokens_go = parse_and_validate_command("go test", self.root, sanitized_path)
            self.assertEqual(tokens_go[0], echo_bin)
            self.assertEqual(tokens_go[1:], ["test"])

    def test_tp09_exit_simulation_pass(self) -> None:
        """TP-09: 'exit 0' traduz para código seguro em Python sem shell."""
        res = execute_single_command("exit 0", cwd=self.root)
        self.assertEqual(res.state, "PASS")
        self.assertEqual(res.exit_code, 0)

    def test_tp10_grant_trust_permissions_and_notice(self) -> None:
        """TP-10: grant_trust gera arquivo com 0600 e aviso de que não é sandbox de SO."""
        data = grant_trust(self.root)
        trust_file = self.root / TRUST_FILE_REL
        self.assertTrue(trust_file.is_file())
        self.assertIn("Não constitui sandbox de sistema operacional", data["notice"])
        if os.name == "posix":
            mode = stat.S_IMODE(trust_file.stat().st_mode)
            self.assertEqual(mode, 0o600)

    # -------------------------------------------------------------------------
    # TESTES NEGATIVOS: META-CARACTERES E INJEÇÃO DE SHELL (TN-01 a TN-05, TN-12)
    # -------------------------------------------------------------------------

    def test_tn01_shell_injection_semicolon(self) -> None:
        """TN-01: Ponto-e-vírgula rejeitado por operador de shell proibido."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("echo ok ; id", cwd=self.root)
        self.assertIn("Metacaractere de shell proibido ';'", str(ctx.exception))

    def test_tn02_shell_injection_double_ampersand(self) -> None:
        """TN-02: Operador '&&' rejeitado."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("echo ok && whoami", cwd=self.root)
        self.assertIn("Metacaractere de shell proibido '&&'", str(ctx.exception))

    def test_tn03_shell_injection_pipe(self) -> None:
        """TN-03: Operador pipe '|' rejeitado."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("echo dado | cat", cwd=self.root)
        self.assertIn("Metacaractere de shell proibido '|'", str(ctx.exception))

    def test_tn04_command_substitution(self) -> None:
        """TN-04: Expansão de comando $() e crases rejeitadas."""
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("echo $(uname -a)", cwd=self.root)
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("echo `uname -a`", cwd=self.root)

    def test_tn05_redirection_operators(self) -> None:
        """TN-05: Redirecionamentos '>' e '<' rejeitados."""
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("echo evil > output.txt", cwd=self.root)
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("cat < input.txt", cwd=self.root)

    def test_tn12_injection_in_ch_prefix(self) -> None:
        """TN-12: Metacaracteres em comando 'ch' bloqueados."""
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("ch status && echo hacked", cwd=self.root)

    # -------------------------------------------------------------------------
    # TESTES NEGATIVOS: BINÁRIOS, ARGUMENTOS E SUBCOMANDOS (TN-06 a TN-11, TN-13)
    # -------------------------------------------------------------------------

    def test_tn06_python_c_flag_forbidden(self) -> None:
        """TN-06: Flag '-c' proibida em invocação Python."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("python3 -c 'print(1)'", cwd=self.root)
        self.assertIn("Flag proibida", str(ctx.exception))

    def test_tn07_python_interactive_flags_forbidden(self) -> None:
        """TN-07: Flags '-i' e '-e' proibidas em Python."""
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("python3 -i tests/t.py", cwd=self.root)
        with self.assertRaises(VerificationSecurityError):
            execute_single_command("python3 -e tests/t.py", cwd=self.root)

    def test_tn08_python_dangerous_module_forbidden(self) -> None:
        """TN-08: Módulos arbitrários (ex: http.server) proibidos."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("python3 -m http.server 8080", cwd=self.root)
        self.assertIn("Módulo Python não autorizado: 'http.server'", str(ctx.exception))

    def test_tn09_path_traversal_in_script(self) -> None:
        """TN-09: Tentativa de path traversal em script Python bloqueada."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("python3 ../../outside.py", cwd=self.root)
        self.assertIn("Path traversal detectado", str(ctx.exception))

    def test_tn10_absolute_script_outside_root(self) -> None:
        """TN-10: Caminho absoluto fora da raiz do projeto bloqueado."""
        with self.assertRaises(VerificationSecurityError) as ctx:
            execute_single_command("python3 /tmp/malicious.py", cwd=self.root)
        self.assertIn("Caminho absoluto de script não permitido", str(ctx.exception))

    def test_tn11_unauthorized_npm_subcommand_and_lifecycle(self) -> None:
        """TN-11: Subcomando npm não autorizado ('install') e scripts perigosos bloqueados."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        with patch("shutil.which", return_value="/usr/bin/echo"):
            with self.assertRaises(VerificationSecurityError) as ctx1:
                parse_and_validate_command("npm install", self.root, sanitized_path)
            self.assertIn("Subcomando 'install' não autorizado", str(ctx1.exception))

            with self.assertRaises(VerificationSecurityError) as ctx2:
                parse_and_validate_command("npm run publish", self.root, sanitized_path)
            self.assertIn("Comando remoto mutável proibido", str(ctx2.exception))

            with self.assertRaises(VerificationSecurityError) as ctx3:
                parse_and_validate_command("npm run deploy", self.root, sanitized_path)
            self.assertIn("Script de ciclo de vida 'deploy' não autorizado", str(ctx3.exception))

    def test_tn13_forbidden_system_binaries(self) -> None:
        """TN-13: Executáveis de sistema fora da allowlist (rm, curl, wget, gh) bloqueados."""
        for bad_cmd in ["rm -rf .", "curl http://example.com", "wget http://example.com", "gh auth status"]:
            with self.assertRaises(VerificationSecurityError):
                execute_single_command(bad_cmd, cwd=self.root)

    # -------------------------------------------------------------------------
    # TESTES NEGATIVOS: SANITIZAÇÃO DE AMBIENTE E PATH (TN-14, TN-21 a TN-24)
    # -------------------------------------------------------------------------

    def test_tn14_env_sanitization_removes_secrets(self) -> None:
        """TN-14: Variáveis sensíveis e credenciais são expurgadas compulsoriamente."""
        dirty_env = {
            "PATH": "/usr/bin:/bin",
            "GITHUB_TOKEN": "ghp_supersecrettoken123",
            "AWS_SECRET_ACCESS_KEY": "AKIASECRET123",
            "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
            "USER": "tester",
        }
        clean = sanitize_subprocess_env(dirty_env, self.root)
        self.assertNotIn("GITHUB_TOKEN", clean)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", clean)
        self.assertNotIn("DATABASE_URL", clean)
        self.assertEqual(clean.get("USER"), "tester")

    def test_tn21_relative_path_entry_stripped(self) -> None:
        """TN-21: Entradas relativas em PATH (. ou ./bin) rejeitadas antes de canonicalização."""
        dirty_env = {"PATH": ".:bin:../bin:/usr/bin"}
        clean = sanitize_subprocess_env(dirty_env, self.root)
        path_parts = clean["PATH"].split(os.pathsep)
        self.assertNotIn(".", path_parts)
        self.assertNotIn("bin", path_parts)
        self.assertNotIn("../bin", path_parts)
        self.assertIn("/usr/bin", path_parts)

    def test_tn22_world_writable_path_directory_rejected(self) -> None:
        """TN-22: Diretório world-writable em PATH (st_mode & 0o002) é expurgado."""
        writable_dir = Path(tempfile.mkdtemp(prefix="ch_ww_"))
        try:
            os.chmod(writable_dir, 0o777)
            dirty_env = {"PATH": f"{writable_dir}:/usr/bin"}
            clean = sanitize_subprocess_env(dirty_env, self.root)
            self.assertNotIn(str(writable_dir), clean["PATH"].split(os.pathsep))
        finally:
            os.rmdir(writable_dir)

    def test_tn23_path_entry_inside_project_root_rejected(self) -> None:
        """TN-23: Diretório de PATH apontando para dentro do projeto é expurgado (anti-hijacking)."""
        local_bin = self.root / "local_bin"
        local_bin.mkdir()
        dirty_env = {"PATH": f"{local_bin}:/usr/bin"}
        clean = sanitize_subprocess_env(dirty_env, self.root)
        self.assertNotIn(str(local_bin), clean["PATH"].split(os.pathsep))

    def test_tn24_fake_ch_executable_in_path_ignored(self) -> None:
        """TN-24: Executável falso com nome 'ch' é ignorado em favor de sys.executable."""
        fake_bin_dir = Path(tempfile.mkdtemp(prefix="fake_bin_"))
        try:
            fake_ch = fake_bin_dir / "ch"
            fake_ch.write_text("#!/bin/sh\necho 'fake'\n", encoding="utf-8")
            fake_ch.chmod(0o755)
            # Ao resolver 'ch', safe_resolve_executable sempre retorna sys.executable
            res = safe_resolve_executable("ch", f"{fake_bin_dir}:/usr/bin", self.root)
            self.assertEqual(res, sys.executable)
        finally:
            if (fake_bin_dir / "ch").exists():
                (fake_bin_dir / "ch").unlink()
            os.rmdir(fake_bin_dir)

    # -------------------------------------------------------------------------
    # TESTES NEGATIVOS: PROCESSO, STREAMING LIMITADO E TIMEOUT (TN-15, TN-28)
    # -------------------------------------------------------------------------

    def test_tn15_timeout_two_stage_process_group_termination(self) -> None:
        """TN-15: Timeout em dois estágios encerra processo em loop sem zumbis."""
        cmd = "python3 -c 'import time; time.sleep(10)'"
        # Executa com timeout de 0.5s via script Python interno
        script = self.root / "tests" / "hang.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("import time\nwhile True:\n    time.sleep(0.1)\n", encoding="utf-8")
        res = execute_single_command("python3 tests/hang.py", cwd=self.root, timeout=0.5)
        self.assertEqual(res.state, "TIMEOUT")
        self.assertEqual(res.exit_code, -1)
        self.assertIn("Timeout excedido", res.stderr)

    def test_tn28_bounded_stream_memory_output_5mb(self) -> None:
        """TN-28: Processo gerando > 5 MB de saída trunca leitura sem consumo ilimitado."""
        script = self.root / "tests" / "big_output.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        # Gera ~6 MB de texto
        script.write_text(
            "import sys\nfor _ in range(70):\n    sys.stdout.write('A' * 100000 + '\\n')\n",
            encoding="utf-8"
        )
        res = execute_single_command("python3 tests/big_output.py", cwd=self.root)
        self.assertEqual(res.state, "PASS")
        self.assertIn("AVISO DE SEGURANÇA: Saída stdout truncada ao atingir o teto de 5 MB", res.stdout)
        # Verifica que o tamanho capturado não excede significativamente o teto (5MB + aviso)
        self.assertLessEqual(len(res.stdout.encode("utf-8")), MAX_OUTPUT_BYTES + 4096)

    # -------------------------------------------------------------------------
    # TESTES NEGATIVOS: MANIFESTO FAIL-CLOSED (TN-16 a TN-19, TN-29)
    # -------------------------------------------------------------------------

    def test_tn16_manifest_yaml_syntax_error_fail_closed(self) -> None:
        """TN-16: Manifesto com erro de sintaxe YAML falha fechado imediatamente."""
        self.manifest_file.write_text("verification:\n  commands: [broken yaml: : :", encoding="utf-8")
        ev = run_verification(self.root)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertEqual(ev.commands[0].state, "FAIL")
        self.assertIn("Falha de validação do manifesto (fail-closed)", ev.commands[0].stderr)

    def test_tn17_manifest_commands_not_a_list(self) -> None:
        """TN-17: 'commands' não sendo lista rejeita manifesto com erro estrito."""
        self.manifest_file.write_text(
            "schema_version: '1.0'\nproject:\n  name: Test\nverification:\n  commands: 'echo ok'\n",
            encoding="utf-8"
        )
        ev = run_verification(self.root)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertIn("deve ser uma lista", ev.commands[0].stderr)

    def test_tn18_manifest_commands_non_string_item(self) -> None:
        """TN-18: Item não-string na lista de comandos rejeita manifesto."""
        self.manifest_file.write_text(
            "schema_version: '1.0'\nproject:\n  name: Test\nverification:\n  commands:\n    - 123\n",
            encoding="utf-8"
        )
        ev = run_verification(self.root)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertIn("deve ser uma string", ev.commands[0].stderr)

    def test_tn19_manifest_empty_or_whitespace_command(self) -> None:
        """TN-19: Comando vazio ou somente whitespace rejeita manifesto."""
        self.manifest_file.write_text(
            "schema_version: '1.0'\nproject:\n  name: Test\nverification:\n  commands:\n    - '   '\n",
            encoding="utf-8"
        )
        ev = run_verification(self.root)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertIn("não pode ser vazio", ev.commands[0].stderr)

    def test_tn29_manifest_secrets_distinct_security_error(self) -> None:
        """TN-29: Detecção de segredos em manifesto gera ManifestSecurityError distinto de schema."""
        self.manifest_file.write_text(
            "schema_version: '1.0'\nproject:\n  name: Test\napi_key: 'ghp_secretkey12345'\n",
            encoding="utf-8"
        )
        with self.assertRaises(ManifestSecurityError):
            load_manifest(self.manifest_file)

    # -------------------------------------------------------------------------
    # TESTES NEGATIVOS: POLÍTICA DE CONFIANÇA E SUBMIT (TN-20, TN-25 a TN-27, TN-30)
    # -------------------------------------------------------------------------

    def test_tn20_submit_blocks_on_disallowed_command(self) -> None:
        """TN-20: 'ch submit' bloqueia submissão e não realiza push/PR em caso de falha de segurança."""
        self.manifest["verification"]["commands"] = ["rm -rf ."]
        save_manifest(self.manifest_file, self.manifest)
        with self.assertRaises(SubmitError) as ctx:
            validate_and_submit(self.root)
        self.assertIn("Operação bloqueada", str(ctx.exception))

    def test_tn25_trust_invalidated_when_code_modified_or_untracked(self) -> None:
        """TN-25: Alterações em arquivos de código com HEAD inalterado invalidam trust."""
        is_ok_before, _ = check_trust(self.root)
        self.assertTrue(is_ok_before)

        # Adiciona novo arquivo de código não rastreado
        evil_code = self.root / "src" / "new_module.py"
        evil_code.parent.mkdir(parents=True, exist_ok=True)
        evil_code.write_text("print('novo codigo')\n", encoding="utf-8")

        is_ok_after, reason = check_trust(self.root)
        self.assertFalse(is_ok_after)
        self.assertIn("Confiança invalidada", reason)

    def test_tn26_trust_registry_tampering_fails_closed(self) -> None:
        """TN-26: Adulteração direta de .ch/trust.json falha fechado."""
        trust_file = self.root / TRUST_FILE_REL
        trust_file.write_text("invalid json content {{{", encoding="utf-8")
        is_ok, reason = check_trust(self.root)
        self.assertFalse(is_ok)
        self.assertIn("corrompido ou ilegível", reason)

        # Registro com fingerprint adulterado
        data = {"trust_version": "1", "fingerprint": "bad_sha_hash"}
        trust_file.write_text(json.dumps(data), encoding="utf-8")
        is_ok2, reason2 = check_trust(self.root)
        self.assertFalse(is_ok2)
        self.assertIn("Confiança invalidada", reason2)

    def test_tn27_submit_does_not_auto_grant_trust(self) -> None:
        """TN-27: 'ch submit' nunca concede confiança automaticamente; requer aprovação prévia."""
        # Remove trust
        invalidate_trust(self.root)
        self.manifest["verification"]["commands"] = ["echo 'teste'"]
        save_manifest(self.manifest_file, self.manifest)

        with self.assertRaises(SubmitError):
            validate_and_submit(self.root)

    def test_tn30_trust_declaration_explicit_non_sandbox(self) -> None:
        """TN-30: Manifestação de trust explicita não ser sandbox de sistema operacional."""
        trust_data = grant_trust(self.root, declaration="operador_humano_teste")
        self.assertIn("operador_humano_teste", trust_data["declaration"])
        self.assertIn("Não constitui sandbox de sistema operacional", trust_data["notice"])

    # -------------------------------------------------------------------------
    # REGRESSÕES ESPECÍFICAS DA REAUDITORIA INDEPENDENTE R1 (P0-01, P0-02, P0-03)
    # -------------------------------------------------------------------------

    def test_p0_01_save_manifest_and_create_project_never_grant_auto_trust(self) -> None:
        """P0-01: save_manifest e create_project não concedem aprovação/trust implícita."""
        # 1. save_manifest não cria trust.json
        invalidate_trust(self.root)
        self.assertFalse((self.root / TRUST_FILE_REL).exists())
        self.manifest["verification"]["commands"] = ["echo 'novo comando'"]
        save_manifest(self.manifest_file, self.manifest)
        self.assertFalse(
            (self.root / TRUST_FILE_REL).exists(),
            "save_manifest() não deve gravar .ch/trust.json nem manifestar auto-trust.",
        )
        is_ok, reason = check_trust(self.root)
        self.assertFalse(is_ok)
        self.assertIn("Registro de confiança ausente", reason)

        # 2. create_project não cria trust.json
        new_proj_dir = self.root / "sub_new_proj"
        create_project("sub_new_proj", base_dir=self.root)
        self.assertTrue(new_proj_dir.is_dir())
        self.assertFalse(
            (new_proj_dir / TRUST_FILE_REL).exists(),
            "create_project() deve gerar arquivos sem manifestar aprovação ou auto-trust.",
        )
        is_ok_proj, reason_proj = check_trust(new_proj_dir)
        self.assertFalse(is_ok_proj)
        self.assertIn("Registro de confiança ausente", reason_proj)

    def test_p0_02_regression_successive_modifications_with_same_git_status_invalidates_trust(self) -> None:
        """P0-02 (Regressão obrigatória): Conceder trust após 1ª modificação de core.py,

        modificar novamente com mesmo status Git e demonstrar invalidação de confiança.
        """
        core_file = self.root / "core.py"
        # Cria e commita estado base inicial
        core_file.write_text("print('base')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "core.py"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "add core.py"], check=True, capture_output=True)

        # 1ª Modificação não commitada (status: M core.py)
        core_file.write_text("print('modificacao_v1')\n", encoding="utf-8")
        proc_status1 = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("M core.py", proc_status1.stdout)

        # Concede confiança vinculada à modificação v1
        grant_trust(self.root, declaration="trust_v1")
        is_ok_v1, _ = check_trust(self.root)
        self.assertTrue(is_ok_v1, "Trust deve ser válido para a versão v1 concedida.")

        # 2ª Modificação sucessiva (status Git permanece idêntico: M core.py)
        core_file.write_text("print('modificacao_v2_payload_adulterado')\n", encoding="utf-8")
        proc_status2 = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain=v1"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Status do Git continua sendo ' M core.py'
        self.assertIn("M core.py", proc_status2.stdout)

        # Validação obrigatória: a confiança DEVE ser invalidada pelo hash de conteúdo
        is_ok_v2, reason_v2 = check_trust(self.root)
        self.assertFalse(
            is_ok_v2,
            "Confiança DEVE ser invalidada em modificações sucessivas com mesmo status Git.",
        )
        self.assertIn("Confiança invalidada", reason_v2)

    def test_p0_02_fail_closed_on_unreadable_file(self) -> None:
        """P0-02: Erro ao calcular integridade de arquivo falha fechado."""
        with patch("chdevflow.core.trust._hash_file", return_value=""):
            is_ok, reason = check_trust(self.root)
            self.assertFalse(is_ok)
            self.assertIn("fail-closed", reason)

    def test_p0_03_timeout_kills_persisting_child_when_parent_terminates_early(self) -> None:
        """P0-03: Processo pai que termina antes da carência não deixa filho persistente vivo."""
        if os.name != "posix":
            self.skipTest("Teste de isolamento de processo POSIX (killpg)")

        pid_file = self.root / "child_running.pid"
        script = self.root / "tests" / "parent_exit_early.py"
        script.parent.mkdir(parents=True, exist_ok=True)

        # Script pai cria filho que ignora SIGTERM e dorme 100s.
        # Ao receber SIGTERM, o pai encerra imediatamente (sys.exit(0)), antes da carência de 2.0s.
        code = f'''import subprocess, sys, time, signal, os
from pathlib import Path

child_code = """import signal, time, os
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path('{pid_file}').write_text(str(os.getpid()))
time.sleep(100)
"""
p = subprocess.Popen([sys.executable, '-c', child_code])
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
time.sleep(100)
'''
        script.write_text(code, encoding="utf-8")

        # Executa com timeout curto (0.4s)
        res = execute_single_command("python3 tests/parent_exit_early.py", cwd=self.root, timeout=0.4)
        self.assertEqual(res.state, "TIMEOUT")
        self.assertEqual(res.exit_code, -1)

        # Verifica se o PID do filho foi registrado
        self.assertTrue(pid_file.is_file(), "Filho deveria ter gravado seu PID.")
        child_pid = int(pid_file.read_text().strip())

        # Verifica que o filho foi encerrado pelo SIGKILL disparado ao grupo após a carência
        time.sleep(0.1)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    # -------------------------------------------------------------------------
    # TESTES DE REGRESSÃO OBRIGATÓRIOS DO CICLO R2 (AUD-GERAL-P0-04)
    # -------------------------------------------------------------------------

    def test_r2_01_no_shadowing_of_chdevflow_package_by_local_package(self) -> None:
        """R2-01: Pacote chdevflow local na raiz ou em src/ não é executado antes do gate de trust."""
        # Cria pacote sombra local na raiz e em src/
        sentinel_root = self.root / "shadow_root.sentinel"
        sentinel_src = self.root / "shadow_src.sentinel"

        pkg_root = self.root / "chdevflow"
        pkg_root.mkdir(parents=True, exist_ok=True)
        (pkg_root / "__init__.py").write_text(f"from pathlib import Path\nPath(r'{sentinel_root}').write_text('SHADOW_ROOT')\n", encoding="utf-8")
        (pkg_root / "cli.py").write_text(f"from pathlib import Path\nPath(r'{sentinel_root}').write_text('SHADOW_ROOT_CLI')\n", encoding="utf-8")

        pkg_src = self.root / "src" / "chdevflow"
        pkg_src.mkdir(parents=True, exist_ok=True)
        (pkg_src / "__init__.py").write_text(f"from pathlib import Path\nPath(r'{sentinel_src}').write_text('SHADOW_SRC')\n", encoding="utf-8")
        (pkg_src / "cli.py").write_text(f"from pathlib import Path\nPath(r'{sentinel_src}').write_text('SHADOW_SRC_CLI')\n", encoding="utf-8")

        # Manifesto com comando de verificação interno ch status --strict e comando de projeto
        self.manifest["verification"]["commands"] = ["ch status --strict", "python3 -m unittest"]
        save_manifest(self.manifest_file, self.manifest)

        # Executa sem trust prévio (trust=False)
        ev = run_verification(self.root, persist=False, trust=False)

        # O comando interno ch status --strict deve rodar in-process sem importar o pacote sombra local
        self.assertFalse(sentinel_root.exists(), "Pacote sombra na raiz não deve ser importado.")
        self.assertFalse(sentinel_src.exists(), "Pacote sombra em src/ não deve ser importado.")

        # O comando de projeto deve ser bloqueado pela política de confiança
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertEqual(len(ev.commands), 2)
        self.assertEqual(ev.commands[1].state, "FAIL")
        self.assertEqual(ev.commands[1].exit_code, -4)
        self.assertIn("bloqueada pela política de confiança", ev.commands[1].stderr)

    def test_r2_01_no_shadowing_by_single_module_chdevflow_py(self) -> None:
        """R2-01: Módulo único chdevflow.py na raiz do target não é importado."""
        sentinel = self.root / "shadow_single.sentinel"
        (self.root / "chdevflow.py").write_text(
            f"from pathlib import Path\nPath(r'{sentinel}').write_text('SHADOW_MODULE')\n",
            encoding="utf-8",
        )
        res = execute_single_command("ch status --strict", cwd=self.root)
        self.assertFalse(sentinel.exists(), "Módulo chdevflow.py local não deve ser executado.")
        self.assertIn(res.state, ("PASS", "FAIL"))

    def test_r2_02_modification_in_docs_probe_py_invalidates_trust(self) -> None:
        """R2-02: Adulteração de script Python em docs/ altera fingerprint e invalida trust."""
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        probe_script = docs_dir / "probe.py"
        probe_script.write_text("print('probe_v1')\n", encoding="utf-8")

        # Concede trust
        grant_trust(self.root, declaration="trust_docs_probe")
        is_ok_v1, _ = check_trust(self.root)
        self.assertTrue(is_ok_v1, "Trust deve ser válido na versão inicial.")

        # Modifica o script sob docs/
        probe_script.write_text("print('probe_v2_payload_modificado')\n", encoding="utf-8")
        is_ok_v2, reason_v2 = check_trust(self.root)
        self.assertFalse(is_ok_v2, "Modificação em docs/probe.py DEVE invalidar a confiança.")
        self.assertIn("Confiança invalidada", reason_v2)

    def test_r2_02_script_with_text_extension_and_without_extension_invalids_trust(self) -> None:
        """R2-02: Script regular sem extensão ou com extensão .txt em docs/ invalida trust ao ser modificado."""
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        probe_txt = docs_dir / "probe.txt"
        probe_no_ext = docs_dir / "probe_runner"

        probe_txt.write_text("print('txt_v1')\n", encoding="utf-8")
        probe_no_ext.write_text("print('no_ext_v1')\n", encoding="utf-8")

        self.manifest["verification"]["commands"] = ["python3 docs/probe.txt", "python3 docs/probe_runner"]
        save_manifest(self.manifest_file, self.manifest)

        grant_trust(self.root, declaration="trust_probes")
        self.assertTrue(check_trust(self.root)[0])

        # Modifica docs/probe.txt
        probe_txt.write_text("print('txt_v2_mod')\n", encoding="utf-8")
        is_ok_txt, reason_txt = check_trust(self.root)
        self.assertFalse(is_ok_txt, "Modificação em docs/probe.txt DEVE invalidar trust.")
        self.assertIn("Confiança invalidada", reason_txt)

        # Re-concede e modifica docs/probe_runner (sem extensão)
        grant_trust(self.root, declaration="trust_regranted")
        self.assertTrue(check_trust(self.root)[0])
        probe_no_ext.write_text("print('no_ext_v2_mod')\n", encoding="utf-8")
        is_ok_noext, reason_noext = check_trust(self.root)
        self.assertFalse(is_ok_noext, "Modificação em script sem extensão DEVE invalidar trust.")
        self.assertIn("Confiança invalidada", reason_noext)

    def test_r2_02_evidence_persistence_under_dot_ch_does_not_invalidate_trust(self) -> None:
        """R2-02: Relatórios de evidência gerados em .ch/evidence/ não invalidam trust do projeto."""
        grant_trust(self.root, declaration="trust_clean")
        self.assertTrue(check_trust(self.root)[0])

        # Executa verificação com persistência de evidência
        ev = run_verification(self.root, persist=True, trust=False)
        self.assertTrue(Path(ev.evidence_file).is_file())

        # O trust deve permanecer íntegro (evidência sob .ch/ não se auto-invalida)
        is_ok, reason = check_trust(self.root)
        self.assertTrue(is_ok, f"Persistência em .ch/evidence/ não deve invalidar trust: {reason}")

    def test_r2_02_non_git_workspace_detects_changes(self) -> None:
        """R2-02: Projeto fora do Git calcula fingerprint conservador sobre arquivos do workspace."""
        non_git_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(non_git_tmp.cleanup)
        non_git_root = Path(non_git_tmp.name).resolve()
        create_project("nongit_test", non_git_root, "python")
        non_git_proj = non_git_root / "nongit_test"

        fp1, _ = compute_project_fingerprint(non_git_proj)
        grant_trust(non_git_proj, declaration="trust_nongit")
        self.assertTrue(check_trust(non_git_proj)[0])

        # Adiciona/modifica arquivo de script no workspace sem Git
        scripts_dir = non_git_proj / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "probe.py").write_text("print('Modificado no non-git')\n", encoding="utf-8")
        fp2, _ = compute_project_fingerprint(non_git_proj)
        self.assertNotEqual(fp1, fp2, "Fingerprint fora do Git deve mudar com alteração de arquivo.")
        is_ok, reason = check_trust(non_git_proj)
        self.assertFalse(is_ok)
        self.assertIn("Confiança invalidada", reason)

    def test_r2_03_compact_forbidden_flags_rejected(self) -> None:
        """R2-03: Formas compactas de flags proibidas (-cprint(42), -e..., -i...) são rejeitadas."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        bad_commands = [
            "python3 -cprint(42)",
            "python3 -c'import os'",
            "python3 -e'some_expr'",
            "python3 -i tests/test_smoke.py",
            "python3 -c 'print(42)'",
            "python3 -u -c 'print(42)'",
            "python3 -uc",
        ]
        for cmd in bad_commands:
            with self.assertRaises(VerificationSecurityError, msg=f"Deveria rejeitar: {cmd}") as ctx:
                parse_and_validate_command(cmd, self.root, sanitized_path)
            self.assertIn("Flag proibida em comando Python", str(ctx.exception))

    def test_r2_03_stdin_execution_rejected(self) -> None:
        """R2-03: Execução de Python via stdin ('python3 -') é rejeitada fail-closed."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        with self.assertRaises(VerificationSecurityError) as ctx:
            parse_and_validate_command("python3 -", self.root, sanitized_path)
        self.assertIn("stdin", str(ctx.exception))

    def test_r2_03_nonexistent_script_or_directory_target_rejected(self) -> None:
        """R2-03: Script inexistente ou alvo que é diretório são rejeitados."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")
        with self.assertRaises(VerificationSecurityError) as ctx1:
            parse_and_validate_command("python3 nonexistent_script.py", self.root, sanitized_path)
        self.assertIn("Script Python não encontrado", str(ctx1.exception))

        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(VerificationSecurityError) as ctx2:
            parse_and_validate_command("python3 docs", self.root, sanitized_path)
        self.assertIn("arquivo regular", str(ctx2.exception))

    def test_r2_03_allowed_options_before_module_and_script(self) -> None:
        """R2-03: Opções seguras do interpretador (-u, -B, etc.) antes de módulo ou script são aceitas."""
        sanitized_path = sanitize_subprocess_env(None, self.root).get("PATH", "")

        # Opções antes de -m
        tokens_mod = parse_and_validate_command("python3 -u -B -m unittest discover -v -k test_smoke", self.root, sanitized_path)
        self.assertIn("-m", tokens_mod)
        self.assertIn("unittest", tokens_mod)
        self.assertIn("-v", tokens_mod)

        # Opções antes de script regular existente
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        probe = scripts_dir / "probe.py"
        probe.write_text("print('ok')\n", encoding="utf-8")

        tokens_script = parse_and_validate_command("python3 -u -B scripts/probe.py --custom-flag -c-arg", self.root, sanitized_path)
        self.assertIn("scripts/probe.py", tokens_script)
        self.assertIn("--custom-flag", tokens_script)
        self.assertIn("-c-arg", tokens_script)

    def test_r3_01_non_git_workspace_dot_ch_runner_invalidates_trust(self) -> None:
        """R3-01: Alvo aceito em pasta .ch/ (.ch/runner.py) em workspace sem Git invalida trust ao ser alterado."""
        non_git_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(non_git_tmp.cleanup)
        non_git_root = Path(non_git_tmp.name).resolve()
        create_project("nongit_test", non_git_root, "python")
        non_git_proj = non_git_root / "nongit_test"

        ch_dir = non_git_proj / ".ch"
        ch_dir.mkdir(parents=True, exist_ok=True)
        runner_py = ch_dir / "runner.py"
        runner_py.write_text("print('runner v1')\n", encoding="utf-8")

        # Configura manifesto apontando para o runner sob .ch/
        m_path = non_git_proj / "chdevflow.yaml"
        m_data = load_manifest(m_path)
        m_data["verification"]["commands"] = ["python3 .ch/runner.py"]
        save_manifest(m_path, m_data)

        grant_trust(non_git_proj, declaration="trust_dot_ch_runner")
        self.assertTrue(check_trust(non_git_proj)[0])

        # Edita texto inofensivo do runner v1 -> v2
        runner_py.write_text("print('runner v2 modificado')\n", encoding="utf-8")
        is_ok, reason = check_trust(non_git_proj)
        self.assertFalse(is_ok, "Alteração em .ch/runner.py deve invalidar trust")
        self.assertIn("Confiança invalidada", reason)

    def test_r3_01_git_repo_ignored_build_probe_invalidates_trust(self) -> None:
        """R3-01: Alvo em diretório ignorado pelo Git (build/probe.py) invalida trust ao ser alterado."""
        build_dir = self.root / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        probe_py = build_dir / "probe.py"
        probe_py.write_text("print('build probe v1')\n", encoding="utf-8")

        # Adiciona build/ ao .gitignore
        gitignore = self.root / ".gitignore"
        gitignore.write_text(".ch/\nbuild/\n", encoding="utf-8")

        m_path = self.root / "chdevflow.yaml"
        m_data = load_manifest(m_path)
        m_data["verification"]["commands"] = ["python3 build/probe.py"]
        save_manifest(m_path, m_data)

        # Commita apenas chdevflow.yaml e .gitignore (build/probe.py permanece untracked e ignorado)
        subprocess.run(["git", "-C", str(self.root), "add", "chdevflow.yaml", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "add build runner"], check=True)

        grant_trust(self.root, declaration="trust_ignored_build")
        self.assertTrue(check_trust(self.root)[0])

        # Modifica build/probe.py v1 -> v2
        probe_py.write_text("print('build probe v2 modificado')\n", encoding="utf-8")
        is_ok, reason = check_trust(self.root)
        self.assertFalse(is_ok, "Alteração em arquivo ignorado do runner deve invalidar trust")
        self.assertIn("Confiança invalidada", reason)

    def test_r3_01_git_repo_symlink_target_change_invalidates_trust(self) -> None:
        """R3-01: Alvo que é symlink interno (docs/entry.md -> body.txt) invalida trust ao alterar o arquivo apontado."""
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        body_txt = docs_dir / "body.txt"
        body_txt.write_text("print('body v1')\n", encoding="utf-8")

        entry_sym = docs_dir / "entry.md"
        if entry_sym.exists() or entry_sym.is_symlink():
            entry_sym.unlink()
        entry_sym.symlink_to("body.txt")

        m_path = self.root / "chdevflow.yaml"
        m_data = load_manifest(m_path)
        m_data["verification"]["commands"] = ["python3 docs/entry.md"]
        save_manifest(m_path, m_data)

        subprocess.run(["git", "-C", str(self.root), "add", "chdevflow.yaml", "docs/body.txt", "docs/entry.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "add symlink runner"], check=True)

        grant_trust(self.root, declaration="trust_symlink_target")
        self.assertTrue(check_trust(self.root)[0])

        # Altera somente o arquivo físico body.txt (symlink e commit permanecem intocados)
        body_txt.write_text("print('body v2 modificado')\n", encoding="utf-8")
        is_ok, reason = check_trust(self.root)
        self.assertFalse(is_ok, "Alteração no destino físico do symlink deve invalidar trust")
        self.assertIn("Confiança invalidada", reason)

    def test_r3_01_symlink_repointing_destination_invalidates_trust(self) -> None:
        """R3-01: Reapontamento de symlink para outro arquivo regular invalida trust."""
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        body1 = docs_dir / "body1.txt"
        body1.write_text("print('body 1')\n", encoding="utf-8")
        body2 = docs_dir / "body2.txt"
        body2.write_text("print('body 2')\n", encoding="utf-8")

        entry_sym = docs_dir / "runner_sym.py"
        if entry_sym.exists() or entry_sym.is_symlink():
            entry_sym.unlink()
        entry_sym.symlink_to("body1.txt")

        m_path = self.root / "chdevflow.yaml"
        m_data = load_manifest(m_path)
        m_data["verification"]["commands"] = ["python3 docs/runner_sym.py"]
        save_manifest(m_path, m_data)

        grant_trust(self.root, declaration="trust_sym_repoint")
        self.assertTrue(check_trust(self.root)[0])

        # Reaponta o symlink para body2.txt
        entry_sym.unlink()
        entry_sym.symlink_to("body2.txt")
        is_ok, reason = check_trust(self.root)
        self.assertFalse(is_ok, "Reapontar symlink deve invalidar trust")
        self.assertIn("Confiança invalidada", reason)

    def test_r3_01_symlink_broken_or_outside_fails_closed(self) -> None:
        """R3-01: Symlink quebrado ou apontando para fora do projeto falha fechado."""
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        broken_sym = docs_dir / "broken.py"
        if broken_sym.exists() or broken_sym.is_symlink():
            broken_sym.unlink()
        broken_sym.symlink_to("nonexistent.py")

        m_path = self.root / "chdevflow.yaml"
        m_data = load_manifest(m_path)
        m_data["verification"]["commands"] = ["python3 docs/broken.py"]
        save_manifest(m_path, m_data)

        # compute_project_fingerprint deve disparar TrustIntegrityError
        with self.assertRaises(TrustIntegrityError) as ctx:
            compute_project_fingerprint(self.root)
        self.assertIn("quebrado", str(ctx.exception).lower())

    def test_r4_01_casing_variants_of_python_extract_targets_and_invalidate_trust(self) -> None:
        """R4-01: Variantes de capitalização de python/python3 (Python3, PYTHON3, etc.) extraem alvos e invalidam trust."""
        variants = ["python3", "Python3", "PYTHON3", "python", "Python", "PYTHON", "PyThOn3"]
        for bin_variant in variants:
            with self.subTest(binary=bin_variant):
                tmp_dir = tempfile.TemporaryDirectory()
                self.addCleanup(tmp_dir.cleanup)
                proj_root = Path(tmp_dir.name).resolve()
                create_project("case_test", proj_root, "python")
                work_dir = proj_root / "case_test"

                # Cria repositório git e adiciona arquivo em docs/probe.txt
                subprocess.run(["git", "-C", str(work_dir), "init", "-b", "main"], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(work_dir), "config", "user.name", "Tester"], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(work_dir), "config", "user.email", "tester@example.com"], check=True, capture_output=True)
                docs_dir = work_dir / "docs"
                docs_dir.mkdir(parents=True, exist_ok=True)
                probe_txt = docs_dir / "probe.txt"
                probe_txt.write_text("print('probe v1')\n", encoding="utf-8")

                m_path = work_dir / "chdevflow.yaml"
                m_data = load_manifest(m_path)
                m_data["verification"]["commands"] = [f"{bin_variant} docs/probe.txt"]
                save_manifest(m_path, m_data)

                # Verifica que _extract_explicit_targets reconhece o alvo com a variante de casing
                targets = _extract_explicit_targets(work_dir)
                self.assertIn("docs/probe.txt", targets, f"Deveria extrair 'docs/probe.txt' para variante {bin_variant}")

                subprocess.run(["git", "-C", str(work_dir), "add", "."], check=True, capture_output=True)
                subprocess.run(["git", "-C", str(work_dir), "commit", "-m", "init"], check=True, capture_output=True)

                grant_trust(work_dir, declaration=f"trust_{bin_variant}")
                self.assertTrue(check_trust(work_dir)[0])

                # Edita o arquivo do script v1 -> v2
                probe_txt.write_text("print('probe v2 modificado')\n", encoding="utf-8")
                is_ok, reason = check_trust(work_dir)
                self.assertFalse(is_ok, f"Alteração do script deve invalidar trust para variante {bin_variant}")
                self.assertIn("Confiança invalidada", reason)

    def test_tn_51_unicode_accented_paths_and_successive_modifications_invalidate_trust(self) -> None:
        """TN-51 (R5-01): Arquivo Unicode acentuado não listado em TARGETS invalida trust em alterações sucessivas sob status M."""
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        proj_root = Path(tmp_dir.name).resolve()
        create_project("proj_tn51", proj_root, "python")
        work_dir = proj_root / "proj_tn51"

        subprocess.run(["git", "-C", str(work_dir), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "config", "user.email", "tester@example.com"], check=True, capture_output=True)

        m_path = work_dir / "chdevflow.yaml"
        m_data = load_manifest(m_path)
        m_data["verification"]["commands"] = ["echo 'default checks'"]
        save_manifest(m_path, m_data)

        # Arquivo de código com caracteres acentuados rastreado pelo Git, fora de TARGETS
        accented_file = work_dir / "módulo_segurança.py"
        accented_file.write_text("print('v1_base')\n", encoding="utf-8")

        subprocess.run(["git", "-C", str(work_dir), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "commit", "-m", "init"], check=True, capture_output=True)

        # 1ª modificação v1 -> v2 (status Git M módulo_segurança.py)
        accented_file.write_text("print('v2_operador')\n", encoding="utf-8")
        grant_trust(work_dir, declaration="trust_v2")
        is_ok, reason = check_trust(work_dir)
        self.assertTrue(is_ok, f"Trust com v2 deveria ser válido, obteve: {reason}")

        # Alteração sucessiva de conteúdo v2 -> v3 sob o mesmo status Git M
        accented_file.write_text("print('v3_malicioso_alterado')\n", encoding="utf-8")
        is_ok_after, reason_after = check_trust(work_dir)
        self.assertFalse(is_ok_after, "Alteração sucessiva em arquivo acentuado deve invalidar o trust")
        self.assertIn("Confiança invalidada", reason_after)

    def test_git_status_renames_and_special_characters_invalidate_trust(self) -> None:
        """R5-01: Renomeações com acentos/espaços e arquivos com caracteres especiais invalidam trust adequadamente."""
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        proj_root = Path(tmp_dir.name).resolve()
        create_project("proj_special", proj_root, "python")
        work_dir = proj_root / "proj_special"

        subprocess.run(["git", "-C", str(work_dir), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "config", "user.email", "tester@example.com"], check=True, capture_output=True)

        # 1. Renomeação de arquivo de código com acentos e espaços
        orig_file = work_dir / "origem_coração.py"
        orig_file.write_text("print('orig')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(work_dir), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "commit", "-m", "init"], check=True, capture_output=True)

        grant_trust(work_dir, declaration="trust_orig")
        self.assertTrue(check_trust(work_dir)[0])

        subprocess.run(["git", "-C", str(work_dir), "mv", "origem_coração.py", "dest_novo_ação com espaços.py"], check=True, capture_output=True)
        is_ok, reason = check_trust(work_dir)
        self.assertFalse(is_ok, f"Renomeação de código deve invalidar trust: {reason}")
        self.assertIn("Confiança invalidada", reason)

        # Concede novo trust no estado renomeado e altera o conteúdo do destino
        grant_trust(work_dir, declaration="trust_renamed")
        self.assertTrue(check_trust(work_dir)[0])

        dest_file = work_dir / "dest_novo_ação com espaços.py"
        dest_file.write_text("print('dest modificado')\n", encoding="utf-8")
        is_ok_mod, reason_mod = check_trust(work_dir)
        self.assertFalse(is_ok_mod, f"Modificação após renomeação deve invalidar trust: {reason_mod}")
        self.assertIn("Confiança invalidada", reason_mod)

        # 2. Arquivo com aspas no nome
        quote_file = work_dir / 'script_"quote"_teste.py'
        quote_file.write_text("print('quote v1')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(work_dir), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work_dir), "commit", "-m", "add quote file"], check=True, capture_output=True)
        grant_trust(work_dir, declaration="trust_quote")
        self.assertTrue(check_trust(work_dir)[0])

        quote_file.write_text("print('quote v2 modificado')\n", encoding="utf-8")
        is_ok_quote, reason_quote = check_trust(work_dir)
        self.assertFalse(is_ok_quote, f"Modificação de arquivo com aspas deve invalidar trust: {reason_quote}")
        self.assertIn("Confiança invalidada", reason_quote)


if __name__ == "__main__":
    unittest.main()
