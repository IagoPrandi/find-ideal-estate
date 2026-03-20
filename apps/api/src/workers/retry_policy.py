from __future__ import annotations

from dataclasses import dataclass

from contracts import JobType


@dataclass(frozen=True)
class RetryRule:
    max_retries: int
    backoff_seconds: tuple[int, ...]


class JobRetryPolicy:
    TRANSPORT_SEARCH = RetryRule(max_retries=2, backoff_seconds=(5, 30))
    ZONE_GENERATION = RetryRule(max_retries=1, backoff_seconds=(10,))
    ZONE_ENRICHMENT = RetryRule(max_retries=2, backoff_seconds=(5, 15))
    LISTINGS_SCRAPE = RetryRule(max_retries=3, backoff_seconds=(10, 30, 60))
    LISTINGS_DEDUP = RetryRule(max_retries=2, backoff_seconds=(5, 10))
    REPORT_GENERATE = RetryRule(max_retries=1, backoff_seconds=(15,))

    _BY_JOB_TYPE = {
        JobType.TRANSPORT_SEARCH: TRANSPORT_SEARCH,
        JobType.ZONE_GENERATION: ZONE_GENERATION,
        JobType.ZONE_ENRICHMENT: ZONE_ENRICHMENT,
        JobType.LISTINGS_SCRAPE: LISTINGS_SCRAPE,
        JobType.LISTINGS_DEDUP: LISTINGS_DEDUP,
        JobType.REPORT_GENERATE: REPORT_GENERATE,
        JobType.LISTINGS_PREWARM: LISTINGS_SCRAPE,
    }

    @classmethod
    def for_job_type(cls, job_type: JobType) -> RetryRule:
        return cls._BY_JOB_TYPE.get(job_type, cls.TRANSPORT_SEARCH)
