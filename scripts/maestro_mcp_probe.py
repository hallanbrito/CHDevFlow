"""Consulta explicitamente o servidor MCP local do Maestro (sem despachar tarefas)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

_TOOLS = ("maestro_catalog", "factory_issues", "fallback_evidence")


def make_stdio_settings(maestro_repo: Path) -> tuple[str, list[str], dict[str, str]]:
    """Valida checkout e prepara subprocesso isolado com PYTHONPATH explicito."""
    repo = maestro_repo.expanduser().resolve()
    if not (repo / "src" / "maestro_router" / "factory_mcp.py").is_file():
        raise ValueError("Checkout do Maestro sem src/maestro_router/factory_mcp.py")
    env = dict(os.environ)
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo / "src") + (os.pathsep + current if current else "")
    return sys.executable, ["-m", "maestro_router.factory_mcp"], env


async def probe(maestro_repo: Path, tool: str, project: str, limit: int) -> object:
    """Conecta por MCP stdio; nunca solicita ferramentas de escrita."""
    if tool not in _TOOLS or project not in ("CHDevFlow", "maestro-router") or not 1 <= limit <= 20:
        raise ValueError("Ferramenta ou parametro fora da allowlist")
    command, args, env = make_stdio_settings(maestro_repo)
    try:
        from mcp import Client, StdioServerParameters
    except ImportError as exc:
        raise RuntimeError("Instale o MCP SDK v2 no ambiente Python >=3.11") from exc

    server = StdioServerParameters(command=command, args=args, env=env)
    async with Client(server) as client:
        kwargs = {"project": project, "limit": limit} if tool == "factory_issues" else {}
        result = await client.call_tool(tool, kwargs)
        if result.is_error:
            raise RuntimeError("Ferramenta MCP retornou erro; nenhuma acao executada")
        return result.structured_content if result.structured_content is not None else {"content": [str(x) for x in result.content]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste read-only da integracao CHDevFlow -> Maestro MCP")
    parser.add_argument("--maestro-repo", required=True, type=Path, help="Checkout local do Maestro")
    parser.add_argument("--tool", choices=_TOOLS, default="maestro_catalog")
    parser.add_argument("--project", choices=("CHDevFlow", "maestro-router"), default="CHDevFlow")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        data = asyncio.run(probe(args.maestro_repo, args.tool, args.project, args.limit))
    except (ValueError, RuntimeError, OSError):
        print("MCP indisponivel: verifique SDK, checkout e conexao local", file=sys.stderr)
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
