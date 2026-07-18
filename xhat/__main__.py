"""Permite executar o pacote com `python -m xhat`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
