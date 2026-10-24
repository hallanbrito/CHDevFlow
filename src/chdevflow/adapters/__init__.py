"""Registro e fábrica de adapters de tecnologia do CHDevFlow."""
from __future__ import annotations

from chdevflow.adapters.angular import AngularAdapter
from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic
from chdevflow.adapters.dotnet import DotnetAdapter
from chdevflow.adapters.generic import GenericAdapter
from chdevflow.adapters.java import JavaAdapter
from chdevflow.adapters.node import NodeAdapter
from chdevflow.adapters.postgres import PostgresAdapter
from chdevflow.adapters.python import PythonAdapter
from chdevflow.adapters.react import ReactAdapter

ADAPTERS_REGISTRY: dict[str, type[BaseAdapter]] = {
    "generic": GenericAdapter,
    "python": PythonAdapter,
    "dotnet": DotnetAdapter,
    "node": NodeAdapter,
    "angular": AngularAdapter,
    "react": ReactAdapter,
    "java": JavaAdapter,
    "postgres": PostgresAdapter,
    "postgresql": PostgresAdapter,
}


def get_adapter(name: str) -> BaseAdapter | None:
    """Retorna instância do adapter solicitado pelo nome, ou None se não suportado."""
    cls = ADAPTERS_REGISTRY.get(name.strip().lower())
    return cls() if cls else None
