from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from contracts import (
    AuthGoogleLoginRequest,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthStatusRead,
    AuthUserRead,
)
from core.config import get_settings
from core.db import get_engine
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from modules.journeys.service import get_journey_for_access
from sqlalchemy import text

AUTH_SESSION_COOKIE = "auth_session"
AUTH_SESSION_TTL_DAYS = 30
PASSWORD_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_DISPLAY_NAME_LENGTH = 120
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(frozen=True)
class AuthenticatedSession:
    user: AuthUserRead
    expires_at: datetime


@dataclass(frozen=True)
class RequestAuthContext:
    user: AuthUserRead | None
    session_expires_at: datetime | None
    session_token: str | None
    anonymous_session_id: str | None


@dataclass(frozen=True)
class GoogleIdentityClaims:
    subject: str
    email: str
    display_name: str | None


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def default_session_expiration() -> datetime:
    return _utc_now() + timedelta(days=AUTH_SESSION_TTL_DAYS)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or len(normalized) > 320 or not _EMAIL_PATTERN.match(normalized):
        raise ValueError("Informe um e-mail válido.")
    return normalized


def _normalize_display_name(display_name: str | None) -> str | None:
    if display_name is None:
        return None
    normalized = display_name.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError("O nome exibido é muito longo.")
    return normalized


def _verify_google_credential_sync(credential: str, *, client_id: str) -> GoogleIdentityClaims:
    token = credential.strip()
    if not token:
        raise ValueError("Token do Google não informado.")

    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            google_auth_requests.Request(),
            client_id,
        )
    except ValueError as exc:
        raise ValueError("Login com Google inválido.") from exc

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise ValueError("Emissor do login Google inválido.")
    if claims.get("aud") != client_id:
        raise ValueError("Login Google emitido para outro aplicativo.")
    if claims.get("email_verified") is not True:
        raise ValueError("O e-mail da conta Google precisa estar verificado.")

    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip()
    if not subject:
        raise ValueError("Login Google sem identificador de usuário.")

    return GoogleIdentityClaims(
        subject=subject,
        email=_normalize_email(email),
        display_name=_normalize_display_name(str(claims.get("name") or "") or None),
    )


async def _verify_google_credential(credential: str) -> GoogleIdentityClaims:
    client_id = (get_settings().google_client_id or "").strip()
    if not client_id:
        raise ValueError("Login com Google não está configurado neste ambiente.")
    return await asyncio.to_thread(_verify_google_credential_sync, credential, client_id=client_id)


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("A senha excede o limite permitido.")


