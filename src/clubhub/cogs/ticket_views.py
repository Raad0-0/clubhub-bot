"""Persistent and ephemeral Discord UI Views and Modals for the ticket system."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord
from discord import ui

if TYPE_CHECKING:
    from clubhub.cogs.ticket_cog import TicketCog

logger = logging.getLogger("clubhub.tickets.views")


class TicketRequestModal(ui.Modal, title="Submit Support Request"):
    """Modal for submitting a support request."""

    def __init__(self, cog: TicketCog, category_key: str):
        super().__init__()
        self.cog = cog
        self.category_key = category_key

        cat_cfg = cog.config.tickets.categories.get(category_key)
        cat_name = cat_cfg.display_name if cat_cfg else category_key
        self.title = f"Submit: {cat_name}"[:45]

        self.subject_input = ui.TextInput(
            label="Subject",
            placeholder=f"Brief summary of your {cat_name.lower()}...",
            max_length=100,
            required=True,
        )
        self.description_input = ui.TextInput(
            label="Description",
            placeholder="Please describe your question, issue, or concern in detail...",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True,
        )

        self.add_item(self.subject_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_ticket_submission(
            interaction=interaction,
            category_key=self.category_key,
            subject=self.subject_input.value.strip(),
            description=self.description_input.value.strip(),
        )


class CategorySelect(ui.Select):
    """Dropdown for choosing a ticket category."""

    def __init__(self, cog: TicketCog):
        self.cog = cog
        options: List[discord.SelectOption] = []
        for cat_key, cat_cfg in cog.config.tickets.categories.items():
            options.append(
                discord.SelectOption(
                    label=cat_cfg.display_name[:100],
                    value=cat_key,
                    description=cat_cfg.description[:100] if cat_cfg.description else None,
                    emoji="🔒" if cat_cfg.is_sensitive else "💬",
                )
            )

        super().__init__(
            placeholder="Select a request category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="clubhub:select_category",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        category_key = self.values[0]
        modal = TicketRequestModal(self.cog, category_key)
        await interaction.response.send_modal(modal)


class CategorySelectView(ui.View):
    """View containing the category select menu."""

    def __init__(self, cog: TicketCog):
        super().__init__(timeout=180)
        self.add_item(CategorySelect(cog))


class TicketCategoryButton(ui.Button):
    """Direct category button that opens a request modal without needing an intermediate dropdown."""

    def __init__(
        self,
        cog: TicketCog,
        category_key: str,
        cat_cfg: Any,
    ):
        emoji = getattr(cat_cfg, "emoji", None)
        if not emoji:
            if getattr(cat_cfg, "is_sensitive", False):
                emoji = "🔒"
            elif "member" in category_key.lower():
                emoji = "📋"
            elif any(w in category_key.lower() for w in ("activity", "project", "help")):
                emoji = "🛠️"
            else:
                emoji = "💬"

        raw_style = getattr(cat_cfg, "button_style", None)
        if raw_style == "danger":
            style = discord.ButtonStyle.danger
        elif raw_style == "success":
            style = discord.ButtonStyle.success
        elif raw_style == "secondary" or getattr(cat_cfg, "is_sensitive", False):
            style = discord.ButtonStyle.secondary
        else:
            style = discord.ButtonStyle.primary

        super().__init__(
            label=cat_cfg.display_name[:80],
            style=style,
            emoji=emoji,
            custom_id=f"clubhub:create_ticket:{category_key}",
        )
        self.cog = cog
        self.category_key = category_key

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.cog:
            await interaction.response.send_message(
                "Bot is initializing. Please try again in a moment.", ephemeral=True
            )
            return

        # Check 1-ticket limit per Section 9.3
        assert interaction.guild is not None
        has_ticket = await self.cog.db.has_active_or_pending_ticket(
            interaction.guild.id, interaction.user.id
        )
        if has_ticket:
            await interaction.response.send_message(
                "⚠️ **You already have a pending or active request.**\n"
                "In order to ensure fair support for all members, each person may only have one active request at a time. "
                "Please wait until your existing ticket is closed or resolved.",
                ephemeral=True,
            )
            return

        # Immediately open the modal for this category!
        modal = TicketRequestModal(self.cog, self.category_key)
        await interaction.response.send_modal(modal)


class TicketEntryView(ui.View):
    """Persistent view attached to the permanent entry panel with direct category buttons."""

    def __init__(self, cog: Optional[TicketCog] = None):
        super().__init__(timeout=None)
        self.cog = cog

        if cog:
            for cat_key, cat_cfg in cog.config.tickets.categories.items():
                self.add_item(TicketCategoryButton(cog, cat_key, cat_cfg))


class LegacyTicketEntryView(ui.View):
    """Backwards-compatibility view for older single 'Create Ticket' panels."""

    def __init__(self, cog: Optional[TicketCog] = None):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="clubhub:entry_create_ticket",
        emoji="📩",
    )
    async def create_ticket_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if not self.cog:
            await interaction.response.send_message(
                "Bot is initializing. Please try again in a moment.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        has_ticket = await self.cog.db.has_active_or_pending_ticket(
            interaction.guild.id, interaction.user.id
        )
        if has_ticket:
            await interaction.response.send_message(
                "⚠️ **You already have a pending or active request.**\n"
                "In order to ensure fair support for all members, each person may only have one active request at a time. "
                "Please wait until your existing ticket is closed or resolved.",
                ephemeral=True,
            )
            return

        view = CategorySelectView(self.cog)
        await interaction.response.send_message(
            "Please select the category that best matches your request:",
            view=view,
            ephemeral=True,
        )


class TicketDeclineModal(ui.Modal, title="Decline Support Request"):
    """Modal for entering a reason when declining a ticket."""

    def __init__(self, cog: TicketCog, ticket_id: str):
        super().__init__()
        self.cog = cog
        self.ticket_id = ticket_id

        self.reason_input = ui.TextInput(
            label="Reason for Declining",
            placeholder="Explain why this request is being declined...",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_ticket_decline(
            interaction=interaction,
            ticket_id=self.ticket_id,
            reason=self.reason_input.value.strip(),
        )


class TicketReviewView(ui.View):
    """Persistent review controls for staff in the review queue."""

    def __init__(self, cog: Optional[TicketCog] = None, ticket_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_id = ticket_id

    @ui.button(
        label="Accept",
        style=discord.ButtonStyle.success,
        custom_id="clubhub:review_accept",
        emoji="✅",
    )
    async def accept_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        await self.cog.handle_ticket_accept(interaction)

    @ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        custom_id="clubhub:review_decline",
        emoji="✖️",
    )
    async def decline_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        # Open decline modal
        assert interaction.message is not None
        ticket = await self.cog.db.get_ticket_by_review_message(interaction.message.id)
        if not ticket:
            await interaction.response.send_message(
                "Unable to identify the ticket for this review message.", ephemeral=True
            )
            return

        # Check authorization
        if not self.cog.is_user_authorized_for_ticket(interaction.user, ticket):
            await interaction.response.send_message(
                "⛔ You do not have permission to review this category of requests.",
                ephemeral=True,
            )
            return

        modal = TicketDeclineModal(self.cog, ticket["ticket_id"])
        await interaction.response.send_modal(modal)


class TicketCloseConfirmView(ui.View):
    """Confirmation prompt before closing a ticket."""

    def __init__(self, cog: TicketCog, ticket_id: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.ticket_id = ticket_id

    @ui.button(label="Confirm Close", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        await self.cog.execute_ticket_closure(
            ticket_id=self.ticket_id,
            closed_by_user=interaction.user,
            reason="Closed by participant",
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message("Closure cancelled.", ephemeral=True)
        self.stop()


class TicketControlView(ui.View):
    """Persistent control message pinned in the ticket discussion channel."""

    def __init__(self, cog: Optional[TicketCog] = None):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="clubhub:control_close_ticket",
        emoji="🔒",
    )
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return

        assert interaction.channel is not None
        ticket = await self.cog.db.get_ticket_by_text_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "This channel is not recognized as an active ticket space.", ephemeral=True
            )
            return

        # Check if user is requester, assigned staff, or administrator
        is_requester = interaction.user.id == ticket["requester_id"]
        is_staff = self.cog.is_user_authorized_for_ticket(interaction.user, ticket)
        if not (is_requester or is_staff):
            await interaction.response.send_message(
                "⛔ Only the ticket requester or authorized handling staff may close this ticket.",
                ephemeral=True,
            )
            return

        view = TicketCloseConfirmView(self.cog, ticket["ticket_id"])
        await interaction.response.send_message(
            "Are you sure you want to close and delete this ticket space?",
            view=view,
            ephemeral=True,
        )


class TicketWarningView(ui.View):
    """Inactivity warning prompt sent 15 minutes before auto-closure."""

    def __init__(self, cog: Optional[TicketCog] = None, ticket_id: Optional[str] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_id = ticket_id

    @ui.button(
        label="Keep Open",
        style=discord.ButtonStyle.primary,
        custom_id="clubhub:warn_keep_open",
        emoji="⏱️",
    )
    async def keep_open_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return

        assert interaction.channel is not None
        ticket = await self.cog.db.get_ticket_by_text_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Ticket not found.", ephemeral=True)
            return

        await self.cog.db.clear_ticket_warned(ticket["ticket_id"])
        await interaction.response.send_message(
            f"✅ Inactivity timer reset by {interaction.user.mention}. This ticket will remain open.",
        )
        try:
            await interaction.message.delete()
        except Exception:
            pass

    @ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="clubhub:warn_close_ticket",
        emoji="🔒",
    )
    async def close_now_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return

        assert interaction.channel is not None
        ticket = await self.cog.db.get_ticket_by_text_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Ticket not found.", ephemeral=True)
            return

        await interaction.response.defer()
        await self.cog.execute_ticket_closure(
            ticket_id=ticket["ticket_id"],
            closed_by_user=interaction.user,
            reason="Closed via inactivity warning prompt",
        )
