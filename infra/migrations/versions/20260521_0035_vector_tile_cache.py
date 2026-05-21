"""Add persistent vector tile cache.

Revision ID: 20260521_0035
Revises: 20260519_0034
Create Date: 2026-05-21 00:00:00.000000
"""

from alembic import op

revision = "20260521_0035"
down_revision = "20260519_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_tile_cache (
            layer_name text NOT NULL,
            z integer NOT NULL,
            x integer NOT NULL,
            y integer NOT NULL,
            cache_version text NOT NULL,
            tile bytea NOT NULL,
            byte_size integer NOT NULL,
            generated_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NULL,
            duration_ms integer NULL,
            CONSTRAINT pk_vector_tile_cache
                PRIMARY KEY (layer_name, z, x, y, cache_version),
            CONSTRAINT ck_vector_tile_cache_zoom
                CHECK (z >= 0 AND z <= 22),
            CONSTRAINT ck_vector_tile_cache_coords
                CHECK (x >= 0 AND y >= 0),
            CONSTRAINT ck_vector_tile_cache_byte_size
                CHECK (byte_size >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_vector_tile_cache_layer_generated
        ON vector_tile_cache (layer_name, generated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_vector_tile_cache_expires_at
        ON vector_tile_cache (expires_at)
        WHERE expires_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vector_tile_cache_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_vector_tile_cache_layer_generated")
    op.execute("DROP TABLE IF EXISTS vector_tile_cache")
