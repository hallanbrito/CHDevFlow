"""Regressao do modo Docker F6, sem daemon, imagem ou chamadas de agentes."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core import docker_acceptance


class DockerAcceptanceTests(unittest.TestCase):
    def test_cmd_isola_codigo_gerado_em_linux_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = docker_acceptance.build_command(Path(tmp))
        self.assertEqual(cmd[:3], ["docker", "run", "--rm"])
        for option in (
                "--pull=never", "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--pids-limit=64", "--memory=256m", "--cpus=1",
                "--user=65534:65534"):
            self.assertIn(option, cmd)
        self.assertIn("type=bind,source=" + str(Path(tmp).resolve()) +
                      ",target=/work,readonly", cmd)
        self.assertEqual(cmd[-10:], ["-I", "-B", "-m", "unittest",
                                    "discover", "-s", "tests", "-p",
                                    "test_*.py", "-v"])
        self.assertNotIn("--privileged", cmd)
        self.assertNotIn("--network=host", cmd)

    def test_bloqueia_sem_docker_antes_do_agy(self):
        with patch.object(docker_acceptance.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Docker CLI"):
                docker_acceptance.preflight()

    def test_bloqueia_daemon_windows(self):
        with patch.object(docker_acceptance.shutil, "which", return_value="docker.exe"), \
             patch.object(docker_acceptance.subprocess, "run",
                          return_value=SimpleNamespace(returncode=0, stdout="windows\n")):
            with self.assertRaisesRegex(ValueError, "Linux"):
                docker_acceptance.preflight()

    def test_bloqueia_imagem_ausente_sem_pull(self):
        with patch.object(docker_acceptance.shutil, "which", return_value="docker.exe"), \
             patch.object(docker_acceptance.subprocess, "run",
                          side_effect=[
                              SimpleNamespace(returncode=0, stdout="linux\n"),
                              SimpleNamespace(returncode=1, stdout=""),
                          ]) as calls:
            with self.assertRaisesRegex(ValueError, "docker pull"):
                docker_acceptance.preflight()
            self.assertEqual(calls.call_count, 2)

    def test_liberado_com_imagem_local_identificada(self):
        with patch.object(docker_acceptance.shutil, "which", return_value="docker.exe"), \
             patch.object(docker_acceptance.subprocess, "run",
                          side_effect=[
                              SimpleNamespace(returncode=0, stdout="linux\n"),
                              SimpleNamespace(returncode=0, stdout="sha256:" + "a"*64),
                          ]) as calls:
            self.assertEqual(docker_acceptance.preflight(),
                             "sha256:" + "a"*64)
            self.assertEqual(calls.call_count, 2)


if __name__ == "__main__":
    unittest.main()
