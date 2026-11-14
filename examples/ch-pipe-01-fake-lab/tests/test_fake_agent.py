"""Miniensaio offline de fluxo; nenhuma integração com agentes reais."""
import unittest


class FakePipeline(unittest.TestCase):
    def test_sequencia_agy_testes_codex(self):
        stages = ("AGY_FAKE", "TESTES_FAKE", "CODEX_FAKE", "DOSSIER_FAKE")
        self.assertEqual(stages[0], "AGY_FAKE")
        self.assertEqual(stages[-1], "DOSSIER_FAKE")

    def test_codex_veto_bloqueia(self):
        verdict = "BLOQUEADO"
        self.assertNotEqual(verdict, "APROVAR_LAB")


if __name__ == "__main__":
    unittest.main()
