"""CH-PIPE-01/F3: reserva local antirreplay, somente para futuros pilotos.

Não é um runner. Nenhum processo AGY/Codex é iniciado aqui. Um lock abandonado
bloqueia novas reservas até reconciliação humana: nunca libera por timeout.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from threading import Event
from typing import Literal

DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{3,100}$")


class ReservationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    run_id: str
    mission_digest: str
    state: str


class PilotClaimStore:
    """Reserva exclusiva no *mesmo host*, não coordena múltiplas máquinas."""

    def __init__(self, state_dir: Path) -> None:
        if state_dir.is_symlink() or not state_dir.is_dir():
            raise ValueError("Diretório de estado ausente/inseguro")
        self.root = state_dir.resolve()
        for folder in (self.root, self.root.parent):
            if folder.is_symlink():
                raise ValueError("Diretório simbólico recusado")
        self._lock_path = self.root / "active.lock"

    def reserve(self, digest: str, run_id: str) -> Reservation:
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            raise ValueError("Digest inválido")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            raise ValueError("Run ID inválido")
        history = self.root / f"{digest}.claim.json"
        if history.exists() or history.is_symlink():
            raise ReservationBlocked("Replay ou missão previamente reservada")
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ReservationBlocked("Outra missão ativa ou lock órfão") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"run_id": run_id, "mission_digest": digest}, handle)
            # A marca de replay é gravada ANTES de devolver a reserva.
            hfd = os.open(history, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(hfd, "w", encoding="utf-8") as handle:
                json.dump({"run_id": run_id, "mission_digest": digest,
                           "state": "RESERVED"}, handle)
            return Reservation(run_id, digest, "RESERVED")
        except BaseException:
            # Não apagar histórico existente; eventual crash exige reconciliação.
            if self._lock_path.exists():
                self._lock_path.unlink()
            raise

    def finish(self, reservation: Reservation, state: Literal[
        "COMPLETED", "BLOCKED", "CANCELLED", "INDETERMINATE"
    ]) -> Reservation:
        if state not in {"COMPLETED", "BLOCKED", "CANCELLED", "INDETERMINATE"}:
            raise ValueError("Estado final inválido")
        if not self._lock_path.is_file() or self._lock_path.is_symlink():
            raise ReservationBlocked("Lock ausente ou inválido")
        try:
            active = json.loads(self._lock_path.read_text(encoding="utf-8"))
            if active != {"run_id": reservation.run_id,
                          "mission_digest": reservation.mission_digest}:
                raise ReservationBlocked("Reserva de outra missão")
            history = self.root / f"{reservation.mission_digest}.claim.json"
            previous = json.loads(history.read_text(encoding="utf-8"))
            if previous.get("run_id") != reservation.run_id or previous.get("state") != "RESERVED":
                raise ReservationBlocked("Histórico inesperado; reconciliação necessária")
            # Substitui conteúdo por arquivo temporário + rename no mesmo diretório.
            temp = self.root / f"{reservation.mission_digest}.closing"
            if temp.exists() or temp.is_symlink():
                raise ReservationBlocked("Arquivo temporário de fechamento já existe")
            fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({**previous, "state": state}, handle)
            temp.replace(history)
            self._lock_path.unlink()
            return Reservation(reservation.run_id, reservation.mission_digest, state)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ReservationBlocked("Falha ao finalizar; lock preservado") from exc


class PilotCancellation:
    """Sinal cooperativo para futura integração; não mata processos externos."""
    def __init__(self) -> None:
        self._event = Event()

    def request(self) -> None:
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()