def _hash_password(password: str, *, salt: str | None = None) -> str:
    _validate_password(password)
    salt_value = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt_value}${derived.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations_raw, salt, expected_hash = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_raw)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(derived, expected_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_user(row) -> AuthUserRead:
    return AuthUserRead(
        id=row["id"],
        email=row["email"],
        display_name=row.get("display_name"),
        is_active=row["is_active"],
        created_at=row["created_at"],
        role=row.get("role", "user") or "user",
    )


def build_auth_status(context: RequestAuthContext) -> AuthStatusRead:
    return AuthStatusRead(
        is_authenticated=context.user is not None,
        user=context.user,
        session_expires_at=context.session_expires_at,
    )


async def get_user_by_email(email: str) -> tuple[AuthUserRead, str | None] | None:
    normalized_email = _normalize_email(email)
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, email, display_name, is_active, created_at, role, password_hash
                FROM users
                WHERE lower(email) = :email
                LIMIT 1
                """
            ),
            {"email": normalized_email},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_user(row), row.get("password_hash")


async def _get_user_row_by_email(conn, email: str):
    return (
        await conn.execute(
            text(
                """
                SELECT
                    id, email, display_name, is_active, created_at, role,
                    password_hash, google_subject
                FROM users
                WHERE lower(email) = :email
                LIMIT 1
                """
            ),
            {"email": email},
        )
    ).mappings().first()


async def _get_user_row_by_google_subject(conn, subject: str):
    return (
        await conn.execute(
            text(
                """
                SELECT
                    id, email, display_name, is_active, created_at, role,
                    password_hash, google_subject
                FROM users
                WHERE google_subject = :google_subject
                LIMIT 1
                """
            ),
            {"google_subject": subject},
        )
    ).mappings().first()


async def _migrate_anonymous_state(conn, *, user_id: UUID, anonymous_session_id: str | None) -> None:
    if not anonymous_session_id:
        return
    await conn.execute(
        text(
            """
            UPDATE journeys
            SET user_id = :user_id,
                anonymous_session_id = NULL,
                updated_at = now()
            WHERE anonymous_session_id = :anonymous_session_id
              AND user_id IS NULL
            """
        ),
        {
            "user_id": user_id,
            "anonymous_session_id": anonymous_session_id,
        },
    )
    await conn.execute(
        text(
            """
            UPDATE listing_search_requests
            SET user_id = :user_id
            WHERE session_id = :anonymous_session_id
              AND user_id IS NULL
            """
        ),
        {
            "user_id": user_id,
            "anonymous_session_id": anonymous_session_id,
        },
    )


async def _create_session(conn, *, user_id: UUID) -> tuple[str, datetime]:
    session_token = generate_session_token()
    expires_at = default_session_expiration()
    await conn.execute(
        text(
            """
            INSERT INTO user_sessions (user_id, token_hash, expires_at)
            VALUES (:user_id, :token_hash, :expires_at)
            """
        ),
        {
            "user_id": user_id,
            "token_hash": hash_session_token(session_token),
            "expires_at": expires_at,
        },
    )
    return session_token, expires_at


async def _activate_free_plan(conn, *, user_id: UUID) -> None:
    plan_result = await conn.execute(
        text("SELECT id, monthly_credits FROM plans WHERE slug = 'free' AND is_active = true LIMIT 1")
    )
    plan_row = plan_result.mappings().first()
    if plan_row is None:
        return

    plan_id = plan_row["id"]
    monthly_credits = plan_row["monthly_credits"]

    await conn.execute(
        text("""
            INSERT INTO plan_activations (user_id, plan_id, source_payment_id, status, started_at, ends_at)
            VALUES (:user_id, :plan_id, NULL, 'active', now(), now() + interval '30 days')
            ON CONFLICT DO NOTHING
        """),
        {"user_id": user_id, "plan_id": plan_id},
    )

    await conn.execute(
        text("""
            INSERT INTO user_credits (user_id, plan_id, cycle_credits, monthly_quota, cycle_started_at, cycle_ends_at)
            VALUES (:user_id, :plan_id, :credits, :credits, now(), now() + interval '30 days')
            ON CONFLICT (user_id) DO NOTHING
        """),
        {"user_id": user_id, "plan_id": plan_id, "credits": monthly_credits},
    )

    balance_result = await conn.execute(
        text("SELECT cycle_credits + rollover_balance + legacy_balance AS total FROM user_credits WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    balance_after = balance_result.scalar() or monthly_credits

    await conn.execute(
        text("""
            INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
            VALUES (:user_id, 'cycle', :delta, 'signup_grant_free', NULL, :balance_after)
        """),
        {"user_id": user_id, "delta": monthly_credits, "balance_after": balance_after},
    )


async def register_user(
    payload: AuthRegisterRequest,
    *,
    anonymous_session_id: str | None,
) -> tuple[AuthUserRead, str, datetime]:
    normalized_email = _normalize_email(payload.email)
    display_name = _normalize_display_name(payload.display_name)
    password_hash = _hash_password(payload.password)

    existing = await get_user_by_email(normalized_email)
    if existing is not None:
        raise ValueError("Já existe uma conta com este e-mail.")

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO users (
                    id,
                    email,
                    display_name,
                    password_hash,
                    password_updated_at,
                    is_active,
                    is_superuser,
                    created_at,
                    updated_at
                )
                VALUES (
                    gen_random_uuid(),
                    :email,
                    :display_name,
                    :password_hash,
                    now(),
                    true,
                    false,
                    now(),
                    now()
                )
                RETURNING id, email, display_name, is_active, created_at, role
                """
            ),
            {
                "email": normalized_email,
                "display_name": display_name,
                "password_hash": password_hash,
            },
        )
        row = result.mappings().one()
        user = _row_to_user(row)
        await _migrate_anonymous_state(conn, user_id=user.id, anonymous_session_id=anonymous_session_id)
        await _activate_free_plan(conn, user_id=user.id)
        session_token, expires_at = await _create_session(conn, user_id=user.id)

    if anonymous_session_id:
        from core.redis import get_redis
        redis = get_redis()
        await redis.delete(f"credit:session:{anonymous_session_id}")

    return user, session_token, expires_at


async def login_user(
    payload: AuthLoginRequest,
    *,
    anonymous_session_id: str | None,
) -> tuple[AuthUserRead, str, datetime]:
    record = await get_user_by_email(payload.email)
    if record is None:
        raise ValueError("E-mail ou senha inválidos.")

    user, password_hash = record
    if not user.is_active or not verify_password(payload.password, password_hash):
        raise ValueError("E-mail ou senha inválidos.")

    engine = get_engine()
    async with engine.begin() as conn:
        await _migrate_anonymous_state(conn, user_id=user.id, anonymous_session_id=anonymous_session_id)
        session_token, expires_at = await _create_session(conn, user_id=user.id)

    return user, session_token, expires_at


