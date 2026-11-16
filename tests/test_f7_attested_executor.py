"""F7 E3-C3: negativas de identidade E3-B sem rede ou Docker real."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chdevflow.core import attested_executor as runner


class AttestedExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tar = self.root / "executor.tar"
        self.tar.write_bytes(b"binary fake test fixture; not a real signed tar")

    def test_tar_adulterado_bloqueia_antes_de_qualquer_ferramenta(self):
        with patch.object(runner, "_command") as command:
            with patch.object(runner.shutil, "which", return_value="/usr/bin/tool"):
                with self.assertRaisesRegex(runner.AttestedExecutorError, "SHA-256"):
                    runner.preflight(self.tar)
            command.assert_not_called()

    def test_tar_symlink_bloqueia(self):
        p = self.root / "alias.tar"
        try:
            p.symlink_to(self.tar)
        except (NotImplementedError, OSError):
            self.skipTest("symlink nao suportado")
        with self.assertRaisesRegex(runner.AttestedExecutorError, "Link"):
            runner.verify_tar(p)

    def test_tar_ausente_bloqueia(self):
        with self.assertRaisesRegex(runner.AttestedExecutorError, "ausente"):
            runner.verify_tar(self.root / "missing.tar")

    def test_preflight_valida_gh_docker_digest_user_e_revision(self):
        def command(args, timeout):
            if args[:3] == ["gh", "attestation", "verify"]:
                self.assertIn(runner.SOURCE_SHA, args)
                self.assertIn(runner.SIGNER, args)
                self.assertIn("--deny-self-hosted-runners", args)
                return "Verification succeeded"
            if args[:2] == ["docker", "info"]:
                return "linux"
            if args[:2] == ["docker", "load"]:
                return "Loaded image"
            if args[-1] == "{{.Id}}":
                return runner.IMAGE_ID
            if args[-1] == "{{.Config.User}}":
                return "65534:65534"
            if args[-1].startswith("{{index .Config.Labels"):
                return runner.SOURCE_SHA
            raise AssertionError("Unexpected verification command: " + repr(args))
        with patch.object(runner, "verify_tar", return_value=runner.TAR_SHA256), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(runner, "_command", side_effect=command) as calls:
            result = runner.preflight(self.tar)
        self.assertEqual(result, runner.IMAGE_ID)
        self.assertEqual(calls.call_count, 6)

    def test_pin_recusa_revision_imagem_ou_gh_failure(self):
        for variant in ("gh", "image", "user", "revision"):
            with self.subTest(variant=variant):
                def command(args, timeout):
                    if args[0] == "gh":
                        if variant == "gh":
                            raise runner.AttestedExecutorError("verificacao gh recusada")
                        return "verified"
                    if args[:2] == ["docker", "info"]:
                        return "linux"
                    if args[:2] == ["docker", "load"]:
                        return "loaded"
                    if args[-1] == "{{.Id}}":
                        return "sha256:" + "a"*64 if variant == "image" else runner.IMAGE_ID
                    if args[-1] == "{{.Config.User}}":
                        return "root" if variant == "user" else "65534:65534"
                    return "f"*40 if variant == "revision" else runner.SOURCE_SHA
                with patch.object(runner, "verify_tar", return_value=runner.TAR_SHA256), \
                     patch.object(runner.shutil, "which", return_value="/usr/bin/tool"), \
                     patch.object(runner, "_command", side_effect=command):
                    with self.assertRaises(runner.AttestedExecutorError):
                        runner.preflight(self.tar)

    def test_comando_usa_id_imutavel_e_defesas_docker(self):
        cmd = runner.build_command(self.root)
        self.assertEqual(cmd[0:2], ["docker", "run"])
        self.assertIn(runner.IMAGE_ID, cmd)
        self.assertNotIn("python:3.12-slim", cmd)
        self.assertIn("--network=none", cmd)
        self.assertIn("--read-only", cmd)
        self.assertIn("--cap-drop=ALL", cmd)
        self.assertIn("--security-opt=no-new-privileges", cmd)
        self.assertEqual(cmd[-1], "--run-tests")
        self.assertTrue(any(",readonly" in arg and "target=/work" in arg for arg in cmd))

    def test_resultado_json_aprovado(self):
        stdout = json.dumps({
            "schema": runner.SCHEMA, "status": "TESTS_PASS",
            "tests_exit_code": 0, "log_sha256": "c"*64,
            "log_excerpt": "Ran 2 tests in 0.002s\n\nOK\n",
        })
        self.assertIn("Ran 2 tests", runner.checked_result(stdout, 0))

    def test_resultado_json_assertion_reprovada(self):
        stdout = json.dumps({
            "schema": runner.SCHEMA, "status": "TESTS_FAILED",
            "tests_exit_code": 1, "log_sha256": "c"*64,
            "log_excerpt": "Ran 2 tests in 0.002s\n\nFAILED (failures=1)\n",
        })
        self.assertIn("FAILED", runner.checked_result(stdout, 12))

    def test_resultado_forjado_ou_infra_bloqueia(self):
        good = {
            "schema": runner.SCHEMA, "status": "TESTS_PASS",
            "tests_exit_code": 0, "log_sha256": "c"*64,
            "log_excerpt": "Ran 2 tests in 0.002s\n\nOK\n",
        }
        for change in (
            {"schema": "outro"},
            {"status": "TESTS_FAILED"},
            {"tests_exit_code": True},
            {"log_excerpt": ""},
            {"log_excerpt": "OK"},
            {"log_sha256": "nao"},
        ):
            with self.subTest(change=change):
                with self.assertRaises(runner.AttestedExecutorError):
                    runner.checked_result(json.dumps({**good, **change}), 0)
        for code in (1, 20, 30, 124):
            with self.subTest(exit_code=code):
                with self.assertRaises(runner.AttestedExecutorError):
                    runner.checked_result(json.dumps(good), code)
        with self.assertRaises(runner.AttestedExecutorError):
            runner.checked_result("not-json", 0)


if __name__ == "__main__":
    unittest.main()
