"""ClubHub Bot subclass and lifecycle coordinator."""

from __future__ import annotations

import logging
from typing import Optional
import discord
from discord.ext import commands

from clubhub.config import AppConfig
from clubhub.database import DatabaseManager
from clubhub.services.sheets import GoogleSheetsService

logger = logging.getLogger("clubhub.bot")


class ClubHubBot(commands.Bot):
    """Main bot client for ClubHub."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.db = DatabaseManager(db_path=config.database_path)
        self.sheets = GoogleSheetsService(config=config.sheets_reporting, db=self.db)

        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = config.intents.members
        intents.message_content = config.intents.message_content

        super().__init__(
            command_prefix=commands.when_mentioned_or(config.community.prefix),
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
        )

    async def setup_hook(self) -> None:
        """Run initialization tasks before gateway connection."""
        logger.info("Initializing database connection...")
        await self.db.connect()

        # Load extension cogs
        initial_extensions = [
            "clubhub.cogs.ticket_cog",
            "clubhub.cogs.events_cog",
            "clubhub.cogs.community_cog",
            "clubhub.cogs.admin_cog",
        ]

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}", exc_info=True)

        # Register persistent views so interactive buttons survive restarts (Section 17)
        from clubhub.cogs.ticket_views import (
            LegacyTicketEntryView,
            TicketControlView,
            TicketEntryView,
            TicketReviewView,
            TicketWarningView,
        )
        from clubhub.cogs.events_cog import EventQuestionReviewView, EventRsvpView

        ticket_cog = self.get_cog("Tickets")
        events_cog = self.get_cog("Events")

        self.add_view(TicketEntryView(ticket_cog))  # type: ignore
        self.add_view(LegacyTicketEntryView(ticket_cog))  # type: ignore
        self.add_view(TicketReviewView(ticket_cog))  # type: ignore
        self.add_view(TicketControlView(ticket_cog))  # type: ignore
        self.add_view(TicketWarningView(ticket_cog))  # type: ignore
        self.add_view(EventRsvpView(events_cog))  # type: ignore
        self.add_view(EventQuestionReviewView(events_cog))  # type: ignore

        logger.info("Persistent views successfully registered.")

    async def on_ready(self) -> None:
        """Event fired when bot is fully logged in and ready."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id if self.user else 'N/A'})")
        logger.info(f"Connected to {len(self.guilds)} guild(s).")

        # Perform startup reconciliation for active tickets
        ticket_cog = self.get_cog("Tickets")
        if ticket_cog and hasattr(ticket_cog, "reconcile_tickets_on_startup"):
            await ticket_cog.reconcile_tickets_on_startup()
            logger.info("Startup ticket reconciliation complete.")

    async def close(self) -> None:
        """Gracefully close bot and database connections."""
        logger.info("Shutting down ClubHub...")
        await self.db.close()
        await super().close()
