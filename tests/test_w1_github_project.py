import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import w1_github_project as w1


class W1Tests(unittest.TestCase):
    def test_four_execution_lanes(self):
        self.assertTrue({"01 Hallan", "02 ChatGPT", "03 Codex", "04 AGY"} <= set(w1.VIEWS))

    def test_human_gate(self):
        self.assertIn("AGUARDANDO_PO", w1.FIELDS["Etapa CH"])
        self.assertIn("PARCIAL", w1.FIELDS["Decisao PO"])
        self.assertNotIn("AUTO_MERGE", w1.FIELDS["Decisao PO"])

    def test_offline_preview(self):
        old_gh = w1.gh
        old_args = sys.argv[:]
        try:
            def no_network(*args):
                raise AssertionError("Modo prévia não deve consultar o GitHub")
            w1.gh = no_network
            sys.argv = ["w1_github_project.py"]
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = w1.main()
            self.assertEqual(0, status)
            self.assertIn("PRÉVIA APENAS", output.getvalue())
        finally:
            w1.gh = old_gh
            sys.argv = old_args


if __name__ == "__main__":
    unittest.main()
