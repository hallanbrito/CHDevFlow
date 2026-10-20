"""Subpacote de workers da Sentinela.

Na missão BOOT-01, contém exclusivamente o FakeWorker (simulador inofensivo).
"""

from .fake import FakeWorker

__all__ = ["FakeWorker"]
