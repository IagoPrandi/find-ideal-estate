"""enforce idempotent active jobs for canonical journey job types"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260329_0013"
down_revision = "20260329_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked_duplicates AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY journey_id, job_type
                    ORDER BY created_at DESC, id DESC
                ) AS row_num
            FROM jobs
            WHERE journey_id IS NOT NULL
              AND job_type IN ('transport_search', 'zone_generation', 'zone_enrichment')
              AND state IN ('pending', 'running', 'retrying')
        )
        UPDATE jobs
        SET state = 'cancelled',
            finished_at = COALESCE(finished_at, now()),
            error_message = COALESCE(
                error_message,
                'Superseded by newer active job during idempotency migration'
            )
        WHERE id IN (
            SELECT id
            FROM ranked_duplicates
            WHERE row_num > 1
        )
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_jobs_active_canonical_type_per_journey
        ON jobs (journey_id, job_type)
        WHERE journey_id IS NOT NULL
          AND job_type IN ('transport_search', 'zone_generation', 'zone_enrichment')
          AND state IN ('pending', 'running', 'retrying')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_jobs_active_canonical_type_per_journey")