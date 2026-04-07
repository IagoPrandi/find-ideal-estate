from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def current_dataset_hash(conn: AsyncConnection, dataset_type: str) -> str | None:
    result = await conn.execute(
        text(
            """
            SELECT version_hash
            FROM dataset_versions
            WHERE dataset_type = :dataset_type
              AND is_current = TRUE
            LIMIT 1
            """
        ),
        {"dataset_type": dataset_type},
    )
    value = result.scalar_one_or_none()
    return str(value) if value else None


async def upsert_dataset_version(
    conn: AsyncConnection,
    *,
    dataset_type: str,
    version_hash: str,
    source_label: str,
    extra_meta: dict[str, Any] | None = None,
) -> None:
    meta = {"source_label": source_label}
    if extra_meta:
        meta.update(extra_meta)

    await conn.execute(
        text(
            "UPDATE dataset_versions SET is_current = FALSE WHERE dataset_type = :dataset_type"
        ),
        {"dataset_type": dataset_type},
    )
    await conn.execute(
        text(
            """
            INSERT INTO dataset_versions (dataset_type, version_hash, source_url, metadata, is_current)
            VALUES (:dataset_type, :version_hash, :source_label, CAST(:metadata AS jsonb), TRUE)
            ON CONFLICT (dataset_type, version_hash)
            DO UPDATE
               SET source_url = EXCLUDED.source_url,
                   imported_at = now(),
                   is_current = TRUE,
                   metadata = EXCLUDED.metadata
            """
        ),
        {
            "dataset_type": dataset_type,
            "version_hash": version_hash,
            "source_label": source_label,
            "metadata": __import__("json").dumps(meta, ensure_ascii=True, sort_keys=True),
        },
    )