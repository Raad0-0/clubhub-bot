"""Events Cog managing activity planning, RSVPs, and moderated Q&A."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import discord
from discord import app_commands, ui
from discord.ext import commands

if TYPE_CHECKING:
    from clubhub.bot import ClubHubBot

logger = logging.getLogger("clubhub.events")


class EventQuestionModal(ui.Modal, title="Ask a Question"):
    """Modal for members to submit questions about an event."""

    def __init__(self, cog: EventsCog, event_id: int):
        super().__init__()
        self.cog = cog
        self.event_id = event_id

        self.question_input = ui.TextInput(
            label="Your Question",
            placeholder="Ask organizers about this event (time, prep, details)...",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.add_item(self.question_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_question_submission(
            interaction=interaction,
            event_id=self.event_id,
            question=self.question_input.value.strip(),
        )


class EventQuestionReplyModal(ui.Modal):
    """Modal for organizers to send a personal response to the asking member."""

    def __init__(
        self,
        cog: EventsCog,
        user_id: int,
        user_name: str,
        event_title: str,
        question_id: Optional[int] = None,
    ):
        super().__init__(title=f"Reply to {user_name}"[:45])
        self.cog = cog
        self.user_id = user_id
        self.user_name = user_name
        self.event_title = event_title
        self.question_id = question_id

        self.reply_input = ui.TextInput(
            label="Your Answer",
            placeholder=f"Type your personal answer for {user_name}...",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )
        self.add_item(self.reply_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        user = interaction.client.get_user(self.user_id)
        if not user:
            try:
                user = await interaction.client.fetch_user(self.user_id)
            except Exception:
                user = None

        reply_text = self.reply_input.value.strip()

        dm_sent = False
        if user:
            try:
                dm_embed = discord.Embed(
                    title=f"📬 Answer regarding '{self.event_title}'",
                    description=reply_text,
                    color=self.cog.config.community.branding.color,
                    timestamp=datetime.now(timezone.utc),
                )
                dm_embed.set_footer(
                    text=f"Answered by {interaction.user.display_name} • Event Organizer"
                )
                await user.send(embed=dm_embed)
                dm_sent = True
            except Exception:
                dm_sent = False

        if self.question_id:
            await self.cog.db.review_event_question(
                self.question_id, status="answered", reviewer_id=interaction.user.id
            )

        if dm_sent:
            await interaction.followup.send(
                f"✅ **Your answer was sent directly to {user.mention} via DM!**",
                ephemeral=True,
            )
            # Update the question card in the channel
            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                embed.color = self.cog.config.community.branding.accent_color
                embed.add_field(
                    name="Status",
                    value=f"✅ Answered by {interaction.user.mention} (DM sent)",
                    inline=False,
                )
                await interaction.message.edit(embed=embed, view=None)
        else:
            await interaction.followup.send(
                f"⚠️ Could not send a DM to the member (their DMs may be closed).\n"
                f"Please reply to {f'<@{self.user_id}>'} directly in the text channel!",
                ephemeral=True,
            )


class EventQuestionNotifyView(ui.View):
    """Interactive controls attached to event question notifications in the organizer channel."""

    def __init__(
        self,
        cog: Optional[EventsCog] = None,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        event_title: Optional[str] = None,
        question_id: Optional[int] = None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.user_name = user_name
        self.event_title = event_title
        self.question_id = question_id

    @ui.button(
        label="Reply via DM",
        style=discord.ButtonStyle.primary,
        emoji="💬",
        custom_id="clubhub:event_qa_reply_dm",
    )
    async def reply_dm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may reply to event questions.", ephemeral=True
            )
            return

        user_id = self.user_id
        user_name = self.user_name or "Member"
        event_title = self.event_title or "Community Event"

        if not user_id and interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            if "**From:**" in (embed.description or ""):
                try:
                    part = embed.description.split("**From:**")[1].split("\n")[0]
                    if "<@" in part:
                        user_id = int(part.split("<@")[1].split(">")[0].lstrip("!"))
                except Exception:
                    pass

        if not user_id:
            await interaction.response.send_message(
                "Could not determine the member ID. Please reply to them directly in the text channel.",
                ephemeral=True,
            )
            return

        modal = EventQuestionReplyModal(
            self.cog,
            user_id=user_id,
            user_name=user_name,
            event_title=event_title,
            question_id=self.question_id,
        )
        await interaction.response.send_modal(modal)


# Compatibility alias
EventQuestionReviewView = EventQuestionNotifyView


class EventRsvpView(ui.View):
    """Persistent interactive RSVP buttons for published events."""

    def __init__(self, cog: Optional[EventsCog] = None, event_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.event_id = event_id

    async def _handle_rsvp(self, interaction: discord.Interaction, response_type: str) -> None:
        if not self.cog:
            return
        assert interaction.message is not None
        # Extract event_id from message or button
        event_id = self.event_id
        if not event_id:
            # Parse from embed footer if available
            if interaction.message.embeds:
                footer = interaction.message.embeds[0].footer.text or ""
                if "Event ID: " in footer:
                    try:
                        event_id = int(footer.split("Event ID: ")[1].split()[0])
                    except Exception:
                        pass

        if not event_id:
            await interaction.response.send_message("Event could not be determined.", ephemeral=True)
            return

        await self.cog.db.set_rsvp(
            event_id=event_id,
            user_id=interaction.user.id,
            user_name=str(interaction.user.display_name),
            response=response_type,
        )

        labels = {"going": "Going 🎉", "maybe": "Maybe 🤔", "cant_attend": "Can't Attend 😔"}
        await interaction.response.send_message(
            f"Your RSVP has been updated to **{labels.get(response_type, response_type)}**!",
            ephemeral=True,
        )

        # Refresh RSVP counter on event message
        await self.cog.refresh_event_embed(interaction.message, event_id)

    @ui.button(
        label="Going",
        style=discord.ButtonStyle.success,
        custom_id="clubhub:rsvp_going",
        emoji="✅",
    )
    async def going_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_rsvp(interaction, "going")

    @ui.button(
        label="Maybe",
        style=discord.ButtonStyle.primary,
        custom_id="clubhub:rsvp_maybe",
        emoji="🤔",
    )
    async def maybe_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_rsvp(interaction, "maybe")

    @ui.button(
        label="Can't Attend",
        style=discord.ButtonStyle.secondary,
        custom_id="clubhub:rsvp_cant_attend",
        emoji="❌",
    )
    async def cant_attend_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self._handle_rsvp(interaction, "cant_attend")

    @ui.button(
        label="Ask a Question",
        style=discord.ButtonStyle.secondary,
        custom_id="clubhub:event_ask_question",
        emoji="❓",
    )
    async def ask_question_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return

        event_id = self.event_id
        if not event_id and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            if "Event ID: " in footer:
                try:
                    event_id = int(footer.split("Event ID: ")[1].split()[0])
                except Exception:
                    pass

        if not event_id:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return

        modal = EventQuestionModal(self.cog, event_id)
        await interaction.response.send_modal(modal)


class DraftPublishView(ui.View):
    """Allows immediate one-click publishing of a newly created draft event."""

    def __init__(self, cog: Optional[EventsCog] = None, event_id: Optional[int] = None):
        super().__init__(timeout=600)
        self.cog = cog
        self.event_id = event_id

    @ui.button(
        label="Publish to #events Now",
        style=discord.ButtonStyle.success,
        emoji="🚀",
        custom_id="clubhub:publish_draft_now",
    )
    async def publish_now(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog or not self.event_id:
            await interaction.response.send_message("Event context missing.", ephemeral=True)
            return

        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may publish events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        result = await self.cog.publish_event_to_channel(interaction.guild, self.event_id)
        if result["success"]:
            button.disabled = True
            button.label = "Published ✅"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"🎉 **Event #{self.event_id} has been published to {result['channel_mention']}!**",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ Failed to publish event: {result['error']}", ephemeral=True
            )


def parse_and_validate_calendar_event(
    date_str: str, time_str: str, default_tz: str = "UTC"
) -> tuple[bool, str, Optional[int], Optional[str]]:
    """Parse and validate calendar date and time inputs.

    Returns (is_valid, formatted_display, unix_timestamp, error_message).
    Validates against real calendar dates and generates official Discord timestamp.
    """
    date_clean = date_str.strip()
    time_clean = time_str.strip()

    if not date_clean or not time_clean:
        return (
            False,
            "",
            None,
            "⚠️ Both Calendar Date and Time fields are required.",
        )

    combined = f"{date_clean} {time_clean}"
    try:
        from dateutil import parser as dt_parser
        dt = dt_parser.parse(combined, fuzzy=False)
    except Exception:
        return (
            False,
            "",
            None,
            (
                "⚠️ **Invalid Calendar Date or Time!**\n"
                "Please enter an official calendar date and time:\n"
                "• **Date format:** `YYYY-MM-DD` *(e.g. `2026-11-20`)*\n"
                "• **Time format:** `HH:MM AM/PM TZ` *(e.g. `06:30 PM UTC` or `18:30 UTC`)*"
            ),
        )

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    unix_ts = int(dt.timestamp())
    dt_readable = dt.strftime("%Y-%m-%d %I:%M %p %Z").strip()
    formatted_display = f"<t:{unix_ts}:F> (<t:{unix_ts}:R>)\n📅 `{dt_readable}`"

    return True, formatted_display, unix_ts, None


class EventDetailManageView(ui.View):
    """Interactive controls for concluding, deleting, or cancelling an event."""

    def __init__(self, cog: EventsCog, event_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.event_id = event_id

    @ui.button(
        label="Conclude (Keep Record)",
        style=discord.ButtonStyle.primary,
        emoji="🏁",
        custom_id="clubhub:btn_conclude_event",
    )
    async def conclude_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and Event Management may conclude events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        result = await self.cog.conclude_event_action(interaction.guild, self.event_id)
        if result["success"]:
            button.disabled = True
            button.label = "Concluded ✅"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"🏁 **Event #{self.event_id} has been marked as CONCLUDED.**\n"
                f"The announcement remains in the events channel with final attendance records, and RSVPs are closed.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"⚠️ {result['error']}", ephemeral=True)

    @ui.button(
        label="Remove / Delete Event",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="clubhub:btn_delete_event",
    )
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and Event Management may delete events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        result = await self.cog.delete_event_action(interaction.guild, self.event_id)
        if result["success"]:
            for child in self.children:
                if isinstance(child, ui.Button):
                    child.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"🗑️ **Event #{self.event_id} has been completely removed.**\n"
                f"The announcement message was deleted from the events channel and archived.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"⚠️ {result['error']}", ephemeral=True)

    @ui.button(
        label="Cancel Event",
        style=discord.ButtonStyle.secondary,
        emoji="🛑",
        custom_id="clubhub:btn_cancel_event",
    )
    async def cancel_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and Event Management may cancel events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        event = await self.cog.db.get_event(self.event_id)
        if not event:
            await interaction.response.send_message(f"Event #{self.event_id} not found.", ephemeral=True)
            return

        await self.cog.db.cancel_event(self.event_id)
        if event.get("channel_id") and event.get("message_id"):
            ch = interaction.guild.get_channel(event["channel_id"])
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(event["message_id"])
                    if msg.embeds:
                        embed = msg.embeds[0]
                        embed.title = f"🛑 [CANCELLED] {event['title']}"
                        embed.color = self.cog.config.community.branding.error_color
                        await msg.edit(embed=embed, view=None)
                except Exception:
                    pass

        button.disabled = True
        button.label = "Cancelled 🛑"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🛑 Event #{self.event_id} has been cancelled.", ephemeral=True)

    @ui.button(
        label="RSVP Breakdown",
        style=discord.ButtonStyle.secondary,
        emoji="📊",
        custom_id="clubhub:btn_rsvp_breakdown",
    )
    async def rsvp_summary_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and Event Management may view summaries.", ephemeral=True
            )
            return

        event = await self.cog.db.get_event(self.event_id)
        if not event:
            await interaction.response.send_message(f"Event #{self.event_id} not found.", ephemeral=True)
            return

        rsvps = await self.cog.db.get_event_rsvps_summary(self.event_id)
        embed = discord.Embed(
            title=f"RSVP Breakdown: {event['title']} (#{self.event_id})",
            color=self.cog.config.community.branding.color,
        )
        embed.add_field(
            name=f"Going ({len(rsvps['going'])})",
            value="\n".join(f"• {u}" for u in rsvps["going"]) if rsvps["going"] else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Maybe ({len(rsvps['maybe'])})",
            value="\n".join(f"• {u}" for u in rsvps["maybe"]) if rsvps["maybe"] else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Can't Attend ({len(rsvps['cant_attend'])})",
            value="\n".join(f"• {u}" for u in rsvps["cant_attend"]) if rsvps["cant_attend"] else "None",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EventSelectDropdown(ui.Select):
    """Dropdown menu to choose an event to manage."""

    def __init__(self, cog: EventsCog, events: List[Dict[str, Any]]):
        self.cog = cog
        options = []
        for e in events[:25]:
            status_emoji = {
                "published": "🟢",
                "draft": "🟡",
                "concluded": "🏁",
                "cancelled": "🔴",
            }.get(e.get("status", ""), "📅")
            label = f"#{e['event_id']}: {e['title'][:45]}"
            desc = f"{status_emoji} {e.get('status', '').capitalize()} | {e['location'][:30]}"
            options.append(discord.SelectOption(label=label, value=str(e["event_id"]), description=desc[:100]))

        super().__init__(
            placeholder="Choose an event to manage...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        event_id = int(self.values[0])
        event = await self.cog.db.get_event(event_id)
        if not event:
            await interaction.response.send_message(f"Event #{event_id} not found.", ephemeral=True)
            return

        embed = await self.cog.build_event_detail_embed(event)
        view = EventDetailManageView(self.cog, event_id)
        await interaction.response.send_message(
            f"🛠️ **Managing Event #{event_id}** — Choose an action below:",
            embed=embed,
            view=view,
            ephemeral=True,
        )


class EventManagerDashboardView(ui.View):
    """View containing dropdown to select and manage community events."""

    def __init__(self, cog: EventsCog, events: List[Dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(EventSelectDropdown(cog, events))


class EventCreateLaunchView(ui.View):
    """View containing interactive buttons to open the event creation modal, view events, or manage events."""

    def __init__(self, cog: Optional[EventsCog] = None):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(
        label="Open Event Creation Form",
        style=discord.ButtonStyle.primary,
        emoji="📅",
        custom_id="clubhub:launch_event_create",
        row=0,
    )
    async def open_form(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may create community events.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(EventCreateModal(self.cog))

    @ui.button(
        label="View Event List",
        style=discord.ButtonStyle.secondary,
        emoji="📋",
        custom_id="clubhub:launch_event_list",
        row=0,
    )
    async def view_list(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may view event records.",
                ephemeral=True,
            )
            return
        assert interaction.guild is not None
        events = await self.cog.db.get_events_for_guild(interaction.guild.id)
        if not events:
            await interaction.response.send_message(
                "📅 No events found on this server. Click **Open Event Creation Form** to plan one!",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Community Events ({interaction.guild.name})",
            color=self.cog.config.community.branding.color,
        )
        lines = []
        for e in events[:15]:
            status_badge = {
                "published": "🟢 Published",
                "draft": "🟡 Draft",
                "concluded": "🏁 Concluded",
                "cancelled": "🔴 Cancelled",
            }.get(e.get("status", ""), e.get("status", ""))
            lines.append(
                f"**#{e['event_id']} {e['title']}** — {status_badge}\n"
                f"🕒 {e['event_time']} | 📍 {e['location']}"
            )
        embed.description = "\n\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(
        label="Manage Events",
        style=discord.ButtonStyle.secondary,
        emoji="⚙️",
        custom_id="clubhub:launch_event_manage",
        row=0,
    )
    async def manage_events_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if not self.cog:
            return
        if not self.cog.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may manage events.",
                ephemeral=True,
            )
            return
        assert interaction.guild is not None
        events = await self.cog.db.get_events_for_guild(interaction.guild.id)
        if not events:
            await interaction.response.send_message(
                "📅 No active events found on this server. Click **Open Event Creation Form** to create one!",
                ephemeral=True,
            )
            return

        view = EventManagerDashboardView(self.cog, events)
        await interaction.response.send_message(
            "⚙️ **Event Management Dashboard**\nSelect an event from the dropdown below to conclude it (keep as completed record) or remove it from the channel:",
            view=view,
            ephemeral=True,
        )


class EventCreateModal(ui.Modal, title="Create Community Event Draft"):
    """Modal for organizers to create an event draft with official calendar date validation."""

    def __init__(self, cog: EventsCog):
        super().__init__()
        self.cog = cog

        self.title_input = ui.TextInput(
            label="Event Title",
            placeholder="e.g. Monthly General Meeting / Python Workshop",
            max_length=120,
            required=True,
        )
        self.date_input = ui.TextInput(
            label="📅 Calendar Date (YYYY-MM-DD)",
            placeholder="e.g. 2026-11-20 (Year-Month-Day)",
            max_length=25,
            required=True,
        )
        self.time_input = ui.TextInput(
            label="🕒 Time & Timezone (HH:MM AM/PM TZ)",
            placeholder="e.g. 06:30 PM UTC  or  18:30 EST",
            max_length=30,
            required=True,
        )
        self.location_input = ui.TextInput(
            label="📍 Location / Channel",
            placeholder="e.g. Main Auditorium / Community Lounge / VC #Auditorium",
            max_length=100,
            required=True,
        )
        self.desc_input = ui.TextInput(
            label="📝 Description & Agenda",
            placeholder="Outline topics covered, prerequisites, or schedule...",
            style=discord.TextStyle.paragraph,
            max_length=1200,
            required=True,
        )

        self.add_item(self.title_input)
        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.location_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        is_valid, formatted_time, unix_ts, err_msg = parse_and_validate_calendar_event(
            self.date_input.value, self.time_input.value
        )
        if not is_valid:
            await interaction.response.send_message(err_msg or "Invalid date format.", ephemeral=True)
            return

        event_id = await self.cog.db.create_event(
            guild_id=interaction.guild.id,
            organizer_id=interaction.user.id,
            organizer_name=str(interaction.user.display_name),
            title=self.title_input.value.strip(),
            description=self.desc_input.value.strip(),
            event_time=formatted_time,
            location=self.location_input.value.strip(),
            audience="public",
            status="draft",
        )

        embed = discord.Embed(
            title=f"Draft Event #{event_id}: {self.title_input.value.strip()}",
            description=self.desc_input.value.strip(),
            color=self.cog.config.community.branding.color,
        )
        embed.add_field(name="🕒 Date & Time", value=formatted_time, inline=False)
        embed.add_field(name="📍 Location", value=self.location_input.value.strip(), inline=True)
        embed.set_footer(text=f"Event ID: {event_id} | Status: Draft")

        view = DraftPublishView(self.cog, event_id)
        await interaction.response.send_message(
            f"✅ **Event draft #{event_id} created successfully!**\n"
            f"Review the draft below and click **Publish to #events Now** or run `!event publish {event_id}`.",
            embed=embed,
            view=view,
            ephemeral=True,
        )


class EventsCog(commands.Cog, name="Events"):
    """Organizer tools for event scheduling, RSVP management, and Q&A."""

    def __init__(self, bot: ClubHubBot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db

    def is_user_organizer(self, user: Union[discord.User, discord.Member]) -> bool:
        if not isinstance(user, discord.Member) and not hasattr(user, "guild_permissions"):
            return False
        guild_perms = getattr(user, "guild_permissions", None)
        if guild_perms and getattr(guild_perms, "administrator", False):
            return True
        admin_roles = [str(r).lower() for r in self.config.roles.admin_roles]
        organizer_roles = [str(r).lower() for r in self.config.roles.organizer_roles]
        allowed_names = set(admin_roles + organizer_roles + ["event management", "admin", "administrator"])
        for r in getattr(user, "roles", []):
            if (
                r.name.lower() in allowed_names
                or r.id in self.config.roles.admin_roles
                or r.id in self.config.roles.organizer_roles
            ):
                return True
        return False

    def _resolve_channel(
        self, guild: discord.Guild, channel_ref: Union[str, int]
    ) -> Optional[discord.TextChannel]:
        if isinstance(channel_ref, int) or (isinstance(channel_ref, str) and channel_ref.isdigit()):
            ch = guild.get_channel(int(channel_ref))
            if isinstance(ch, discord.TextChannel):
                return ch
        name = str(channel_ref).lower().lstrip("#")
        return discord.utils.find(lambda c: c.name.lower() == name, guild.text_channels)

    async def setup_or_get_management_channel(
        self, guild: discord.Guild
    ) -> tuple[Optional[discord.TextChannel], bool]:
        """Resolve or automatically create the dedicated event management channel with restricted permissions.

        Returns (channel, created_boolean).
        Restricts access so only Administrators and the Event Management team can view or send messages.
        """
        ch_ref = self.config.channels.event_management_channel
        channel = self._resolve_channel(guild, ch_ref)
        if channel:
            return channel, False

        bot_member = guild.me
        if not bot_member.guild_permissions.manage_channels:
            logger.warning("Bot lacks 'manage_channels' permission to create event management channel.")
            return None, False

        channel_name = str(ch_ref).lower().lstrip("#") if isinstance(ch_ref, str) else "create-event"

        overwrites: Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False,
                view_channel=False,
                send_messages=False,
            ),
            bot_member: discord.PermissionOverwrite(
                read_messages=True,
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_permissions=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
            ),
        }

        roles_to_grant: List[Union[str, int]] = (
            list(self.config.roles.admin_roles)
            + list(self.config.roles.organizer_roles)
            + ["Event Management", "Admin", "Administrator"]
        )

        for role_ref in roles_to_grant:
            target_role = None
            if isinstance(role_ref, int) or (isinstance(role_ref, str) and role_ref.isdigit()):
                target_role = guild.get_role(int(role_ref))
            else:
                r_name = str(role_ref).lower()
                target_role = discord.utils.find(lambda r: r.name.lower() == r_name, guild.roles)

            if target_role and target_role not in overwrites:
                overwrites[target_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    view_channel=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                )

        try:
            new_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic="Dedicated channel for event creation and planning (Admin & Event Management only)",
            )
            return new_channel, True
        except Exception as e:
            logger.error(f"Failed to auto-create event management channel '{channel_name}': {e}", exc_info=True)
            return None, False

    async def lock_management_channel_permissions(
        self, channel: discord.TextChannel
    ) -> bool:
        """Lock permissions on a channel so only Admin, Event Management, and bot can view/send."""
        guild = channel.guild
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_channels and not bot_member.guild_permissions.manage_permissions:
            return False

        try:
            await channel.set_permissions(
                guild.default_role,
                view_channel=False,
                send_messages=False,
                read_messages=False,
            )
            await channel.set_permissions(
                bot_member,
                view_channel=True,
                send_messages=True,
                read_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
            )
            roles_to_grant: List[Union[str, int]] = (
                list(self.config.roles.admin_roles)
                + list(self.config.roles.organizer_roles)
                + ["Event Management", "Admin", "Administrator"]
            )
            for role_ref in roles_to_grant:
                target_role = None
                if isinstance(role_ref, int) or (isinstance(role_ref, str) and role_ref.isdigit()):
                    target_role = guild.get_role(int(role_ref))
                else:
                    r_name = str(role_ref).lower()
                    target_role = discord.utils.find(lambda r: r.name.lower() == r_name, guild.roles)

                if target_role:
                    await channel.set_permissions(
                        target_role,
                        view_channel=True,
                        send_messages=True,
                        read_messages=True,
                        embed_links=True,
                        attach_files=True,
                        read_message_history=True,
                    )
            return True
        except Exception as e:
            logger.warning(f"Failed to lock permissions on channel '{channel.name}': {e}")
            return False

    def build_event_management_panel(self) -> str:
        """Construct full-width Markdown text for the permanent event creation panel.

        Provides comprehensive instructions on how to use the !event commands,
        interactive modal buttons, and workflow details for Admin and Event Management.
        Strictly sized well within Discord's 2,000-character content limit.
        """
        lines = [
            "# 📅 EVENT MANAGEMENT & CREATION PANEL",
            "Restricted to **Administrators** and the **Event Management** team.",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "### 🚀 OPTION 1: Interactive Popup Form (Official Calendar)",
            "Click the **📅 Open Event Creation Form** button below.",
            "Enter Title, **Calendar Date (YYYY-MM-DD)**, **Time (HH:MM AM/PM)**, Location, and Description.",
            "Dates are validated against real calendar days and rendered with Discord's dynamic timestamp!",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "### ⌨️ OPTION 2: Chat Command Syntax",
            "Create a draft directly in chat using pipe `|` separators:",
            "```",
            "!event create <Title> | <YYYY-MM-DD> | <HH:MM TZ> | <Location> | [Description]",
            "```",
            "*Example:*",
            "`!event create AI Workshop | 2026-11-20 | 06:30 PM UTC | VC #Auditorium | Hands-on PyTorch coding session!`",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "### 🛠️ Organizer Command Reference",
            "• **`!event create`** / **`!event_create`** — Open calendar popup form or draft via syntax",
            "• **`!event publish <id>`** / **`!event_publish <id>`** — Broadcast draft to `#events` with live RSVP buttons",
            "• **`!event conclude <id>`** / **`!event_conclude <id>`** — Mark event over (keeps record in `#events`, closes RSVPs)",
            "• **`!event delete <id>`** / **`!event_delete <id>`** — Remove/delete event message completely from `#events`",
            "• **`!event manage [id]`** / **`!event_manage [id]`** — Open interactive event management dashboard",
            "• **`!event cancel <id>`** / **`!event_cancel <id>`** — Cancel event with cancellation badge",
            "• **`!event summary <id>`** — View RSVP attendee list *(Going, Maybe, Can't Attend)*",
            "• **`!event list`** — List all community events & statuses",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "⚡ **Click a button below to get started:**",
        ]
        return "\n".join(lines)

    async def post_event_panel(
        self, channel: discord.abc.Messageable
    ) -> discord.Message:
        """Post the permanent event management panel with instructions and interactive buttons."""
        content = self.build_event_management_panel()
        view = EventCreateLaunchView(self)
        if len(content) > 1950:
            cut_idx = content[:1950].rfind("\n")
            if cut_idx > 0:
                content = content[:cut_idx] + "\n\n⚡ **Click a button below to get started:**"
            else:
                content = content[:1950]
        return await channel.send(content=content, view=view)

    async def build_event_detail_embed(self, event: Dict[str, Any]) -> discord.Embed:
        """Construct an overview embed for event management."""
        event_id = event["event_id"]
        rsvps = await self.db.get_event_rsvps_summary(event_id)
        status_badges = {
            "published": "🟢 Published",
            "draft": "🟡 Draft",
            "concluded": "🏁 Concluded",
            "cancelled": "🔴 Cancelled",
            "deleted": "🗑️ Deleted",
        }
        status_text = status_badges.get(event.get("status", ""), event.get("status", "").capitalize())

        embed = discord.Embed(
            title=f"Event #{event_id}: {event['title']}",
            description=event["description"][:1000] if event.get("description") else "No description provided.",
            color=self.config.community.branding.color,
        )
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="📍 Location", value=event["location"], inline=True)
        embed.add_field(name="🕒 Date & Time", value=event["event_time"], inline=False)
        embed.add_field(
            name="📊 RSVPs",
            value=f"**Going:** {len(rsvps['going'])} | **Maybe:** {len(rsvps['maybe'])} | **Can't Attend:** {len(rsvps['cant_attend'])}",
            inline=False,
        )
        embed.set_footer(text=f"Organizer ID: {event['organizer_id']}")
        return embed

    async def conclude_event_action(
        self, guild: discord.Guild, event_id: int
    ) -> Dict[str, Any]:
        """Mark event as concluded, keep announcement in #events as past record, and lock RSVPs."""
        event = await self.db.get_event(event_id)
        if not event:
            return {"success": False, "error": f"Event #{event_id} not found."}

        await self.db.conclude_event(event_id)

        # Update announcement card in #events if published
        if event.get("channel_id") and event.get("message_id"):
            ch = guild.get_channel(event["channel_id"])
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(event["message_id"])
                    if msg.embeds:
                        embed = msg.embeds[0]
                        embed.title = f"🏁 [CONCLUDED] {event['title']}"
                        embed.color = 0x747F8D

                        # Update or insert status field
                        status_updated = False
                        for i, f in enumerate(embed.fields):
                            if f.name == "Event Status":
                                embed.set_field_at(
                                    i, name="Event Status", value="🏁 **Concluded** • This event has ended", inline=False
                                )
                                status_updated = True
                                break
                        if not status_updated:
                            embed.insert_field_at(
                                0, name="Event Status", value="🏁 **Concluded** • This event has ended", inline=False
                            )

                        # Remove RSVP view buttons so no further votes can be cast
                        await msg.edit(embed=embed, view=None)
                except Exception as e:
                    logger.warning(f"Could not update concluded event message in #{ch.name}: {e}")

        return {"success": True, "event": event}

    async def delete_event_action(
        self, guild: discord.Guild, event_id: int
    ) -> Dict[str, Any]:
        """Completely remove event from #events channel and archive it."""
        event = await self.db.get_event(event_id)
        if not event:
            return {"success": False, "error": f"Event #{event_id} not found."}

        if event.get("channel_id") and event.get("message_id"):
            ch = guild.get_channel(event["channel_id"])
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(event["message_id"])
                    await msg.delete()
                except Exception as e:
                    logger.warning(f"Could not delete message for event #{event_id}: {e}")

        await self.db.delete_event(event_id)
        return {"success": True, "event": event}

    async def refresh_event_embed(self, message: discord.Message, event_id: int) -> None:
        """Update RSVP counts displayed on an event message."""
        event = await self.db.get_event(event_id)
        if not event or not message.embeds:
            return

        rsvps = await self.db.get_event_rsvps_summary(event_id)
        embed = message.embeds[0]

        # Update or add RSVP field
        rsvp_text = (
            f"**Going ({len(rsvps['going'])}):** {', '.join(rsvps['going'][:8]) if rsvps['going'] else 'None yet'}\n"
            f"**Maybe ({len(rsvps['maybe'])}):** {len(rsvps['maybe'])}\n"
            f"**Can't Attend ({len(rsvps['cant_attend'])}):** {len(rsvps['cant_attend'])}"
        )

        field_idx = None
        for i, f in enumerate(embed.fields):
            if f.name.startswith("RSVP Responses"):
                field_idx = i
                break

        if field_idx is not None:
            embed.set_field_at(field_idx, name="RSVP Responses", value=rsvp_text, inline=False)
        else:
            embed.add_field(name="RSVP Responses", value=rsvp_text, inline=False)

        try:
            await message.edit(embed=embed)
        except Exception:
            pass

    async def handle_question_submission(
        self, interaction: discord.Interaction, event_id: int, question: str
    ) -> None:
        """Process question submitted by member and post it directly on the text channel."""
        guild = interaction.guild
        if not guild:
            return

        event = await self.db.get_event(event_id)
        event_title = event["title"] if event else f"Event #{event_id}"

        q_id = await self.db.add_event_question(
            event_id=event_id,
            user_id=interaction.user.id,
            user_name=str(interaction.user.display_name),
            question=question,
        )

        # 1. Resolve the text channel where the event was published
        events_ch: Optional[discord.TextChannel] = None
        event_msg: Optional[discord.Message] = None

        if event and event.get("channel_id"):
            raw_ch = guild.get_channel(event["channel_id"])
            if isinstance(raw_ch, discord.TextChannel):
                events_ch = raw_ch
                if event.get("message_id"):
                    try:
                        event_msg = await events_ch.fetch_message(event["message_id"])
                    except Exception as e:
                        logger.warning(f"Could not fetch event message {event.get('message_id')}: {e}")

        if not events_ch:
            events_ch = self._resolve_channel(guild, self.config.channels.events_channel)

        if not events_ch and isinstance(interaction.channel, discord.TextChannel):
            events_ch = interaction.channel

        # Format question notification embed
        embed = discord.Embed(
            title=f"❓ Question: {event_title}",
            description=(
                f"**From:** {interaction.user.mention} (`{interaction.user.display_name}`)\n"
                f"**Event:** #{event_id} — {event_title}\n\n"
                f"**Question:**\n> {question}\n\n"
                f"💡 *Organizers can reply to {interaction.user.mention} directly here in this channel, "
                f"or click **Reply via DM** below to answer them privately.*"
            ),
            color=self.config.community.branding.color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Event ID: {event_id} | Member ID: {interaction.user.id}")

        view = EventQuestionNotifyView(
            self,
            user_id=interaction.user.id,
            user_name=str(interaction.user.display_name),
            event_title=event_title,
            question_id=q_id,
        )

        posted = False
        if events_ch:
            try:
                if event_msg:
                    await event_msg.reply(
                        content=f"📢 **New question for {event_title}** from {interaction.user.mention}:",
                        embed=embed,
                        view=view,
                        mention_author=False,
                    )
                else:
                    await events_ch.send(
                        content=f"📢 **New question for {event_title}** from {interaction.user.mention}:",
                        embed=embed,
                        view=view,
                    )
                posted = True
            except Exception as e:
                logger.error(f"Failed to post question in events channel: {e}", exc_info=True)

        # 2. Also notify separate internal organizer channel if configured and distinct from events_ch
        review_ch = self._resolve_channel(guild, self.config.channels.event_qa_review_channel)
        if review_ch and review_ch != events_ch:
            try:
                await review_ch.send(
                    content=f"📢 **Event Question (Event #{event_id})** from {interaction.user.mention}:",
                    embed=embed,
                    view=EventQuestionNotifyView(
                        self,
                        user_id=interaction.user.id,
                        user_name=str(interaction.user.display_name),
                        event_title=event_title,
                        question_id=q_id,
                    ),
                )
            except Exception as e:
                logger.warning(f"Could not notify organizer review channel: {e}")

        # Send member feedback
        if posted and events_ch:
            await interaction.followup.send(
                f"✅ **Your question about '{event_title}' has been posted in {events_ch.mention}!**\n"
                "An organizer will reply to you on the channel or reach out personally.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"✅ **Your question about '{event_title}' has been received!**\n"
                "An organizer will reply to you personally or in the text channel.",
                ephemeral=True,
            )

    # =========================================================================
    # Organizer Commands
    # =========================================================================

    async def publish_event_to_channel(
        self, guild: discord.Guild, event_id: int
    ) -> Dict[str, Any]:
        """Publish an event draft to the community events channel with interactive RSVP controls."""
        event = await self.db.get_event(event_id)
        if not event:
            return {"success": False, "error": f"Event #{event_id} not found."}

        events_ch = self._resolve_channel(guild, self.config.channels.events_channel)
        if not events_ch:
            return {
                "success": False,
                "error": f"Configured events channel '{self.config.channels.events_channel}' not found.",
            }

        embed = discord.Embed(
            title=f"📅 {event['title']}",
            description=event["description"],
            color=self.config.community.branding.color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="🕒 Date & Time", value=event["event_time"], inline=True)
        embed.add_field(name="📍 Location", value=event["location"], inline=True)
        embed.add_field(name="Organizer", value=f"<@{event['organizer_id']}>", inline=True)
        embed.add_field(
            name="RSVP Responses",
            value="*No RSVPs yet. Click below to participate!*",
            inline=False,
        )
        embed.set_footer(text=f"Event ID: {event_id} | RSVP Status: Active")

        view = EventRsvpView(self, event_id)
        msg = await events_ch.send(embed=embed, view=view)

        await self.db.publish_event(event_id, channel_id=events_ch.id, message_id=msg.id)
        return {
            "success": True,
            "channel_mention": events_ch.mention,
            "message_id": msg.id,
            "channel_id": events_ch.id,
        }

    # =========================================================================
    # Organizer Commands
    # =========================================================================

    @commands.group(name="event", invoke_without_command=True)
    async def event_group(self, ctx: commands.Context) -> None:
        """Event coordination commands."""
        await ctx.send(
            "📅 **ClubHub Events Subsystem (Admin & Event Management)**:\n"
            "• `!post_event_panel` - Deploy the permanent event creation panel with instructions\n"
            "• `!setup_event_channel` - Create and lock dedicated #create-event channel\n"
            "• `!event create` - Open interactive popup form to plan an event draft\n"
            "• `!event create <Title> | <Time> | <Location> | [Description]` - Create draft via chat\n"
            "• `!event publish <id>` - Broadcast a draft event to the events channel\n"
            "• `!event list` - View current and scheduled events\n"
            "• `!event summary <id>` - View attendee RSVP breakdown\n"
            "• `!event cancel <id>` - Cancel a published or scheduled event\n\n"
            "*Slash commands:* `/event_create`, `/event_publish`, `/event_summary`, `/post_event_panel`"
        )

    @event_group.command(name="post_panel")
    async def event_post_panel_subcmd(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Deploy the permanent event creation panel."""
        await self.post_event_panel_cmd(ctx, channel=channel)

    @event_group.command(name="setup_channel")
    async def event_setup_channel_subcmd(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Create and configure the dedicated event management channel."""
        await self.setup_event_channel_cmd(ctx, channel=channel)

    @event_group.command(name="create")
    async def create_event_cmd(self, ctx: commands.Context, *, details: Optional[str] = None) -> None:
        """Create a new event draft via interactive form or piped arguments."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may create community events.")
            return

        if not details:
            embed = discord.Embed(
                title="📅 Community Event Planner",
                description=(
                    "Click the button below to open the interactive event creation form,\n"
                    "or run `/event_create` directly in chat.\n\n"
                    "**Quick Chat Shortcut:**\n"
                    "`!event create Title | Date & Time | Location | Description`"
                ),
                color=self.config.community.branding.color,
            )
            view = EventCreateLaunchView(self)
            await ctx.send(embed=embed, view=view)
            return

        parts = [p.strip() for p in details.split("|")]
        if len(parts) >= 5:
            title = parts[0]
            date_str = parts[1]
            time_str = parts[2]
            location = parts[3]
            desc = parts[4] if parts[4] else "Join us for this community event!"
            is_valid, formatted_time, _, err_msg = parse_and_validate_calendar_event(date_str, time_str)
            if not is_valid:
                await ctx.send(err_msg or "⚠️ Invalid date/time format.")
                return
            event_time = formatted_time
        elif len(parts) >= 3:
            title = parts[0]
            date_time_raw = parts[1]
            location = parts[2]
            desc = parts[3] if len(parts) > 3 else "Join us for this community event!"
            dt_parts = date_time_raw.split(maxsplit=1)
            if len(dt_parts) == 2:
                is_valid, formatted_time, _, _ = parse_and_validate_calendar_event(dt_parts[0], dt_parts[1])
                event_time = formatted_time if is_valid else date_time_raw
            else:
                event_time = date_time_raw
        else:
            await ctx.send(
                "⚠️ **Format:** `!event create Title | YYYY-MM-DD | HH:MM TZ | Location | [Optional Description]`\n"
                "Or simply type `!event create` without arguments to use the official calendar popup form."
            )
            return

        assert ctx.guild is not None
        event_id = await self.db.create_event(
            guild_id=ctx.guild.id,
            organizer_id=ctx.author.id,
            organizer_name=str(ctx.author.display_name),
            title=title,
            description=desc,
            event_time=event_time,
            location=location,
            audience="public",
            status="draft",
        )

        embed = discord.Embed(
            title=f"Draft Event #{event_id}: {title}",
            description=desc,
            color=self.config.community.branding.color,
        )
        embed.add_field(name="🕒 Date & Time", value=event_time, inline=False)
        embed.add_field(name="📍 Location", value=location, inline=True)
        embed.set_footer(text=f"Event ID: {event_id} | Status: Draft")

        view = DraftPublishView(self, event_id)
        await ctx.send(
            f"✅ **Event draft #{event_id} created!**\nClick below or run `!event publish {event_id}` to post it to the events channel.",
            embed=embed,
            view=view,
        )

    @event_group.command(name="publish")
    async def publish_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Publish a draft event to the community events channel."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may publish community events.")
            return

        assert ctx.guild is not None
        result = await self.publish_event_to_channel(ctx.guild, event_id)
        if result["success"]:
            await ctx.send(f"✅ Event #{event_id} published to {result['channel_mention']}!")
        else:
            await ctx.send(f"⚠️ {result['error']}")

    @event_group.command(name="conclude")
    async def conclude_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Mark an event as concluded (keeps announcement in #events with final attendance, closes RSVPs)."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may conclude events.")
            return

        assert ctx.guild is not None
        result = await self.conclude_event_action(ctx.guild, event_id)
        if result["success"]:
            await ctx.send(
                f"🏁 **Event #{event_id} has been marked as CONCLUDED.**\n"
                f"The announcement message remains in the events channel with final attendance, and RSVPs are closed."
            )
        else:
            await ctx.send(f"⚠️ {result['error']}")

    @event_group.command(name="delete", aliases=["remove"])
    async def delete_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Completely delete/remove an event announcement from #events and archive it."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may delete events.")
            return

        assert ctx.guild is not None
        result = await self.delete_event_action(ctx.guild, event_id)
        if result["success"]:
            await ctx.send(
                f"🗑️ **Event #{event_id} has been completely removed.**\n"
                f"The announcement message was deleted from the events channel."
            )
        else:
            await ctx.send(f"⚠️ {result['error']}")

    @event_group.command(name="manage")
    async def manage_event_cmd(self, ctx: commands.Context, event_id: Optional[int] = None) -> None:
        """Open event management controls (conclude, remove, or cancel)."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may manage events.")
            return

        assert ctx.guild is not None
        if event_id is not None:
            event = await self.db.get_event(event_id)
            if not event:
                await ctx.send(f"⚠️ Event #{event_id} not found.")
                return
            embed = await self.build_event_detail_embed(event)
            view = EventDetailManageView(self, event_id)
            await ctx.send(
                f"🛠️ **Managing Event #{event_id}** — Choose an action below:",
                embed=embed,
                view=view,
            )
            return

        events = await self.db.get_events_for_guild(ctx.guild.id)
        if not events:
            await ctx.send("📅 No active events found on this server. Use `!event create` to plan one!")
            return

        view = EventManagerDashboardView(self, events)
        await ctx.send(
            "⚙️ **Event Management Dashboard**\nSelect an event from the dropdown below to conclude it or remove it from the channel:",
            view=view,
        )

    @event_group.command(name="cancel")
    async def cancel_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Cancel an event."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may cancel community events.")
            return

        event = await self.db.get_event(event_id)
        if not event:
            await ctx.send(f"Event #{event_id} not found.")
            return

        await self.db.cancel_event(event_id)
        if event.get("channel_id") and event.get("message_id") and ctx.guild:
            ch = ctx.guild.get_channel(event["channel_id"])
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(event["message_id"])
                    if msg.embeds:
                        embed = msg.embeds[0]
                        embed.title = f"🛑 [CANCELLED] {event['title']}"
                        embed.color = self.config.community.branding.error_color
                        await msg.edit(embed=embed, view=None)
                except Exception:
                    pass

        await ctx.send(f"🛑 Event #{event_id} (`{event['title']}`) has been cancelled.")

    @event_group.command(name="list")
    async def list_events_cmd(self, ctx: commands.Context) -> None:
        """List community events."""
        assert ctx.guild is not None
        events = await self.db.get_events_for_guild(ctx.guild.id)
        if not events:
            await ctx.send("📅 No events found on this server. Use `!event create` to plan one!")
            return

        embed = discord.Embed(
            title=f"Community Events ({ctx.guild.name})",
            color=self.config.community.branding.color,
        )
        lines = []
        for e in events[:15]:
            status_badge = {
                "published": "🟢 Published",
                "draft": "🟡 Draft",
                "concluded": "🏁 Concluded",
                "cancelled": "🔴 Cancelled",
            }.get(e.get("status", ""), e.get("status", ""))
            lines.append(
                f"**#{e['event_id']} {e['title']}** — {status_badge}\n"
                f"🕒 {e['event_time']} | 📍 {e['location']}"
            )

        embed.description = "\n\n".join(lines)
        await ctx.send(embed=embed)

    @event_group.command(name="summary")
    async def summary_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Show full RSVP breakdown for an event."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may view event summaries.")
            return

        event = await self.db.get_event(event_id)
        if not event:
            await ctx.send(f"Event #{event_id} not found.")
            return

        rsvps = await self.db.get_event_rsvps_summary(event_id)
        embed = discord.Embed(
            title=f"RSVP Summary: {event['title']} (#{event_id})",
            description=f"Status: **{event.get('status', 'unknown').capitalize()}** | 🕒 {event['event_time']}\n📍 {event['location']}",
            color=self.config.community.branding.color,
        )
        embed.add_field(
            name=f"Going ({len(rsvps['going'])})",
            value="\n".join(f"• {u}" for u in rsvps["going"]) if rsvps["going"] else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Maybe ({len(rsvps['maybe'])})",
            value="\n".join(f"• {u}" for u in rsvps["maybe"]) if rsvps["maybe"] else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Can't Attend ({len(rsvps['cant_attend'])})",
            value="\n".join(f"• {u}" for u in rsvps["cant_attend"]) if rsvps["cant_attend"] else "None",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="post_event_panel")
    async def post_event_panel_cmd(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Post the permanent Event Management Panel with instructions and creation button."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may deploy the event panel.")
            return

        assert ctx.guild is not None
        target_ch = channel
        if not target_ch:
            target_ch, created = await self.setup_or_get_management_channel(ctx.guild)
            if created and target_ch:
                await ctx.send(f"📁 Created dedicated channel {target_ch.mention} with restricted permissions (Admin & Event Management only)!")

        if not target_ch:
            target_ch = ctx.channel

        await self.post_event_panel(target_ch)
        if target_ch != ctx.channel:
            await ctx.send(f"✅ Event creation panel successfully deployed in {target_ch.mention}!")

    @commands.command(name="setup_event_channel")
    async def setup_event_channel_cmd(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Create or configure the dedicated event channel restricted to Admin & Event Management."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only Administrators and the Event Management team may configure the event channel.")
            return

        assert ctx.guild is not None
        if channel:
            target_ch = channel
            await self.lock_management_channel_permissions(target_ch)
            await ctx.send(f"🔒 Permissions locked for {target_ch.mention}: visible only to Admin and Event Management.")
        else:
            target_ch, created = await self.setup_or_get_management_channel(ctx.guild)
            if not target_ch:
                await ctx.send("⚠️ Could not create or find the event channel. Please check bot permissions.")
                return
            if not created:
                await self.lock_management_channel_permissions(target_ch)
                await ctx.send(f"🔒 Channel {target_ch.mention} found and permissions locked (Admin & Event Management only).")
            else:
                await ctx.send(f"📁 Created channel {target_ch.mention} with restricted permissions (Admin & Event Management only)!")

        await self.post_event_panel(target_ch)
        await ctx.send(f"✅ Event creation panel deployed in {target_ch.mention}!")

    # Standalone command shortcuts (!event_create, !event_publish, etc.)
    @commands.command(name="event_create")
    async def event_create_standalone_cmd(
        self, ctx: commands.Context, *, details: Optional[str] = None
    ) -> None:
        """Create a new event draft (standalone shortcut for !event create)."""
        await self.create_event_cmd(ctx, details=details)

    @commands.command(name="event_publish")
    async def event_publish_standalone_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Publish a draft event (standalone shortcut for !event publish)."""
        await self.publish_event_cmd(ctx, event_id=event_id)

    @commands.command(name="event_summary")
    async def event_summary_standalone_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """View event RSVP summary (standalone shortcut for !event summary)."""
        await self.summary_event_cmd(ctx, event_id=event_id)

    @commands.command(name="event_list")
    async def event_list_standalone_cmd(self, ctx: commands.Context) -> None:
        """List community events (standalone shortcut for !event list)."""
        await self.list_events_cmd(ctx)

    @commands.command(name="event_cancel")
    async def event_cancel_standalone_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Cancel an event (standalone shortcut for !event cancel)."""
        await self.cancel_event_cmd(ctx, event_id=event_id)

    @commands.command(name="event_conclude")
    async def event_conclude_standalone_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Mark an event as concluded (standalone shortcut for !event conclude)."""
        await self.conclude_event_cmd(ctx, event_id=event_id)

    @commands.command(name="event_delete", aliases=["event_remove"])
    async def event_delete_standalone_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Completely delete/remove an event (standalone shortcut for !event delete)."""
        await self.delete_event_cmd(ctx, event_id=event_id)

    @commands.command(name="event_manage")
    async def event_manage_standalone_cmd(
        self, ctx: commands.Context, event_id: Optional[int] = None
    ) -> None:
        """Open event management controls (standalone shortcut for !event manage)."""
        await self.manage_event_cmd(ctx, event_id=event_id)

    # =========================================================================
    # Slash Commands
    # =========================================================================

    @app_commands.command(
        name="post_event_panel",
        description="Deploy the event creation panel to the dedicated management channel",
    )
    async def post_event_panel_slash(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Slash command to deploy the event creation panel."""
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may deploy the event panel.",
                ephemeral=True,
            )
            return

        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        target_ch = channel
        if not target_ch:
            target_ch, _ = await self.setup_or_get_management_channel(interaction.guild)

        if not target_ch:
            target_ch = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None

        if not target_ch:
            await interaction.followup.send("⚠️ Could not find a valid text channel for the panel.", ephemeral=True)
            return

        await self.post_event_panel(target_ch)
        await interaction.followup.send(
            f"✅ Event creation panel deployed in {target_ch.mention}!", ephemeral=True
        )

    @app_commands.command(
        name="event_create",
        description="Open form to plan a new community event",
    )
    async def event_create_slash(self, interaction: discord.Interaction) -> None:
        """Interactive modal to create a new event draft."""
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may create community events.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(EventCreateModal(self))

    @app_commands.command(
        name="event_publish",
        description="Publish a draft event to the community events channel",
    )
    @app_commands.describe(event_id="Numeric ID of the event draft to broadcast")
    async def event_publish_slash(self, interaction: discord.Interaction, event_id: int) -> None:
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may publish events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        result = await self.publish_event_to_channel(interaction.guild, event_id)
        if result["success"]:
            await interaction.response.send_message(
                f"✅ Event #{event_id} published to {result['channel_mention']}!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ {result['error']}", ephemeral=True
            )

    @app_commands.command(
        name="event_conclude",
        description="Mark an event as concluded (keeps announcement in #events, closes RSVPs)",
    )
    @app_commands.describe(event_id="Numeric ID of the completed event")
    async def event_conclude_slash(self, interaction: discord.Interaction, event_id: int) -> None:
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may conclude events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        result = await self.conclude_event_action(interaction.guild, event_id)
        if result["success"]:
            await interaction.response.send_message(
                f"🏁 **Event #{event_id} has been marked as CONCLUDED.**\n"
                f"The announcement remains in the events channel with final attendance, and RSVPs are closed.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"⚠️ {result['error']}", ephemeral=True)

    @app_commands.command(
        name="event_delete",
        description="Completely remove an event announcement from the events channel and archive it",
    )
    @app_commands.describe(event_id="Numeric ID of the event to delete")
    async def event_delete_slash(self, interaction: discord.Interaction, event_id: int) -> None:
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may delete events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        result = await self.delete_event_action(interaction.guild, event_id)
        if result["success"]:
            await interaction.response.send_message(
                f"🗑️ **Event #{event_id} has been completely removed.**\n"
                f"The announcement was deleted from the events channel.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"⚠️ {result['error']}", ephemeral=True)

    @app_commands.command(
        name="event_manage",
        description="Open interactive controls to conclude, delete, or cancel an event",
    )
    @app_commands.describe(event_id="Optional numeric ID of a specific event")
    async def event_manage_slash(
        self, interaction: discord.Interaction, event_id: Optional[int] = None
    ) -> None:
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may manage events.", ephemeral=True
            )
            return

        assert interaction.guild is not None
        if event_id is not None:
            event = await self.db.get_event(event_id)
            if not event:
                await interaction.response.send_message(f"⚠️ Event #{event_id} not found.", ephemeral=True)
                return
            embed = await self.build_event_detail_embed(event)
            view = EventDetailManageView(self, event_id)
            await interaction.response.send_message(
                f"🛠️ **Managing Event #{event_id}** — Choose an action below:",
                embed=embed,
                view=view,
                ephemeral=True,
            )
            return

        events = await self.db.get_events_for_guild(interaction.guild.id)
        if not events:
            await interaction.response.send_message(
                "📅 No active events found on this server. Use `/event_create` to plan one!",
                ephemeral=True,
            )
            return

        view = EventManagerDashboardView(self, events)
        await interaction.response.send_message(
            "⚙️ **Event Management Dashboard**\nSelect an event from the dropdown below to conclude it or remove it from the channel:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="event_summary",
        description="View RSVP attendance breakdown for an event",
    )
    @app_commands.describe(event_id="Numeric ID of the event")
    async def event_summary_slash(self, interaction: discord.Interaction, event_id: int) -> None:
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only Administrators and the Event Management team may view event summaries.", ephemeral=True
            )
            return

        event = await self.db.get_event(event_id)
        if not event:
            await interaction.response.send_message(f"Event #{event_id} not found.", ephemeral=True)
            return

        rsvps = await self.db.get_event_rsvps_summary(event_id)
        embed = discord.Embed(
            title=f"RSVP Summary: {event['title']} (#{event_id})",
            description=f"Status: **{event.get('status', 'unknown').capitalize()}** | 🕒 {event['event_time']}\n📍 {event['location']}",
            color=self.config.community.branding.color,
        )
        embed.add_field(
            name=f"Going ({len(rsvps['going'])})",
            value="\n".join(f"• {u}" for u in rsvps["going"]) if rsvps["going"] else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Maybe ({len(rsvps['maybe'])})",
            value="\n".join(f"• {u}" for u in rsvps["maybe"]) if rsvps["maybe"] else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Can't Attend ({len(rsvps['cant_attend'])})",
            value="\n".join(f"• {u}" for u in rsvps["cant_attend"]) if rsvps["cant_attend"] else "None",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: ClubHubBot) -> None:
    await bot.add_cog(EventsCog(bot))
