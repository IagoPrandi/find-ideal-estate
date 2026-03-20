"""Local import shim for monorepo contracts during bootstrap.

This keeps `import contracts` working from `apps/api` while re-exporting the
real shared DTOs from `packages/contracts/contracts`.
"""

# ruff: noqa: E402

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

# __file__ = apps/api/contracts/__init__.py -> repo root is parents[3].
_SHARED_CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "contracts"
if str(_SHARED_CONTRACTS_DIR) not in __path__:
    __path__.append(str(_SHARED_CONTRACTS_DIR))

from .enums import JobState, JobType, JourneyState
from .jobs import JobCancelAccepted, JobCreate, JobEventRead, JobRead
from .journeys import JourneyCreate, JourneyRead, JourneyReferencePoint, JourneyUpdate

__version__ = "0.1.0"

__all__ = [
    "JobCancelAccepted",
    "JobCreate",
    "JobEventRead",
    "JobRead",
    "JobState",
    "JobType",
    "JourneyCreate",
    "JourneyRead",
    "JourneyReferencePoint",
    "JourneyState",
    "JourneyUpdate",
]
