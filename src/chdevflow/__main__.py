"""Ponto de entrada quando executado via `python -m chdevflow`."""
from __future__ import annotations

import sys
from chdevflow.cli import main

if __name__ == "__main__":
    sys.exit(main())
