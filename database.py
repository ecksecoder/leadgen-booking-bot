"""Database management module for LeadGen & Booking Bot.

This module provides SQLite connection pooling with Write-Ahead Logging (WAL)
enforcement, asynchronous schema initialization, self-healing automated migrations,
and async-safe lead lifecycle management via thread executor delegation.
"""

import asyncio
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

logger = logging.getLogger(__name__)

# Default database path resolved relative to the project root
DEFAULT_DB_PATH: str = os.getenv("DB_PATH", "leads.db")


def _get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create and configure a SQLite connection with WAL journal mode.

    Enforces WAL (Write-Ahead Logging), NORMAL synchronization, foreign key
    constraints, and a 10-second busy timeout to handle concurrent access safely.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Returns:
        sqlite3.Connection: A configured SQLite database connection instance.

    Raises:
        sqlite3.Error: If the connection fails or PRAGMA execution encounters an error.
    """
    db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        database=str(db_file),
        timeout=10.0,
    )
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    try:
        # Enforce WAL mode for non-blocking concurrent reads and writes
        cursor.execute("PRAGMA journal_mode=WAL;")
        journal_mode = cursor.fetchone()[0]

        # Recommended balance between performance and durability in WAL mode
        cursor.execute("PRAGMA synchronous=NORMAL;")

        # Set 5000ms busy timeout to prevent database locked errors during write concurrency
        cursor.execute("PRAGMA busy_timeout=5000;")

        # Enforce referential integrity
        cursor.execute("PRAGMA foreign_keys=ON;")

        logger.debug(
            "SQLite connection opened for '%s' (journal_mode=%s)",
            db_file.name,
            journal_mode,
        )
    finally:
        cursor.close()

    return conn


@contextmanager
def get_db_context(
    db_path: str = DEFAULT_DB_PATH,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for managing SQLite connection lifecycle and transactions.

    Yields:
        sqlite3.Connection: Active database connection.

    Ensures:
        Transaction commits on successful exit or rollbacks on exception,
        followed by safe connection closure.
    """
    conn = _get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("Database transaction rolled back due to error: %s", exc)
        raise
    finally:
        conn.close()


def _sync_init_db(db_path: str) -> None:
    """Synchronously initialize SQLite database tables and apply self-healing migrations.

    Creates the leads table if not present, inspects existing table columns
    via PRAGMA table_info(), and automatically executes ALTER TABLE ADD COLUMN
    for new fields (comment, context_tag, status, updated_at).

    Args:
        db_path: Target SQLite database file path.
    """
    logger.info("Initializing database schema at '%s'...", db_path)
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()

        # Create table with comprehensive schema for fresh installations
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                service TEXT NOT NULL,
                client_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                comment TEXT,
                context_tag TEXT,
                status TEXT DEFAULT 'NEW',
                created_at TIMESTAMP NOT NULL,
                updated_at TEXT
            );
            """
        )

        # Inspect current columns for self-healing schema migration
        cursor.execute("PRAGMA table_info(leads);")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        required_columns: Dict[str, str] = {
            "comment": "TEXT",
            "context_tag": "TEXT",
            "status": "TEXT DEFAULT 'NEW'",
            "updated_at": "TEXT",
        }

        for col_name, col_def in required_columns.items():
            if col_name not in existing_columns:
                logger.info(
                    "Self-healing database: adding missing column '%s' (%s) to leads table.",
                    col_name,
                    col_def,
                )
                cursor.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def};")

        # Backfill status for existing legacy rows if NULL
        cursor.execute("UPDATE leads SET status = 'NEW' WHERE status IS NULL;")

        # Ensure performance indexes exist
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);"
        )
        cursor.close()

    logger.info("Database schema initialized and self-healed successfully with WAL mode.")


def _sync_save_lead(
    user_id: int,
    username: Optional[str],
    service: str,
    client_name: str,
    phone_number: str,
    comment: Optional[str] = None,
    context_tag: Optional[str] = None,
    status: str = "NEW",
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Synchronously insert a new lead record into the database.

    Args:
        user_id: Telegram user ID.
        username: Telegram username handle (if available).
        service: Selected service package or category.
        client_name: Client full name provided during onboarding.
        phone_number: Client contact telephone number.
        comment: Optional client commentary or project context.
        context_tag: Categorization tag derived from triage (e.g., 'URGENT_VIP').
        status: Initial lifecycle status (defaults to 'NEW').
        db_path: Target database file path.

    Returns:
        int: The auto-generated primary key ID of the inserted lead record.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    updated_at = created_at
    query = """
        INSERT INTO leads (
            user_id, username, service, client_name, phone_number,
            comment, context_tag, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            query,
            (
                user_id,
                username,
                service,
                client_name,
                phone_number,
                comment,
                context_tag,
                status,
                created_at,
                updated_at,
            ),
        )
        lead_id = cursor.lastrowid
        cursor.close()

    if lead_id is None:
        raise RuntimeError("Failed to retrieve generated row ID for new lead record.")

    logger.info(
        "Lead successfully persisted: ID=%d, user_id=%d, service='%s', tag='%s', status='%s'",
        lead_id,
        user_id,
        service,
        context_tag,
        status,
    )
    return lead_id


