"""Executor local: Windows/Linux, comandos sem credenciais, sem agentes reais no CI."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "apps/bootstrap/sentinela/src") not in sys.path:
    sys.path.insert(0, str(ROOT / "apps/bootstrap/sentinela/src"))

from chdevflow.core import local_executor as local


class LocalExecutorTests(unittest.TestCase):
    def test_doctor_linux_with_clis(self):
        with patch.object(local, "_executables", return_value=(["/usr/bin/agy"], ["/usr/bin/codex"])), \
             patch("platform.system", return_value="Linux"):
            report = local._doctor()
        self.assertEqual(report["status"], "PRONTO_PARA_LAB")
        self.assertEqual(report["host_os"], "Linux")
        self.assertFalse(report["authentication_verified"])

    def test_doctor_windows_with_clis(self):
        with patch.object(local, "_executables", return_value=(["C:/agy.exe"], ["C:/codex.exe"])), \
             patch("platform.system", return_value="Windows"):
            report = local._doctor()
        self.assertEqual(report["status"], "PRONTO_PARA_LAB")
        self.assertFalse(report["credential_access_verified"])

    def test_doctor_sem_codex(self):
        with patch.object(local, "_executables", return_value=(["agy"], [])), \
             redirect_stdout(StringIO()) as out:
            code = local.main(["doctor"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "FALTAM_CLIS")

    def test_run_sem_opt_in_sem_processos(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(local, "run_local_pilot", side_effect=AssertionError("nao chamar")), \
             redirect_stderr(StringIO()) as err:
            code = local.main(["run", "--root", str(Path(temp) / "root")])
        self.assertEqual(code, 2)
        self.assertIn("BLOQUEADO", err.getvalue())

    def test_timeout_invalido_sem_processos(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(local, "run_local_pilot", side_effect=AssertionError("nao chamar")), \
             redirect_stderr(StringIO()):
            code = local.main([
                "run", "--root", str(Path(temp) / "root"),
                "--timeout", "999", "--i-accept-local-risk",
            ])
        self.assertEqual(code, 2)

    def test_run_usa_pastas_novas_e_resultado_do_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "laboratorios"
            seen = []

            def fake_run(*, workspace, evidence, accepted, timeout):
                seen.append((workspace, evidence, accepted, timeout))
                self.assertFalse(workspace.exists())
                self.assertFalse(evidence.exists())
                evidence.mkdir()
                (evidence / "RELATORIO_COMPLETO_CH1.md").write_text("dossie")
                class Result:
                    status = "LAB_APROVADO_AGUARDANDO_CH1"
                    def to_dict(self):
                        return {"status": self.status}
                return Result()

            with patch.object(local, "run_local_pilot", side_effect=fake_run), \
                 redirect_stdout(StringIO()) as out:
                status = local.main([
                    "run", "--root", str(root),
                    "--timeout", "180", "--i-accept-local-risk",
                ])
            self.assertEqual(status, 0)
            self.assertEqual(len(seen), 1)
            workspace, evidence, accepted, timeout = seen[0]
            self.assertTrue(accepted)
            self.assertEqual(timeout, 180)
            self.assertEqual(workspace.parent, root)
            self.assertEqual(evidence.parent, root)
            self.assertNotEqual(workspace, evidence)
            self.assertIn("DOSSIE_CH1", out.getvalue())

    def test_lab_bloqueado_retorna_falha(self):
        with tempfile.TemporaryDirectory() as temp:
            class Blocked:
                status = "LAB_BLOQUEADO"
                def to_dict(self):
                    return {"status": self.status}
            with patch.object(local, "run_local_pilot", return_value=Blocked()), \
                 redirect_stdout(StringIO()):
                status = local.main([
                    "run", "--root", str(Path(temp) / "lab"),
                    "--i-accept-local-risk",
                ])
        self.assertEqual(status, 1)

    def test_ch_pipeline_local_doctor_encaminha_ao_executor(self):
        from chdevflow.cli import main as ch_main
        with patch("chdevflow.cli.local_executor_main", return_value=0) as called:
            self.assertEqual(ch_main(["pipeline", "local-doctor"]), 0)
        called.assert_called_once_with(["doctor"])

    def test_ch_pipeline_local_once_exige_opt_in_no_executor(self):
        from chdevflow.cli import main as ch_main
        with patch("chdevflow.cli.local_executor_main", return_value=2) as called:
            code = ch_main(["pipeline", "local-once", "--timeout", "300"])
        self.assertEqual(code, 2)
        called.assert_called_once_with(["run", "--timeout", "300"])

    def test_ch_pipeline_local_once_repassa_flag_e_root(self):
        from chdevflow.cli import main as ch_main
        with tempfile.TemporaryDirectory() as root:
            with patch("chdevflow.cli.local_executor_main", return_value=0) as called:
                code = ch_main(["pipeline", "local-once", "--root", root,
                                "--timeout", "180", "--i-accept-local-risk"])
            self.assertEqual(code, 0)
            called.assert_called_once_with([
                "run", "--timeout", "180", "--root", root,
                "--i-accept-local-risk",
            ])


    def test_registro_e_interrupcao_de_processos_ativos(self):
        from unittest.mock import MagicMock
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None

        local.register_active_process(fake_proc)
        self.assertIn(fake_proc, local.get_active_processes())

        with patch.object(local, "_kill_tree") as mock_kill:
            terminados = local.terminate_all_active_processes()
            mock_kill.assert_called_with(fake_proc, platform=sys.platform)
            self.assertEqual(terminados, 1)

        local.unregister_active_process(fake_proc)
        self.assertNotIn(fake_proc, local.get_active_processes())


if __name__ == "__main__":
    unittest.main()
