from enum import Enum


class StringEnum(str, Enum):
    pass


class JourneyState(StringEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PROCESSING = "processing"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"


class JobType(StringEnum):
    TRANSPORT_SEARCH = "transport_search"
    ZONE_GENERATION = "zone_generation"
    ZONE_ENRICHMENT = "zone_enrichment"
    LISTINGS_SCRAPE = "listings_scrape"
    LISTINGS_DEDUP = "listings_dedup"
    LISTINGS_PREWARM = "listings_prewarm"
    REPORT_GENERATE = "report_generate"


class JobState(StringEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    CANCELLED_PARTIAL = "cancelled_partial"