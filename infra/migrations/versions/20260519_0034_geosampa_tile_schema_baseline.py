"""Ensure GeoSampa tile tables exist for clean production databases.

Revision ID: 20260519_0034
Revises: 20260505_0033
Create Date: 2026-05-19
"""

from alembic import op


revision = "20260519_0034"
down_revision = "20260505_0033"
branch_labels = None
depends_on = None


def _ensure_table(table_name: str) -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGSERIAL PRIMARY KEY,
            geometry geometry(Geometry, 4326) NOT NULL
        )
        """
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{table_name}_geometry "
        f"ON {table_name} USING GIST (geometry)"
    )


def _add_text_columns(table_name: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column} TEXT")


def upgrade() -> None:
    _ensure_table("geosampa_metro_stations")
    _add_text_columns("geosampa_metro_stations", ("nm_estacao_metro_trem",))

    _ensure_table("geosampa_trem_stations")
    _add_text_columns("geosampa_trem_stations", ("nm_estacao_metro_trem",))

    _ensure_table("geosampa_bus_stops")
    _add_text_columns("geosampa_bus_stops", ("nm_ponto_onibus",))

    _ensure_table("geosampa_bus_terminals")
    _add_text_columns("geosampa_bus_terminals", ("nm_terminal",))

    _ensure_table("geosampa_bus_corridors")
    _add_text_columns("geosampa_bus_corridors", ("nm_corredor",))

    _ensure_table("geosampa_metro_lines")
    _add_text_columns("geosampa_metro_lines", ("nm_linha_metro_trem", "nr_nome_linha"))

    _ensure_table("geosampa_trem_lines")
    _add_text_columns("geosampa_trem_lines", ("nm_linha_metro_trem",))

    _ensure_table("geosampa_bus_lines")
    _add_text_columns("geosampa_bus_lines", ("ln_nome",))

    _ensure_table("geosampa_vegetacao_significativa")
    _add_text_columns("geosampa_vegetacao_significativa", ("ves_categ", "ves_bairro"))

    _ensure_table("geosampa_mancha_inundacao")
    _add_text_columns("geosampa_mancha_inundacao", ("nm_bacia_hidrografica", "cd_identificador"))


def downgrade() -> None:
    # Keep tables because they may be populated by ingestion jobs and are shared by
    # earlier routes. Dropping the metadata columns is enough for downgrade symmetry.
    for table_name, columns in (
        ("geosampa_metro_stations", ("nm_estacao_metro_trem",)),
        ("geosampa_trem_stations", ("nm_estacao_metro_trem",)),
        ("geosampa_bus_stops", ("nm_ponto_onibus",)),
        ("geosampa_bus_terminals", ("nm_terminal",)),
        ("geosampa_bus_corridors", ("nm_corredor",)),
        ("geosampa_metro_lines", ("nm_linha_metro_trem", "nr_nome_linha")),
        ("geosampa_trem_lines", ("nm_linha_metro_trem",)),
        ("geosampa_bus_lines", ("ln_nome",)),
        ("geosampa_vegetacao_significativa", ("ves_categ", "ves_bairro")),
        ("geosampa_mancha_inundacao", ("nm_bacia_hidrografica", "cd_identificador")),
    ):
        for column in columns:
            op.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column}")
