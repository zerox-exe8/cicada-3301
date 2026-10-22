"""
Kyro Discord Bot - Launcher Entrypoint
Enables convenient execution via `python main.py` or `python -m src.main`.
"""
import sys
from pathlib import Path

# Ensure root directory is top of sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import asyncio
from src.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
