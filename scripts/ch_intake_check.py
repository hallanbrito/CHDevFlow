#!/usr/bin/env python3
"""Wrapper local do contrato canônico chdevflow.core.intake (somente leitura)."""
from pathlib import Path
import sys

_ROOT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_ROOT_SRC) not in sys.path:
    sys.path.insert(0, str(_ROOT_SRC))

from chdevflow.core.intake import main, validate_issue  # noqa: E402, F401

if __name__ == "__main__":
    raise SystemExit(main())