async def login_google_user(
    payload: AuthGoogleLoginRequest,
    *,
    anonymous_session_id: str | None,
) -> tuple[AuthUserRead, str, datetime]:
    claims = await _verify_google_credential(payload.credential)

    engine = get_engine()
    created_user = False
    async with engine.begin() as conn:
        row = await _get_user_row_by_google_subject(conn, claims.subject)

        if row is None:
            row = await _get_user_row_by_email(conn, claims.email)
            if row is not None and row.get("google_subject") not in (None, claims.subject):
                raise ValueError("Esta conta já está vinculada a outro login Google.")

            if row is not None:
                if not row["is_active"]:
                    raise ValueError("Conta inativa.")
                update_result = await conn.execute(
                    text(
                        """
                        UPDATE users
                        SET google_subject = :google_subject,
                            email_verified_at = COALESCE(email_verified_at, now()),
                            display_name = COALESCE(display_name, :display_name),
                            updated_at = now()
                        WHERE id = :user_id
                        RETURNING
                            id, email, display_name, is_active, created_at,
                            role, password_hash, google_subject
                        """
                    ),
                    {
                        "google_subject": claims.subject,
                        "display_name": claims.display_name,
                        "user_id": row["id"],
                    },
                )
                row = update_result.mappings().one()
            else:
                insert_result = await conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            id,
                            email,
                            display_name,
                            password_hash,
                            password_updated_at,
                            google_subject,
                            email_verified_at,
                            is_active,
                            is_superuser,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            gen_random_uuid(),
                            :email,
                            :display_name,
                            NULL,
                            NULL,
                            :google_subject,
                            now(),
                            true,
                            false,
                            now(),
                            now()
                        )
                        RETURNING
                            id, email, display_name, is_active, created_at,
                            role, password_hash, google_subject
                        """
                    ),
                    {
                        "email": claims.email,
                        "display_name": claims.display_name,
                        "google_subject": claims.subject,
                    },
                )
                row = insert_result.mappings().one()
                created_user = True

        if not row["is_active"]:
            raise ValueError("Conta inativa.")

        user = _row_to_user(row)
        await _migrate_anonymous_state(
            conn,
            user_id=user.id,
            anonymous_session_id=anonymous_session_id,
        )
        if created_user:
            await _activate_free_plan(conn, user_id=user.id)
        session_token, expires_at = await _create_session(conn, user_id=user.id)

    if anonymous_session_id:
        from core.redis import get_redis
        redis = get_redis()
        await redis.delete(f"credit:session:{anonymous_session_id}")

    return user, session_token, expires_at


async def get_authenticated_session_by_token(token: str) -> AuthenticatedSession | None:
    if not token:
        return None
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    u.id,
                    u.email,
                    u.display_name,
                    u.is_active,
                    u.created_at,
                    u.role,
                    s.expires_at
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = :token_hash
                LIMIT 1
                """
            ),
            {"token_hash": hash_session_token(token)},
        )
        row = result.mappings().first()
        if row is None:
            return None

        expires_at = row["expires_at"]
        if expires_at <= _utc_now():
            await conn.execute(
                text("DELETE FROM user_sessions WHERE token_hash = :token_hash"),
                {"token_hash": hash_session_token(token)},
            )
            return None

        await conn.execute(
            text(
                """
                UPDATE user_sessions
                SET last_seen_at = now()
                WHERE token_hash = :token_hash
                """
            ),
            {"token_hash": hash_session_token(token)},
        )

    return AuthenticatedSession(user=_row_to_user(row), expires_at=expires_at)


async def build_request_auth_context(
    *,
    session_token: str | None,
    anonymous_session_id: str | None,
) -> RequestAuthContext:
    authenticated = await get_authenticated_session_by_token(session_token) if session_token else None
    return RequestAuthContext(
        user=authenticated.user if authenticated else None,
        session_expires_at=authenticated.expires_at if authenticated else None,
        session_token=session_token,
        anonymous_session_id=anonymous_session_id,
    )


async def revoke_session_by_token(token: str | None) -> None:
    if not token:
        return
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM user_sessions WHERE token_hash = :token_hash"),
            {"token_hash": hash_session_token(token)},
        )


async def get_accessible_journey(journey_id: UUID, context: RequestAuthContext):
    return await get_journey_for_access(
        journey_id,
        user_id=context.user.id if context.user is not None else None,
        anonymous_session_id=context.anonymous_session_id,
    )
