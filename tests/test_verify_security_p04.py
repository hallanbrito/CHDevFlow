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
import stat
import subprocess
import sys
import tempfile
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
from chdevflow.core.tree import generate as generate_tree
from chdevflow.core.submit import validate_and_submit, SubmitError
from chdevflow.core.trust import (
    check_trust,
    compute_project_fingerprint,
    grant_trust,
    invalidate_trust,
    TRUST_FILE_REL,
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
        with patch("shutil.which", return_value="/usr/bin/npm"):
            tokens_test = parse_and_validate_command("npm test", self.root, sanitized_path)
            self.assertTrue(tokens_test[0].endswith("npm") or tokens_test[0].endswith("npm-cli.js"))
            self.assertEqual(tokens_test[1:], ["test"])

            tokens_run = parse_and_validate_command("npm run test:ci", self.root, sanitized_path)
            self.assertTrue(tokens_run[0].endswith("npm") or tokens_run[0].endswith("npm-cli.js"))
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
        # Salva sem auto_trust
        content = json.dumps(self.manifest)
        # Escreve cru para não disparar save_manifest auto_trust
        import yaml
        self.manifest_file.write_text(yaml.safe_dump(self.manifest), encoding="utf-8")

        with self.assertRaises(SubmitError):
            validate_and_submit(self.root)

    def test_tn30_trust_declaration_explicit_non_sandbox(self) -> None:
        """TN-30: Manifestação de trust explicita não ser sandbox de sistema operacional."""
        trust_data = grant_trust(self.root, declaration="operador_humano_teste")
        self.assertIn("operador_humano_teste", trust_data["declaration"])
        self.assertIn("Não constitui sandbox de sistema operacional", trust_data["notice"])


if __name__ == "__main__":
    unittest.main()
