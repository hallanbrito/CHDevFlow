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

    def test_graphql_view_layout(self):
        """A API usa BOARD_LAYOUT; uma alteração silenciosa quebra a instalação."""
        original = w1.graphql
        commands = []

        def fake_graphql(query, **variables):
            commands.append(query)
            if "user(login:" in query:
                return {"user": {"projectV2": {"id": "PVT_demo", "views": {"nodes": []}}}}
            if "createProjectV2View" in query:
                return {"createProjectV2View": {"projectV2View": {"id": "VIEW_demo"}}}
            if "updateProjectV2View" in query:
                return {"updateProjectV2View": {"projectV2View": {"id": "VIEW_demo"}}}
            raise AssertionError("Operação GraphQL desconhecida")

        try:
            w1.graphql = fake_graphql
            with contextlib.redirect_stdout(io.StringIO()):
                w1.ensure_views("hallanbrito", 1)
        finally:
            w1.graphql = original
        create_queries = [q for q in commands if "createProjectV2View" in q]
        self.assertEqual(len(w1.VIEWS), len(create_queries))
        self.assertTrue(all("layout:BOARD_LAYOUT" in q for q in create_queries))

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