def _sync_get_lead_by_id(
    lead_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Synchronously retrieve a lead record by primary key.

    Args:
        lead_id: Primary key ID of the lead.
        db_path: Target database file path.

    Returns:
        Optional[Dict[str, Any]]: Lead row represented as dictionary, or None.
    """
    query = """
        SELECT id, user_id, username, service, client_name, phone_number,
               comment, context_tag, status, created_at, updated_at
        FROM leads
        WHERE id = ?;
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (lead_id,))
        row = cursor.fetchone()
        cursor.close()

    if row is None:
        return None
    return dict(row)


def _sync_get_active_lead_by_user(
    user_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Synchronously retrieve the most recent active lead for a given user.

    Active leads possess status in ('NEW', 'IN_PROGRESS', 'CONFIRMED').

    Args:
        user_id: Telegram user ID.
        db_path: Target database file path.

    Returns:
        Optional[Dict[str, Any]]: Lead dictionary if active booking exists, else None.
    """
    query = """
        SELECT id, user_id, username, service, client_name, phone_number,
               comment, context_tag, status, created_at, updated_at
        FROM leads
        WHERE user_id = ? AND status IN ('NEW', 'IN_PROGRESS', 'CONFIRMED')
        ORDER BY id DESC
        LIMIT 1;
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (user_id,))
        row = cursor.fetchone()
        cursor.close()

    if row is None:
        return None
    return dict(row)


