"""Motor de diagnóstico de ambiente e ferramentas (`ch doctor`)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chdevflow.adapters import ADAPTERS_REGISTRY, get_adapter
from chdevflow.adapters.base import ToolDiagnostic
from chdevflow.core.config import load_manifest, ManifestError


def run_doctor(project_path: Path | None = None) -> dict[str, Any]:
    """
    Executa diagnóstico de capacidade local sem alterar arquivos do sistema ou executar sudo.
    Distingue estritamente ferramentas OBRIGATÓRIAS (conforme manifesto) de OPCIONAIS.
    """
    manifest_data: dict[str, Any] | None = None
    target_dir = (project_path or Path.cwd()).resolve()

    manifest_file = target_dir / "chdevflow.yaml"
    if manifest_file.is_file():
        try:
            manifest_data = load_manifest(manifest_file)
        except ManifestError:
            manifest_data = None

    required_stacks: set[str] = set()
    if manifest_data:
        stack = manifest_data.get("stack", {})
        backend_type = stack.get("backend", {}).get("type")
        frontend_type = stack.get("frontend", {}).get("type")
        db_type = stack.get("database", {}).get("type")
        if backend_type and backend_type != "none":
            required_stacks.add(backend_type.lower())
        if frontend_type and frontend_type != "none":
            required_stacks.add(frontend_type.lower())
        if db_type and db_type != "none":
            required_stacks.add(db_type.lower())

    diagnostics: list[ToolDiagnostic] = []

    # 1. Governança Universal (Git, gh, Docker)
    generic_adapter = get_adapter("generic")
    if generic_adapter:
        diagnostics.extend(generic_adapter.check_prerequisites(target_dir, is_required=True))

    # 2. Adapters específicos
    visited_adapters: set[str] = set()

    # Primeiro executa os requeridos pelo manifesto
    for stack_name in sorted(required_stacks):
        adapter = get_adapter(stack_name)
        if adapter and adapter.name not in visited_adapters:
            diagnostics.extend(adapter.check_prerequisites(target_dir, is_required=True))
            visited_adapters.add(adapter.name)

    # Depois executa diagnóstico dos demais como opcionais
    for adapter_key in ["python", "dotnet", "node", "angular", "react", "java", "postgres"]:
        if adapter_key in visited_adapters:
            continue
        adapter = get_adapter(adapter_key)
        if adapter:
            diagnostics.extend(adapter.check_prerequisites(target_dir, is_required=False))
            visited_adapters.add(adapter.name)

    # Consolida diagnósticos deduplicando por ferramenta (preserva a de maior severidade/requisito)
    seen_tools: dict[str, ToolDiagnostic] = {}
    for d in diagnostics:
        if d.tool not in seen_tools:
            seen_tools[d.tool] = d
        else:
            existing = seen_tools[d.tool]
            # Se a nova ocorrência for obrigatória e a existente não, substitui
            if d.required and not existing.required:
                seen_tools[d.tool] = d

    final_diagnostics = list(seen_tools.values())

    # Consolida estatísticas
    required_total = sum(1 for d in final_diagnostics if d.required)
    required_ok = sum(1 for d in final_diagnostics if d.required and d.installed and d.status == "OK")
    optional_total = sum(1 for d in final_diagnostics if not d.required)
    optional_ok = sum(1 for d in final_diagnostics if not d.required and d.installed and d.status == "OK")

    is_healthy = (required_ok == required_total)

    return {
        "healthy": is_healthy,
        "project_path": str(target_dir),
        "manifest_found": bool(manifest_data),
        "required_stacks": sorted(list(required_stacks)),
        "summary": {
            "required_total": required_total,
            "required_ok": required_ok,
            "optional_total": optional_total,
            "optional_ok": optional_ok,
        },
        "diagnostics": [d.to_dict() for d in final_diagnostics],
    }


def render_doctor_human(report: dict[str, Any]) -> str:
    """Renderiza relatório humano no terminal com diagnóstico claro e remediações."""
    lines: list[str] = []
    lines.append("=" * 65)
    lines.append("CHDevFlow Doctor — Diagnóstico de Ambiente e Ferramentas")
    lines.append(f"Diretório: {report['project_path']}")
    if report["manifest_found"]:
        lines.append(f"Manifesto: Presente (Stacks requeridas: {', '.join(report['required_stacks']) or 'nenhuma'})")
    else:
        lines.append("Manifesto: Nenhum manifesto detectado (verificação universal)")
    lines.append("=" * 65)

    lines.append("\n[Ferramentas Obrigatórias]")
    required_items = [d for d in report["diagnostics"] if d["required"]]
    if not required_items:
        lines.append("  (Nenhuma ferramenta marcada como obrigatória)")
    for item in required_items:
        symbol = "✓" if (item["installed"] and item["status"] == "OK") else "✗"
        v_str = f"v{item['version']}" if item["version"] else "(não detectada)"
        lines.append(f"  {symbol} {item['tool']:<10} {v_str:<15} [{item['status']}]: {item['details']}")
        if not item["installed"] and item["remediation"]:
            lines.append(f"    → Remediação manual: {item['remediation']}")

    lines.append("\n[Ferramentas Opcionais / Complementares]")
    optional_items = [d for d in report["diagnostics"] if not d["required"]]
    for item in optional_items:
        symbol = "✓" if (item["installed"] and item["status"] == "OK") else " "
        v_str = f"v{item['version']}" if item["version"] else "—"
        lines.append(f"  [{symbol}] {item['tool']:<10} {v_str:<15} [{item['status']}]: {item['details']}")
        if not item["installed"] and item["remediation"]:
            lines.append(f"      Nota: {item['remediation']}")

    summary = report["summary"]
    lines.append("\n" + "-" * 65)
    lines.append(f"Resultado: Obrigatórias: {summary['required_ok']}/{summary['required_total']} OK | Opcionais: {summary['optional_ok']}/{summary['optional_total']} ativas.")
    if report["healthy"]:
        lines.append("Conclusão: Ambiente saudável para governança e execução das stacks do projeto.")
    else:
        lines.append("Conclusão: Ferramentas obrigatórias AUSENTES. Instale os pré-requisitos antes de executar.")
    lines.append("Governança: Diagnóstico local estritamente consultivo. Sem alterações automáticas no sistema.")
    lines.append("=" * 65)

    return "\n".join(lines)
