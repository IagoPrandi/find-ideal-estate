from __future__ import annotations

from core.db import get_engine
from sqlalchemy import text

GLOBAL_USAGE_RESTRICTIONS_KEY = "usage_restrictions_disabled_globally"


async def get_global_usage_restrictions_disabled() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT value FROM app_settings WHERE key = :key LIMIT 1"),
            {"key": GLOBAL_USAGE_RESTRICTIONS_KEY},
        )
        row = result.mappings().first()
    if row is None:
        return False
    value = row["value"]
    return value is True or str(value).strip().lower() == "true"


async def set_global_usage_restrictions_disabled(disabled: bool) -> bool:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (
                    :key,
                    CASE WHEN :value THEN 'true'::jsonb ELSE 'false'::jsonb END,
                    now()
                )
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = now()
                """
            ),
            {"key": GLOBAL_USAGE_RESTRICTIONS_KEY, "value": disabled},
        )
    return disabled
