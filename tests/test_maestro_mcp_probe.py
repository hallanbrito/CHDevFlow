"""Testes offline do cliente local MCP, sem processo servidor real."""
import asyncio
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "maestro_mcp_probe.py"
spec = importlib.util.spec_from_file_location("maestro_mcp_probe", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_rejects_missing_server(tmp_path):
    with pytest.raises(ValueError, match="Checkout do Maestro"):
        module.make_stdio_settings(tmp_path)


def test_prepares_local_stdio_without_remote_endpoint(tmp_path):
    file = tmp_path / "src" / "maestro_router" / "factory_mcp.py"
    file.parent.mkdir(parents=True)
    file.write_text("# fixture\n")
    command, args, env = module.make_stdio_settings(tmp_path)
    assert command
    assert args == ["-m", "maestro_router.factory_mcp"]
    assert str(tmp_path / "src") in env["PYTHONPATH"]


def test_invalid_tool_denied_before_subprocess(tmp_path):
    with pytest.raises(ValueError, match="allowlist"):
        asyncio.run(module.probe(tmp_path, "execute_model", "CHDevFlow", 10))
