"""Testes unittest offline do probe MCP, executados pela CI integral."""
import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "maestro_mcp_probe.py"
spec = importlib.util.spec_from_file_location("maestro_mcp_probe", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestMaestroMCPProbe(unittest.TestCase):
    def test_rejects_missing_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Checkout do Maestro"):
                module.make_stdio_settings(Path(tmp))

    def test_prepares_local_stdio_without_remote_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "src" / "maestro_router" / "factory_mcp.py"
            file.parent.mkdir(parents=True)
            file.write_text("# fixture\n")
            command, args, env = module.make_stdio_settings(root)
            self.assertTrue(command)
            self.assertEqual(args, ["-m", "maestro_router.factory_mcp"])
            self.assertIn(str(root / "src"), env["PYTHONPATH"])

    def test_invalid_tool_denied_before_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "allowlist"):
                asyncio.run(module.probe(Path(tmp), "execute_model", "CHDevFlow", 10))


if __name__ == "__main__":
    unittest.main()
