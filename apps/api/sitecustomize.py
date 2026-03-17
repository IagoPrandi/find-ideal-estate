"""Make workspace-local packages importable when running from apps/api."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = ROOT / "packages" / "contracts"
if CONTRACTS_PATH.exists():
    sys.path.insert(0, str(CONTRACTS_PATH))