def _sync_update_lead_status(
    lead_id: int,
    new_status: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Synchronously update the lifecycle status and timestamp of a lead record.

    Args:
        lead_id: Primary key ID of the lead.
        new_status: New status string (e.g., 'CONFIRMED', 'IN_PROGRESS', 'REJECTED', 'CANCELLED').
        db_path: Target database file path.

    Returns:
        bool: True if a row was updated, False otherwise.
    """
    updated_at = datetime.now(timezone.utc).isoformat()
    query = """
        UPDATE leads
        SET status = ?, updated_at = ?
        WHERE id = ?;
    """
    with get_db_context(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (new_status, updated_at, lead_id))
        updated = cursor.rowcount > 0
        cursor.close()

    logger.info(
        "Lead status update in SQLite: ID=%d, new_status='%s', success=%s",
        lead_id,
        new_status,
        updated,
    )
    return updated


async def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Asynchronously initialize the database schema without blocking the event loop.

    Delegates synchronous I/O execution to an async worker thread.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """
    await asyncio.to_thread(_sync_init_db, db_path)


async def save_lead(
    user_id: int,
    username: Optional[str],
    service: str,
    client_name: str,
    phone_number: str,
    comment: Optional[str] = None,
    context_tag: Optional[str] = None,
    status: str = "NEW",
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Asynchronously persist a new lead record to the SQLite database.

    Safely offloads synchronous database operations to an executor thread,
    guaranteeing non-blocking execution in aiogram handlers.

    Args:
        user_id: Telegram user ID.
        username: Telegram username (without @) or None.
        service: Name of the selected service.
        client_name: Full name provided by the user.
        phone_number: Phone number provided by the user.
        comment: Optional client commentary or task description.
        context_tag: Categorization tag ('URGENT_VIP', 'PRICE_INQUIRY', etc.).
        status: Initial lead status (default 'NEW').
        db_path: Target SQLite database file path.

    Returns:
        int: The newly generated ID of the persisted lead.
    """
    return await asyncio.to_thread(
        _sync_save_lead,
        user_id,
        username,
        service,
        client_name,
        phone_number,
        comment,
        context_tag,
        status,
        db_path,
    )


async def get_lead_by_id(
    lead_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Asynchronously fetch a lead record by ID without blocking the event loop.

    Args:
        lead_id: Primary key ID of the lead.
        db_path: Target database file path.

    Returns:
        Optional[Dict[str, Any]]: Lead dictionary or None if not found.
    """
    return await asyncio.to_thread(_sync_get_lead_by_id, lead_id, db_path)


async def get_active_lead_by_user(
    user_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Asynchronously retrieve active lead for a user without blocking the event loop.

    Active leads are those in status ('NEW', 'IN_PROGRESS', 'CONFIRMED').

    Args:
        user_id: Telegram user ID.
        db_path: Target database file path.

    Returns:
        Optional[Dict[str, Any]]: Lead dictionary or None if no active booking exists.
    """
    return await asyncio.to_thread(_sync_get_active_lead_by_user, user_id, db_path)


async def update_lead_status(
    lead_id: int,
    new_status: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Asynchronously update the lifecycle status of a lead record.

    Args:
        lead_id: Primary key ID of the lead.
        new_status: New status string (e.g., 'CONFIRMED', 'IN_PROGRESS', 'REJECTED', 'CANCELLED').
        db_path: Target database file path.

    Returns:
        bool: True if updated, False otherwise.
    """
    return await asyncio.to_thread(
        _sync_update_lead_status,
        lead_id,
        new_status,
        db_path,
    )


async def cancel_active_lead(
    lead_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Asynchronously cancel an active lead record by setting its status to 'CANCELLED'.

    Args:
        lead_id: Primary key ID of the lead to cancel.
        db_path: Target database file path.

    Returns:
        bool: True if the lead was successfully cancelled, False otherwise.
    """
    return await update_lead_status(lead_id, "CANCELLED", db_path)


def get_user_bookings(user_id: int, db_path: str = DEFAULT_DB_PATH) -> List[sqlite3.Row]:
    """Retrieve all bookings for a specific user with WAL compliance.

    Args:
        user_id: Telegram user ID.
        db_path: Target database file path.

    Returns:
        List[sqlite3.Row]: List of row records for the user's bookings.
    """
    query = """
        SELECT id, user_id, service, service AS service_type, client_name,
               phone_number, comment, context_tag, status, created_at, updated_at
        FROM leads
        WHERE user_id = ?
        ORDER BY created_at DESC;
    """
    try:
        with get_db_context(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()
            cursor.close()
            return rows
    except Exception as exc:
        logger.error(
            "Failed to retrieve bookings for user %d: %s",
            user_id,
            exc,
            exc_info=True,
        )
        return []


def delete_booking(
    booking_id: int,
    user_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Delete a booking by ID, ensuring it belongs to the requesting user.

    Args:
        booking_id: Primary key ID of the booking to delete.
        user_id: Telegram user ID requesting the cancellation.
        db_path: Target database file path.

    Returns:
        bool: True if the booking was found and deleted, False otherwise.
    """
    query = "DELETE FROM leads WHERE id = ? AND user_id = ?;"
    try:
        with get_db_context(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (booking_id, user_id))
            deleted = cursor.rowcount > 0
            cursor.close()
            logger.info(
                "Booking deletion result: ID=%d, user_id=%d, success=%s",
                booking_id,
                user_id,
                deleted,
            )
            return deleted
    except Exception as exc:
        logger.error(
            "Failed to delete booking ID %d for user %d: %s",
            booking_id,
            user_id,
            exc,
            exc_info=True,
        )
        return False
