"""Optional Google Sheets reporting integration with offline retry queue."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from clubhub.config import SheetsConfig
from clubhub.database import DatabaseManager

logger = logging.getLogger("clubhub.sheets")


class GoogleSheetsService:
    """Handles synchronization of ticket records to Google Sheets.
    
    Operates resiliently:
    - Never blocks ticket operations.
    - Queues records in SQLite when offline or unconfigured.
    - Synchronizes asynchronously in batches.
    """

    def __init__(self, config: SheetsConfig, db: DatabaseManager):
        self.config = config
        self.db = db
        self._service = None
        self._initialized = False

    def is_enabled(self) -> bool:
        return bool(self.config.enabled and self.config.spreadsheet_id)

    def _init_client(self) -> bool:
        if self._initialized:
            return self._service is not None

        if not self.is_enabled():
            return False

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_file = self.config.credentials_file
            if not creds_file:
                logger.warning("Google Sheets enabled but no credentials file provided.")
                return False

            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = service_account.Credentials.from_service_account_file(
                creds_file, scopes=scopes
            )
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            self._initialized = True
            logger.info("Successfully initialized Google Sheets API client.")
            return True
        except ImportError:
            logger.warning("google-api-python-client or google-auth not installed. Sheets reporting suspended.")
            self._initialized = True
            return False
        except Exception as e:
            logger.error(f"Error initializing Google Sheets client: {e}")
            return False

    async def record_ticket_event(self, ticket: Dict[str, Any], is_sensitive: bool = False) -> None:
        """Enqueue a ticket event for Google Sheets synchronization."""
        payload = {
            "ticket_id": ticket.get("ticket_id"),
            "requester_name": ticket.get("requester_name"),
            "requester_id": str(ticket.get("requester_id")),
            "category": ticket.get("category_name"),
            "subject": ticket.get("subject"),
            "description": ticket.get("description"),
            "requested_at": ticket.get("created_at"),
            "handling_role": str(ticket.get("handling_role_id") or ""),
            "accepted_by": ticket.get("accepted_by_name") or "",
            "accepted_by_id": str(ticket.get("accepted_by_id") or ""),
            "accepted_at": ticket.get("accepted_at") or "",
            "status": ticket.get("status"),
            "closed_at": ticket.get("closed_at") or "",
            "closed_by_id": str(ticket.get("closed_by_id") or ""),
            "outcome_reason": ticket.get("outcome_reason") or "",
            "is_sensitive": is_sensitive,
        }

        # Store in local SQLite retry queue first (Reliability rule: reporting failures never break support)
        await self.db.enqueue_sheet_record(ticket["ticket_id"], payload)

        if self.is_enabled():
            await self.process_queue()

    async def process_queue(self) -> None:
        """Process pending items in the SQLite retry queue."""
        if not self.is_enabled():
            return

        if not self._init_client() or self._service is None:
            return

        records = await self.db.get_pending_sheet_records(limit=10)
        if not records:
            return

        for rec in records:
            rec_id = rec["id"]
            try:
                payload = json.loads(rec["payload"])
                is_sensitive = payload.get("is_sensitive", False)
                worksheet = (
                    self.config.sensitive_worksheet
                    if is_sensitive
                    else self.config.support_worksheet
                )

                row_values = [
                    payload.get("ticket_id", ""),
                    payload.get("requester_name", ""),
                    payload.get("requester_id", ""),
                    payload.get("category", ""),
                    payload.get("subject", ""),
                    payload.get("requested_at", ""),
                    payload.get("handling_role", ""),
                    payload.get("accepted_by", ""),
                    payload.get("accepted_at", ""),
                    payload.get("status", ""),
                    payload.get("closed_at", ""),
                    payload.get("outcome_reason", ""),
                ]

                # Append row to Google Sheets
                body = {"values": [row_values]}
                range_name = f"{worksheet}!A:L"
                
                # Executed in a thread to keep async loop non-blocking
                import asyncio
                await asyncio.to_thread(
                    self._service.spreadsheets().values().append(
                        spreadsheetId=self.config.spreadsheet_id,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        insertDataOption="INSERT_ROWS",
                        body=body,
                    ).execute
                )

                await self.db.update_sheet_record_status(rec_id, status="synced")
                logger.info(f"Synced ticket {payload.get('ticket_id')} to Google Sheet '{worksheet}'.")
            except Exception as e:
                logger.warning(f"Failed to sync ticket record {rec_id} to Google Sheets: {e}")
                await self.db.update_sheet_record_status(rec_id, status="pending", error=str(e))
