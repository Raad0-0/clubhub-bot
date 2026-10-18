"""Unit tests for automatic cleanup calculations and time duration parsing."""

import pytest
from datetime import datetime, timedelta, timezone
from clubhub.cogs.community_cog import parse_duration_to_seconds
from clubhub.database import DatabaseManager


def test_parse_duration():
    """Test duration parser supporting s, m, h, d."""
    assert parse_duration_to_seconds("30s") == 30
    assert parse_duration_to_seconds("15m") == 900
    assert parse_duration_to_seconds("2h") == 7200
    assert parse_duration_to_seconds("1d") == 86400
    assert parse_duration_to_seconds("invalid") is None
    assert parse_duration_to_seconds("") is None


@pytest.mark.asyncio
async def test_ticket_activity_and_warning_lifecycle(tmp_path):
    """Test updating activity, setting warnings, and clearing warnings via Keep Open."""
    db_file = tmp_path / "cleanup_test.db"
    db = DatabaseManager(str(db_file))
    await db.connect()

    ticket_id = "TICKET-9999"
    await db.create_ticket(
        ticket_id=ticket_id,
        guild_id=1,
        requester_id=2,
        requester_name="User",
        category_key="general",
        category_name="General",
        subject="Sub",
        description="Desc",
    )
    await db.accept_ticket_atomic(
        ticket_id=ticket_id,
        accepted_by_id=3,
        accepted_by_name="Staff",
        discord_category_id=4,
        discord_text_channel_id=5,
        discord_voice_channel_id=6,
        control_message_id=7,
    )

    t = await db.get_ticket(ticket_id)
    assert t["warned_at"] is None

    # Set warning
    warn_time = datetime.now(timezone.utc).isoformat()
    await db.set_ticket_warned(ticket_id, warn_time)
    t = await db.get_ticket(ticket_id)
    assert t["warned_at"] == warn_time

    # Member or staff clicks Keep Open -> clears warning and resets last_activity_at
    await db.clear_ticket_warned(ticket_id)
    t = await db.get_ticket(ticket_id)
    assert t["warned_at"] is None

    # Text message from human resets activity
    new_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    await db.update_ticket_activity(ticket_id, timestamp=new_time)
    t = await db.get_ticket(ticket_id)
    assert t["last_activity_at"] == new_time

    await db.close()
