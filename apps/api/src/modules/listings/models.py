"""Listings domain: ZoneCacheStatus state machine and related constants."""

from __future__ import annotations

from typing import ClassVar


class InvalidStateTransition(RuntimeError):
    """Raised when an invalid state transition is attempted."""


class ZoneCacheStatus:
    """
    Explicit state machine for zone_listing_caches.status.

    Valid transitions:
        pending        → scraping
        scraping       → partial | complete | failed | cancelled_partial
        partial        → complete | failed | cancelled_partial
    """

    PENDING           = "pending"
    SCRAPING          = "scraping"
    PARTIAL           = "partial"
    COMPLETE          = "complete"
    FAILED            = "failed"
    CANCELLED_PARTIAL = "cancelled_partial"

    _ALLOWED: ClassVar[dict[str, set[str]]] = {
        PENDING:           {SCRAPING},
        SCRAPING:          {PARTIAL, COMPLETE, FAILED, CANCELLED_PARTIAL},
        PARTIAL:           {COMPLETE, FAILED, CANCELLED_PARTIAL},
        COMPLETE:          set(),
        FAILED:            set(),
        CANCELLED_PARTIAL: set(),
    }

    @classmethod
    def validate_transition(cls, current: str, new: str) -> None:
        allowed = cls._ALLOWED.get(current, set())
        if new not in allowed:
            raise InvalidStateTransition(
                f"Cannot transition zone_listing_cache from '{current}' to '{new}'. "
                f"Allowed targets: {sorted(allowed) or 'none (terminal state)'}"
            )

    @classmethod
    def transition_to(cls, current: str, new_state: str) -> str:
        """Single transition API used by cache status updates."""
        cls.validate_transition(current, new_state)
        return new_state

    @classmethod
    def is_usable(cls, status: str | None) -> bool:
        """Returns True when a cache record can serve listings immediately."""
        return status in {cls.COMPLETE, cls.PARTIAL}

    @classmethod
    def is_terminal(cls, status: str | None) -> bool:
        return status in {cls.COMPLETE, cls.FAILED, cls.CANCELLED_PARTIAL}


class PreliminaryResultThresholds:
    MIN_GEOMETRIC_COVERAGE = 0.30  # 30 % of zone area covered
    MIN_PROPERTIES_RENTAL  = 5
    MIN_PROPERTIES_SALE    = 3
    MAX_CACHE_AGE_RENTAL   = 12   # hours
    MAX_CACHE_AGE_SALE     = 24   # hours


PLATFORM_QUINTOANDAR = "quintoandar"
PLATFORM_ZAPIMOVEIS  = "zapimoveis"
PLATFORM_VIVAREAL    = "vivareal"

FREE_PLATFORMS  = [PLATFORM_QUINTOANDAR, PLATFORM_ZAPIMOVEIS]
PRO_PLATFORMS   = [PLATFORM_QUINTOANDAR, PLATFORM_ZAPIMOVEIS, PLATFORM_VIVAREAL]
ALL_PLATFORMS   = PRO_PLATFORMS
