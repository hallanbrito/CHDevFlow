"""Gate 3: negativas isoladas de origem e code objects do executor F7."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core import po_escalation_runtime as runtime


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.name = "auditprobe.core.sample"
        self.relative = "src/auditprobe/core/sample.py"
        self.path = self.root / self.relative
        self.path.parent.mkdir(parents=True)
        self.path.write_text("def check():\n    return 123\n", encoding="utf-8")
        def git(*args):
            proc = subprocess.run(
                ["git", "-C", str(self.root), *args],
                stdin=subprocess.DEVNULL, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout.decode("ascii").strip()
        git("init", "-q")
        git("add", self.relative)
        git("-c", "user.name=CH Tests", "-c",
            "user.email=ch-tests@users.noreply.github.com", "commit", "-qm", "probe")
        self.commit = git("rev-parse", "HEAD")
        self.module = types.ModuleType(self.name)
        self.module.__file__ = str(self.path)
        exec(compile(self.path.read_text(encoding="utf-8"), str(self.path),
                     "exec", dont_inherit=True),
             self.module.__dict__)

    @contextmanager
    def loaded(self, module=None):
        with patch.dict(sys.modules, {self.name: module or self.module}):
            with patch.object(runtime, "CORE_MODULES", (self.name,)):
                yield

    def test_checkout_real_e_modulos_f7_carregados_batem_com_git(self):
        # Smoke independente usando os modulos de producao, sem GH remoto.
        from chdevflow.core import po_escalation_publication as publication
        self.assertFalse(publication.REMOTE_PUBLICATION_ENABLED)
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD"],
            stdin=subprocess.DEVNULL, capture_output=True, check=False)
        self.assertEqual(head.returncode, 0)
        digest = runtime.verify_loaded_f7_modules(
            ROOT, head.stdout.decode("ascii").strip())
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_blobs_e_funcoes_carregadas_idempotentes(self):
        with self.loaded():
            digest = runtime.verify_loaded_f7_modules(self.root, self.commit)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertEqual(digest, runtime.verify_loaded_f7_modules(
                self.root, self.commit))

    def test_fonte_alterada_apos_commit_bloqueia(self):
        with self.loaded():
            self.path.write_text("def check():\n    return 999\n", encoding="utf-8")
            with self.assertRaisesRegex(runtime.RuntimeIdentityError, "Blob"):
                runtime.verify_loaded_f7_modules(self.root, self.commit)

    def test_bytecode_alterado_com_fonte_git_intacta_bloqueia(self):
        with self.loaded():
            self.module.check.__code__ = (lambda: -1).__code__
            with self.assertRaisesRegex(runtime.RuntimeIdentityError, "Bytecode"):
                runtime.verify_loaded_f7_modules(self.root, self.commit)

    def test_modulo_carregado_de_outro_diretorio_bloqueia(self):
        (self.root / "outro.py").write_text("def check(): pass\n", encoding="utf-8")
        self.module.__file__ = str(self.root / "outro.py")
        with self.loaded():
            with self.assertRaisesRegex(runtime.RuntimeIdentityError, "origem inesperada"):
                runtime.verify_loaded_f7_modules(self.root, self.commit)

    def test_modulo_ausente_bloqueia(self):
        with patch.object(runtime, "CORE_MODULES", ("nao.existe.modulo",)):
            with self.assertRaisesRegex(runtime.RuntimeIdentityError, "nao carregado"):
                runtime.verify_loaded_f7_modules(self.root, self.commit)

    def test_commit_pin_divergente_bloqueia(self):
        with self.loaded():
            with self.assertRaises(runtime.RuntimeIdentityError):
                runtime.verify_loaded_f7_modules(self.root, "0" * 40)

    def test_link_simbolico_bloqueia_quando_disponivel(self):
        alias = self.root / "linked"
        try:
            alias.symlink_to(self.root / "src", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks indisponiveis")
        self.module.__file__ = str(alias / "auditprobe/core/sample.py")
        with self.loaded():
            with self.assertRaises(runtime.RuntimeIdentityError):
                runtime.verify_loaded_f7_modules(self.root, self.commit)


if __name__ == "__main__":
    unittest.main()
