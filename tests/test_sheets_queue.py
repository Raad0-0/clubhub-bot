"""Unit tests for offline Google Sheets retry queue and reliability."""

import pytest
from clubhub.config import SheetsConfig
from clubhub.database import DatabaseManager
from clubhub.services.sheets import GoogleSheetsService


@pytest.mark.asyncio
async def test_sheets_offline_queue(tmp_path):
    """Reporting failures or disabled status must safely enqueue records without raising exceptions."""
    db_file = tmp_path / "sheets_test.db"
    db = DatabaseManager(str(db_file))
    await db.connect()

    cfg = SheetsConfig(enabled=False)
    service = GoogleSheetsService(config=cfg, db=db)

    ticket_data = {
        "ticket_id": "TICKET-0050",
        "requester_name": "Alice",
        "requester_id": 12345,
        "category_name": "General Assistance",
        "subject": "Question",
        "description": "Details",
        "created_at": "2026-10-19T00:00:00Z",
        "status": "closed",
        "outcome_reason": "Resolved",
    }

    # Should safely succeed without throwing any error
    await service.record_ticket_event(ticket_data, is_sensitive=False)

    # Verify record was stored in local SQLite retry queue
    pending = await db.get_pending_sheet_records()
    assert len(pending) == 1
    assert pending[0]["ticket_id"] == "TICKET-0050"
    assert pending[0]["status"] == "pending"

    # Simulate retry/error update
    rec_id = pending[0]["id"]
    await db.update_sheet_record_status(rec_id, status="pending", error="API Rate Limit")
    updated_records = await db.get_pending_sheet_records()
    assert updated_records[0]["attempts"] == 1
    assert updated_records[0]["last_error"] == "API Rate Limit"

    # Simulate success update
    await db.update_sheet_record_status(rec_id, status="synced")
    synced_records = await db.get_pending_sheet_records()
    assert len(synced_records) == 0

    await db.close()
