"""Centralized vendor path setup for SWARM imports."""

import sys
from pathlib import Path

_VENDOR_SWARM = Path(__file__).resolve().parent.parent / "vendor" / "swarm"
if str(_VENDOR_SWARM) not in sys.path:
    sys.path.insert(0, str(_VENDOR_SWARM))
