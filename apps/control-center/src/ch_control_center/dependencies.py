"""Injeção de dependências e singletons para os serviços do Control Center."""
from __future__ import annotations

from ch_control_center.services.mission_service import MissionService
from ch_control_center.services.project_service import ProjectService

_mission_service_instance: MissionService | None = None
_project_service_instance: ProjectService | None = None


def get_mission_service() -> MissionService:
    """Retorna a instância compartilhada do MissionService."""
    global _mission_service_instance
    if _mission_service_instance is None:
        _mission_service_instance = MissionService()
    return _mission_service_instance


def get_project_service() -> ProjectService:
    """Retorna a instância compartilhada do ProjectService."""
    global _project_service_instance
    if _project_service_instance is None:
        _project_service_instance = ProjectService()
    return _project_service_instance


def reset_services() -> None:
    """Reinicializa as instâncias de serviço (útil para testes isolados)."""
    global _mission_service_instance, _project_service_instance
    _mission_service_instance = None
    _project_service_instance = None
