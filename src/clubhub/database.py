"""SQLite Database manager and data access layer for ClubHub."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import aiosqlite


class DatabaseManager:
    """Manages SQLite operations asynchronously using aiosqlite."""

    def __init__(self, db_path: str = "clubhub.db"):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Establish database connection and initialize tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._init_schema()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _init_schema(self) -> None:
        """Create necessary tables if they do not exist."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            # Tickets Table
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    requester_id INTEGER NOT NULL,
                    requester_name TEXT NOT NULL,
                    category_key TEXT NOT NULL,
                    category_name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    handling_role_id INTEGER,
                    review_message_id INTEGER,
                    review_channel_id INTEGER,
                    accepted_by_id INTEGER,
                    accepted_by_name TEXT,
                    accepted_at TEXT,
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    closed_by_id INTEGER,
                    outcome_reason TEXT,
                    discord_category_id INTEGER,
                    discord_text_channel_id INTEGER,
                    discord_voice_channel_id INTEGER,
                    control_message_id INTEGER,
                    last_activity_at TEXT NOT NULL,
                    warned_at TEXT
                )
                """
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_guild_requester ON tickets(guild_id, requester_id, status)"
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)"
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_text_ch ON tickets(discord_text_channel_id)"
            )

            # Ticket Counter per Guild (for formatted TICKET-0001 IDs)
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_counters (
                    guild_id INTEGER PRIMARY KEY,
                    last_ticket_number INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # Events Table
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    organizer_id INTEGER NOT NULL,
                    organizer_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    location TEXT NOT NULL,
                    audience TEXT NOT NULL DEFAULT 'public',
                    status TEXT NOT NULL DEFAULT 'draft',
                    channel_id INTEGER,
                    message_id INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Event RSVPs Table
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS event_rsvps (
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL,
                    response TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (event_id, user_id),
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
                )
                """
            )

            # Event Questions Table (Moderated Q&A Queue)
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS event_questions (
                    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
                )
                """
            )

            # Reminders Table
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    remind_at TEXT NOT NULL,
                    message TEXT NOT NULL,
                    is_activity INTEGER NOT NULL DEFAULT 0,
                    delivered INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # Google Sheets Offline Retry Queue
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sheets_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

        await self._connection.commit()

    # =========================================================================
    # Ticket Operations
    # =========================================================================

    async def get_next_ticket_id(self, guild_id: int, prefix: str = "TICKET") -> str:
        """Generate the next sequential ticket identifier for a guild."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO ticket_counters (guild_id, last_ticket_number)
                VALUES (?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET
                    last_ticket_number = last_ticket_number + 1
                RETURNING last_ticket_number
                """,
                (guild_id,),
            )
            row = await cursor.fetchone()
            num = row[0] if row else 1
            await self._connection.commit()
            return f"{prefix}-{num:04d}"

    async def has_active_or_pending_ticket(self, guild_id: int, requester_id: int) -> bool:
        """Check if a member has a pending or active ticket on the server.
        
        Per Section 9.3:
        Existing status:
        - Pending review: No other request allowed
        - Open: No other request allowed
        - Closing: No other request allowed
        - Closed: Yes (allowed)
        - Declined: Yes (allowed)
        """
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT 1 FROM tickets
                WHERE guild_id = ? AND requester_id = ? AND status IN ('pending_review', 'open', 'closing')
                LIMIT 1
                """,
                (guild_id, requester_id),
            )
            row = await cursor.fetchone()
            return row is not None

    async def create_ticket(
        self,
        ticket_id: str,
        guild_id: int,
        requester_id: int,
        requester_name: str,
        category_key: str,
        category_name: str,
        subject: str,
        description: str,
        review_channel_id: Optional[int] = None,
        review_message_id: Optional[int] = None,
        handling_role_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record a newly submitted ticket in 'pending_review' status."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO tickets (
                    ticket_id, guild_id, requester_id, requester_name,
                    category_key, category_name, subject, description,
                    status, review_channel_id, review_message_id, handling_role_id,
                    created_at, last_activity_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    guild_id,
                    requester_id,
                    requester_name,
                    category_key,
                    category_name,
                    subject,
                    description,
                    review_channel_id,
                    review_message_id,
                    handling_role_id,
                    now_iso,
                    now_iso,
                ),
            )
            await self._connection.commit()

        ticket = await self.get_ticket(ticket_id)
        assert ticket is not None
        return ticket

    async def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a ticket record by its ticket_id."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def get_ticket_by_text_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a ticket record by its active Discord text channel ID."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM tickets WHERE discord_text_channel_id = ? AND status IN ('open', 'closing')",
                (channel_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def get_ticket_by_review_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a ticket record by its review queue message ID."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM tickets WHERE review_message_id = ?", (message_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def accept_ticket_atomic(
        self,
        ticket_id: str,
        accepted_by_id: int,
        accepted_by_name: str,
        discord_category_id: int,
        discord_text_channel_id: int,
        discord_voice_channel_id: int,
        control_message_id: int,
    ) -> bool:
        """Atomically transition a ticket from 'pending_review' to 'open'.
        
        Returns True if successful, or False if another staff member already accepted or declined.
        """
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE tickets
                SET status = 'open',
                    accepted_by_id = ?,
                    accepted_by_name = ?,
                    accepted_at = ?,
                    discord_category_id = ?,
                    discord_text_channel_id = ?,
                    discord_voice_channel_id = ?,
                    control_message_id = ?,
                    last_activity_at = ?,
                    warned_at = NULL
                WHERE ticket_id = ? AND status = 'pending_review'
                """,
                (
                    accepted_by_id,
                    accepted_by_name,
                    now_iso,
                    discord_category_id,
                    discord_text_channel_id,
                    discord_voice_channel_id,
                    control_message_id,
                    now_iso,
                    ticket_id,
                ),
            )
            updated = cursor.rowcount > 0
            await self._connection.commit()
            return updated

    async def decline_ticket_atomic(
        self,
        ticket_id: str,
        declined_by_id: int,
        reason: str,
    ) -> bool:
        """Atomically decline a pending ticket."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE tickets
                SET status = 'declined',
                    closed_by_id = ?,
                    closed_at = ?,
                    outcome_reason = ?
                WHERE ticket_id = ? AND status = 'pending_review'
                """,
                (declined_by_id, now_iso, reason, ticket_id),
            )
            updated = cursor.rowcount > 0
            await self._connection.commit()
            return updated

    async def update_ticket_activity(self, ticket_id: str, timestamp: Optional[str] = None) -> None:
        """Reset the inactivity timestamp when human activity is detected."""
        assert self._connection is not None
        now_iso = timestamp or datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE tickets
                SET last_activity_at = ?,
                    warned_at = NULL
                WHERE ticket_id = ? AND status = 'open'
                """,
                (now_iso, ticket_id),
            )
            await self._connection.commit()

    async def set_ticket_warned(self, ticket_id: str, timestamp: Optional[str] = None) -> None:
        """Record that an inactivity warning has been posted to this ticket."""
        assert self._connection is not None
        now_iso = timestamp or datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE tickets SET warned_at = ? WHERE ticket_id = ?",
                (now_iso, ticket_id),
            )
            await self._connection.commit()

    async def clear_ticket_warned(self, ticket_id: str) -> None:
        """Clear warning status after a user selects Keep Open."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE tickets SET warned_at = NULL, last_activity_at = ? WHERE ticket_id = ?",
                (now_iso, ticket_id),
            )
            await self._connection.commit()

    async def mark_ticket_closing(self, ticket_id: str, closed_by_id: Optional[int], reason: str) -> bool:
        """Mark ticket status as 'closing' before deleting channels."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE tickets
                SET status = 'closing',
                    closed_by_id = ?,
                    outcome_reason = ?,
                    closed_at = ?
                WHERE ticket_id = ? AND status IN ('open', 'closing')
                """,
                (closed_by_id, reason, now_iso, ticket_id),
            )
            updated = cursor.rowcount > 0
            await self._connection.commit()
            return updated

    async def mark_ticket_closed(self, ticket_id: str) -> None:
        """Mark ticket status as 'closed' after channel deletion completes."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE tickets
                SET status = 'closed',
                    closed_at = COALESCE(closed_at, ?)
                WHERE ticket_id = ?
                """,
                (now_iso, ticket_id),
            )
            await self._connection.commit()

    async def get_active_tickets(self, guild_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve all currently open or closing tickets."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            if guild_id:
                await cursor.execute(
                    "SELECT * FROM tickets WHERE guild_id = ? AND status IN ('open', 'closing')",
                    (guild_id,),
                )
            else:
                await cursor.execute(
                    "SELECT * FROM tickets WHERE status IN ('open', 'closing')"
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_pending_tickets(self, guild_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve all pending review tickets."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            if guild_id:
                await cursor.execute(
                    "SELECT * FROM tickets WHERE guild_id = ? AND status = 'pending_review'",
                    (guild_id,),
                )
            else:
                await cursor.execute(
                    "SELECT * FROM tickets WHERE status = 'pending_review'"
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Events & RSVP Operations
    # =========================================================================

    async def create_event(
        self,
        guild_id: int,
        organizer_id: int,
        organizer_name: str,
        title: str,
        description: str,
        event_time: str,
        location: str,
        audience: str = "public",
        status: str = "draft",
    ) -> int:
        """Create a new event record."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO events (
                    guild_id, organizer_id, organizer_name, title, description,
                    event_time, location, audience, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    organizer_id,
                    organizer_name,
                    title,
                    description,
                    event_time,
                    location,
                    audience,
                    status,
                    now_iso,
                ),
            )
            event_id = cursor.lastrowid
            await self._connection.commit()
            assert event_id is not None
            return event_id

    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Fetch an event by event_id."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def publish_event(self, event_id: int, channel_id: int, message_id: int) -> bool:
        """Mark an event as published with its Discord message details."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE events
                SET status = 'published', channel_id = ?, message_id = ?
                WHERE event_id = ?
                """,
                (channel_id, message_id, event_id),
            )
            updated = cursor.rowcount > 0
            await self._connection.commit()
            return updated

    async def cancel_event(self, event_id: int) -> bool:
        """Mark an event as cancelled."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE events SET status = 'cancelled' WHERE event_id = ?",
                (event_id,),
            )
            updated = cursor.rowcount > 0
            await self._connection.commit()
            return updated

    async def set_rsvp(self, event_id: int, user_id: int, user_name: str, response: str) -> None:
        """Set or update a member's RSVP for an event."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO event_rsvps (event_id, user_id, user_name, response, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_id, user_id) DO UPDATE SET
                    response = excluded.response,
                    user_name = excluded.user_name,
                    updated_at = excluded.updated_at
                """,
                (event_id, user_id, user_name, response, now_iso),
            )
            await self._connection.commit()

    async def get_event_rsvps_summary(self, event_id: int) -> Dict[str, Any]:
        """Get summary count and participant list for an event's RSVPs."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "SELECT response, user_name FROM event_rsvps WHERE event_id = ?",
                (event_id,),
            )
            rows = await cursor.fetchall()
            summary: Dict[str, List[str]] = {"going": [], "maybe": [], "cant_attend": []}
            for row in rows:
                resp = row["response"]
                if resp in summary:
                    summary[resp].append(row["user_name"])
            return summary

    async def add_event_question(self, event_id: int, user_id: int, user_name: str, question: str) -> int:
        """Submit a question for an event into the moderation queue."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO event_questions (event_id, user_id, user_name, question, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (event_id, user_id, user_name, question, now_iso),
            )
            q_id = cursor.lastrowid
            await self._connection.commit()
            assert q_id is not None
            return q_id

    async def review_event_question(self, question_id: int, status: str, reviewer_id: int) -> bool:
        """Approve or reject a question from the moderation queue."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE event_questions
                SET status = ?, reviewed_by_id = ?
                WHERE question_id = ?
                """,
                (status, reviewer_id, question_id),
            )
            updated = cursor.rowcount > 0
            await self._connection.commit()
            return updated

    # =========================================================================
    # Reminders Operations
    # =========================================================================

    async def create_reminder(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        remind_at: str,
        message: str,
        is_activity: bool = False,
    ) -> int:
        """Create a scheduled reminder."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO reminders (guild_id, user_id, channel_id, remind_at, message, is_activity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, channel_id, remind_at, message, 1 if is_activity else 0),
            )
            r_id = cursor.lastrowid
            await self._connection.commit()
            assert r_id is not None
            return r_id

    async def get_due_reminders(self) -> List[Dict[str, Any]]:
        """Fetch all reminders whose scheduled time has passed and have not been delivered."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM reminders WHERE delivered = 0 AND remind_at <= ?",
                (now_iso,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def mark_reminder_delivered(self, reminder_id: int) -> None:
        """Mark a reminder as delivered."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE reminders SET delivered = 1 WHERE reminder_id = ?",
                (reminder_id,),
            )
            await self._connection.commit()

    # =========================================================================
    # Google Sheets Offline Retry Queue
    # =========================================================================

    async def enqueue_sheet_record(self, ticket_id: str, payload: Dict[str, Any]) -> int:
        """Enqueue a ticket outcome record for Google Sheets sync."""
        assert self._connection is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO sheets_queue (ticket_id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (ticket_id, json.dumps(payload), now_iso),
            )
            row_id = cursor.lastrowid
            await self._connection.commit()
            assert row_id is not None
            return row_id

    async def get_pending_sheet_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch pending records waiting to sync to Google Sheets."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM sheets_queue WHERE status = 'pending' AND attempts < 5 ORDER BY id ASC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_sheet_record_status(
        self, record_id: int, status: str, error: Optional[str] = None
    ) -> None:
        """Update retry count and status of a sheets queue record."""
        assert self._connection is not None
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE sheets_queue
                SET status = ?, attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (status, error, record_id),
            )
            await self._connection.commit()
