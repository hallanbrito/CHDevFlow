"""Motor de diagnóstico de ambiente e ferramentas (`ch doctor`)."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from chdevflow.adapters import ADAPTERS_REGISTRY, get_adapter
from chdevflow.adapters.base import ToolDiagnostic
from chdevflow.core.config import load_manifest, ManifestError


def check_version_compatibility(detected_version: str | None, required_version: str | None) -> tuple[bool, str]:
    """
    Compara a versão detectada com a versão requerida no manifesto.
    Verifica compatibilidade semântica básica (ex.: major de .NET/Angular/Node ou versão mínima).
    """
    if not required_version or not detected_version:
        return True, "Sem restrição de versão específica"

    det_clean = detected_version.lstrip("v").strip()
    req_clean = required_version.lstrip("v").strip()

    det_parts = [int(p) for p in re.findall(r"\d+", det_clean)]
    req_parts = [int(p) for p in re.findall(r"\d+", req_clean)]

    if not det_parts or not req_parts:
        if det_clean.startswith(req_clean):
            return True, "Compatível"
        return False, f"Versão detectada ({detected_version}) diverge da requerida ({required_version})"

    # Comparação por Major (ex: .NET 10, Java 21, Angular 22)
    if len(req_parts) == 1:
        if det_parts[0] != req_parts[0]:
            return False, f"Versão principal ({det_parts[0]}) incompatível com a versão requerida ({req_parts[0]})"
        return True, "Compatível"

    # Comparação Major.Minor (ex: Python 3.12)
    if len(req_parts) == 2:
        if det_parts[0] != req_parts[0] or det_parts[1] < req_parts[1]:
            return False, f"Versão detectada ({det_clean}) incompatível com a versão mínima requerida ({req_clean})"
        return True, "Compatível"

    # Comparação completa
    if det_parts[:len(req_parts)] != req_parts:
        return False, f"Versão detectada ({det_clean}) diverge da requerida ({req_clean})"
    return True, "Compatível"


def run_doctor(project_path: Path | None = None) -> dict[str, Any]:
    """
    Executa diagnóstico de capacidade local sem alterar arquivos do sistema ou executar sudo.
    Distingue estritamente ferramentas OBRIGATÓRIAS (conforme manifesto) de OPCIONAIS.
    Valida compatibilidade entre versões instaladas e versões requeridas no manifesto.
    """
    manifest_data: dict[str, Any] | None = None
    target_dir = (project_path or Path.cwd()).resolve()

    manifest_file = target_dir / "chdevflow.yaml"
    if manifest_file.is_file():
        try:
            manifest_data = load_manifest(manifest_file)
        except ManifestError:
            manifest_data = None

    required_stacks: dict[str, str | None] = {}
    if manifest_data:
        stack = manifest_data.get("stack", {})
        backend = stack.get("backend", {})
        frontend = stack.get("frontend", {})
        db = stack.get("database", {})

        b_type = backend.get("type")
        if b_type and b_type != "none":
            required_stacks[b_type.lower()] = str(backend.get("version")) if backend.get("version") else None

        f_type = frontend.get("type")
        if f_type and f_type != "none":
            required_stacks[f_type.lower()] = str(frontend.get("version")) if frontend.get("version") else None

        db_type = db.get("type")
        if db_type and db_type != "none":
            required_stacks[db_type.lower()] = str(db.get("version")) if db.get("version") else None

    diagnostics: list[ToolDiagnostic] = []

    # 1. Governança Universal (Git, gh, Docker)
    generic_adapter = get_adapter("generic")
    if generic_adapter:
        diagnostics.extend(generic_adapter.check_prerequisites(target_dir, is_required=True))

    # 2. Adapters específicos
    visited_adapters: set[str] = set()

    # Primeiro executa os requeridos pelo manifesto e valida versões
    for stack_name, req_version in sorted(required_stacks.items()):
        adapter = get_adapter(stack_name)
        if adapter and adapter.name not in visited_adapters:
            diag_items = adapter.check_prerequisites(target_dir, is_required=True)
            for d in diag_items:
                is_direct_tool = (
                    (d.tool == stack_name)
                    or (stack_name == "python" and d.tool in ("python", "python3"))
                    or (stack_name == "angular" and d.tool == "ng")
                    or (stack_name == "java" and d.tool in ("java", "mvn"))
                )
                if is_direct_tool and d.installed and d.version and req_version:
                    compat, msg = check_version_compatibility(d.version, req_version)
                    if not compat:
                        d.status = "INCOMPATIVEL"
                        d.details = f"{d.details}. {msg}."
                        d.remediation = f"Instale a versão {req_version} da ferramenta {d.tool} exigida em chdevflow.yaml."
            diagnostics.extend(diag_items)
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
            elif d.required and existing.required:
                # Se uma estiver incompatível ou ausente, prevalece o erro
                if d.status in ("INCOMPATIVEL", "AUSENTE", "ERRO") and existing.status == "OK":
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
        "required_stacks": sorted(list(required_stacks.keys())),
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
        if (not item["installed"] or item["status"] != "OK") and item["remediation"]:
            lines.append(f"    → Remediação manual: {item['remediation']}")

    lines.append("\n[Ferramentas Opcionais / Complementares]")
    optional_items = [d for d in report["diagnostics"] if not d["required"]]
    for item in optional_items:
        symbol = "✓" if (item["installed"] and item["status"] == "OK") else " "
        v_str = f"v{item['version']}" if item["version"] else "—"
        lines.append(f"  [{symbol}] {item['tool']:<10} {v_str:<15} [{item['status']}]: {item['details']}")
        if (not item["installed"] or item["status"] != "OK") and item["remediation"]:
            lines.append(f"      Nota: {item['remediation']}")

    summary = report["summary"]
    lines.append("\n" + "-" * 65)
    lines.append(f"Resultado: Obrigatórias: {summary['required_ok']}/{summary['required_total']} OK | Opcionais: {summary['optional_ok']}/{summary['optional_total']} ativas.")
    if report["healthy"]:
        lines.append("Conclusão: Ambiente saudável para governança e execução das stacks do projeto.")
    else:
        lines.append("Conclusão: Ferramentas obrigatórias AUSENTES ou INCOMPATÍVEIS. Resolva os pré-requisitos.")
    lines.append("Governança: Diagnóstico local estritamente consultivo. Sem alterações automáticas no sistema.")
    lines.append("=" * 65)

    return "\n".join(lines)
