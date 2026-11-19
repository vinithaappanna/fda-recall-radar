#!/usr/bin/env python3
"""Query the recall archive: recall <number> | firm <name> | theme <theme>."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from recallradar.cli import main

if __name__ == "__main__":
    sys.exit(main())
