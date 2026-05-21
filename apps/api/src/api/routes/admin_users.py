from __future__ import annotations

from typing import Any
from uuid import UUID

from api.routes.admin_common import require_developer
from contracts import (
    AdminUserRead,
    AdminUserRoleUpdateRequest,
    AdminUserScrapingPermissionUpdateRequest,
    AdminUsersRead,
)
from core.db import get_engine
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

router = APIRouter(prefix="/admin/users", tags=["admin"])

_ALLOWED_ROLES = {"user", "proprietario"}


def _row_to_admin_user(row: RowMapping) -> AdminUserRead:
    return AdminUserRead(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        is_active=row["is_active"],
        is_superuser=row["is_superuser"],
        can_start_immediate_scraping=row["can_start_immediate_scraping"],
        role=row["role"] or "user",
        created_at=row["created_at"],
    )


@router.get("", response_model=AdminUsersRead)
async def list_admin_users(
    q: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _ctx=Depends(require_developer),
) -> AdminUsersRead:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    clauses = ["true"]
    if q and q.strip():
        params["q"] = f"%{q.strip().lower()}%"
        clauses.append("(lower(email) LIKE :q OR lower(COALESCE(display_name, '')) LIKE :q)")
    if role and role.strip():
        if role not in _ALLOWED_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Função inválida.")
        params["role"] = role
        clauses.append("role = :role")

    where_sql = " AND ".join(clauses)
    engine = get_engine()
    async with engine.connect() as conn:
        total = await conn.execute(text(f"SELECT count(*) FROM users WHERE {where_sql}"), params)
        result = await conn.execute(
            text(
                f"""
                SELECT
                    id,
                    email,
                    display_name,
                    is_active,
                    is_superuser,
                    COALESCE(can_start_immediate_scraping, false) AS can_start_immediate_scraping,
                    role,
                    created_at
                FROM users
                WHERE {where_sql}
                ORDER BY created_at DESC, email ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        rows = result.mappings().all()
    return AdminUsersRead(
        items=[_row_to_admin_user(row) for row in rows],
        total_count=int(total.scalar_one()),
        limit=limit,
        offset=offset,
    )


@router.patch("/{user_id}/role", response_model=AdminUserRead)
async def update_admin_user_role(
    user_id: UUID,
    payload: AdminUserRoleUpdateRequest,
    _ctx=Depends(require_developer),
) -> AdminUserRead:
    if payload.role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Função inválida.")

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE users
                SET role = :role,
                    updated_at = now()
                WHERE id = :user_id
                RETURNING
                    id,
                    email,
                    display_name,
                    is_active,
                    is_superuser,
                    can_start_immediate_scraping,
                    role,
                    created_at
                """
            ),
            {"user_id": user_id, "role": payload.role},
        )
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return _row_to_admin_user(row)


@router.patch("/{user_id}/scraping-permission", response_model=AdminUserRead)
async def update_admin_user_scraping_permission(
    user_id: UUID,
    payload: AdminUserScrapingPermissionUpdateRequest,
    _ctx=Depends(require_developer),
) -> AdminUserRead:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE users
                SET can_start_immediate_scraping = :can_start_immediate_scraping,
                    updated_at = now()
                WHERE id = :user_id
                RETURNING
                    id,
                    email,
                    display_name,
                    is_active,
                    is_superuser,
                    can_start_immediate_scraping,
                    role,
                    created_at
                """
            ),
            {
                "user_id": user_id,
                "can_start_immediate_scraping": payload.can_start_immediate_scraping,
            },
        )
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return _row_to_admin_user(row)
