"""Adapter para stack React."""
from __future__ import annotations

from pathlib import Path

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic
from chdevflow.adapters.node import NodeAdapter


class ReactAdapter(BaseAdapter):
    name = "react"
    display_name = "React"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        # React requer Node.js e npm
        node_adapter = NodeAdapter()
        return node_adapter.check_prerequisites(project_path, is_required=is_required)

    def get_default_verification_commands(self) -> list[str]:
        return ["npm test"]
