"""Unit and integration tests for SQLite DatabaseManager."""

import pytest
from clubhub.database import DatabaseManager


@pytest.fixture
async def db(tmp_path):
    db_file = tmp_path / "test_clubhub.db"
    manager = DatabaseManager(str(db_file))
    await manager.connect()
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_sequential_ticket_ids(db):
    """Ticket IDs must increment sequentially with formatted prefixes."""
    id1 = await db.get_next_ticket_id(guild_id=123)
    id2 = await db.get_next_ticket_id(guild_id=123)
    id3 = await db.get_next_ticket_id(guild_id=123)

    assert id1 == "TICKET-0001"
    assert id2 == "TICKET-0002"
    assert id3 == "TICKET-0003"


@pytest.mark.asyncio
async def test_one_ticket_per_member_policy(db):
    """Section 9.3: Each member may have only one pending or active ticket per server."""
    guild_id = 100
    user_id = 555

    # Initially allowed
    assert not await db.has_active_or_pending_ticket(guild_id, user_id)

    # 1. Member submits a ticket -> Pending review
    await db.create_ticket(
        ticket_id="TICKET-0001",
        guild_id=guild_id,
        requester_id=user_id,
        requester_name="TestUser#1234",
        category_key="general_assistance",
        category_name="General Assistance",
        subject="Need help",
        description="Help description",
    )

    # Blocked while pending review
    assert await db.has_active_or_pending_ticket(guild_id, user_id)

    # 2. Staff accepts -> Open
    await db.accept_ticket_atomic(
        ticket_id="TICKET-0001",
        accepted_by_id=999,
        accepted_by_name="StaffMember#0001",
        discord_category_id=10,
        discord_text_channel_id=11,
        discord_voice_channel_id=12,
        control_message_id=13,
    )

    # Still blocked while open
    assert await db.has_active_or_pending_ticket(guild_id, user_id)

    # 3. Ticket is closing
    await db.mark_ticket_closing(
        ticket_id="TICKET-0001",
        closed_by_id=999,
        reason="Resolved",
    )

    # Still blocked while closing
    assert await db.has_active_or_pending_ticket(guild_id, user_id)

    # 4. Ticket is fully closed
    await db.mark_ticket_closed("TICKET-0001")

    # Member is now unblocked and can submit another request!
    assert not await db.has_active_or_pending_ticket(guild_id, user_id)


@pytest.mark.asyncio
async def test_declined_ticket_unblocks_member(db):
    """Declined tickets must immediately unblock the member for future submissions."""
    guild_id = 101
    user_id = 666

    await db.create_ticket(
        ticket_id="TICKET-0002",
        guild_id=guild_id,
        requester_id=user_id,
        requester_name="AnotherUser#5678",
        category_key="private_concern",
        category_name="Complaint",
        subject="Complaint",
        description="Private issue",
    )

    assert await db.has_active_or_pending_ticket(guild_id, user_id)

    # Decline ticket
    success = await db.decline_ticket_atomic(
        ticket_id="TICKET-0002",
        declined_by_id=888,
        reason="Please use appropriate forum",
    )
    assert success is True

    # Member is now allowed to submit another ticket
    assert not await db.has_active_or_pending_ticket(guild_id, user_id)


@pytest.mark.asyncio
async def test_atomic_acceptance_concurrency(db):
    """Only one staff member can successfully accept a ticket, preventing duplicate ticket spaces."""
    guild_id = 102
    await db.create_ticket(
        ticket_id="TICKET-0003",
        guild_id=guild_id,
        requester_id=777,
        requester_name="User#7777",
        category_key="general_assistance",
        category_name="General Assistance",
        subject="Concurrency test",
        description="Testing race conditions",
    )

    # First staff acceptance succeeds
    first_accept = await db.accept_ticket_atomic(
        ticket_id="TICKET-0003",
        accepted_by_id=1,
        accepted_by_name="Staff1",
        discord_category_id=101,
        discord_text_channel_id=102,
        discord_voice_channel_id=103,
        control_message_id=104,
    )
    assert first_accept is True

    # Concurrent second acceptance attempt fails!
    second_accept = await db.accept_ticket_atomic(
        ticket_id="TICKET-0003",
        accepted_by_id=2,
        accepted_by_name="Staff2",
        discord_category_id=201,
        discord_text_channel_id=202,
        discord_voice_channel_id=203,
        control_message_id=204,
    )
    assert second_accept is False


@pytest.mark.asyncio
async def test_events_and_rsvps(db):
    """Test event creation, publishing, and member RSVP tracking."""
    event_id = await db.create_event(
        guild_id=200,
        organizer_id=50,
        organizer_name="Organizer#1",
        title="Weekly Workshop",
        description="Python bot development",
        event_time="2026-11-05 18:00 UTC",
        location="Room 101",
    )

    event = await db.get_event(event_id)
    assert event["title"] == "Weekly Workshop"
    assert event["status"] == "draft"

    # Set RSVPs
    await db.set_rsvp(event_id, user_id=1, user_name="Alice", response="going")
    await db.set_rsvp(event_id, user_id=2, user_name="Bob", response="maybe")
    await db.set_rsvp(event_id, user_id=3, user_name="Charlie", response="cant_attend")

    summary = await db.get_event_rsvps_summary(event_id)
    assert "Alice" in summary["going"]
    assert "Bob" in summary["maybe"]
    assert "Charlie" in summary["cant_attend"]

    # Alice changes RSVP to maybe
    await db.set_rsvp(event_id, user_id=1, user_name="Alice", response="maybe")
    updated_summary = await db.get_event_rsvps_summary(event_id)
    assert len(updated_summary["going"]) == 0
    assert "Alice" in updated_summary["maybe"]


@pytest.mark.asyncio
async def test_single_channel_ticket_mode(db):
    """Test acceptance and closure with only a single text channel (no category, no VC)."""
    guild_id = 300
    user_id = 999

    await db.create_ticket(
        ticket_id="TICKET-0100",
        guild_id=guild_id,
        requester_id=user_id,
        requester_name="SoloUser",
        category_key="general_assistance",
        category_name="General Assistance",
        subject="Channel Only Test",
        description="Testing without dedicated category or VC",
    )

    success = await db.accept_ticket_atomic(
        ticket_id="TICKET-0100",
        accepted_by_id=10,
        accepted_by_name="SupportStaff",
        discord_category_id=None,
        discord_text_channel_id=8888,
        discord_voice_channel_id=None,
        control_message_id=9999,
    )
    assert success is True

    ticket = await db.get_ticket("TICKET-0100")
    assert ticket["status"] == "open"
    assert ticket["discord_category_id"] is None
    assert ticket["discord_voice_channel_id"] is None
    assert ticket["discord_text_channel_id"] == 8888

    # Lookup by text channel works
    found = await db.get_ticket_by_text_channel(8888)
    assert found is not None
    assert found["ticket_id"] == "TICKET-0100"
