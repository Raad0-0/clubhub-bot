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


class EventQuestionReviewView(ui.View):
    """Organizer moderation controls for event questions."""

    def __init__(self, cog: Optional[EventsCog] = None, question_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.question_id = question_id

    @ui.button(
        label="Approve & Post",
        style=discord.ButtonStyle.success,
        custom_id="clubhub:approve_question",
        emoji="✅",
    )
    async def approve(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        await self.cog.handle_question_decision(interaction, approved=True)

    @ui.button(
        label="Reject",
        style=discord.ButtonStyle.danger,
        custom_id="clubhub:reject_question",
        emoji="✖️",
    )
    async def reject(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not self.cog:
            return
        await self.cog.handle_question_decision(interaction, approved=False)


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


class EventCreateModal(ui.Modal, title="Create Community Event Draft"):
    """Modal for organizers to create an event draft."""

    def __init__(self, cog: EventsCog):
        super().__init__()
        self.cog = cog

        self.title_input = ui.TextInput(label="Event Title", placeholder="e.g. Monthly General Meeting", max_length=150)
        self.time_input = ui.TextInput(label="Date & Time", placeholder="e.g. 2026-11-01 18:00 UTC", max_length=100)
        self.location_input = ui.TextInput(label="Location / Voice Channel", placeholder="e.g. Community Lounge / Room 204", max_length=100)
        self.desc_input = ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=1500)

        self.add_item(self.title_input)
        self.add_item(self.time_input)
        self.add_item(self.location_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        event_id = await self.cog.db.create_event(
            guild_id=interaction.guild.id,
            organizer_id=interaction.user.id,
            organizer_name=str(interaction.user.display_name),
            title=self.title_input.value.strip(),
            description=self.desc_input.value.strip(),
            event_time=self.time_input.value.strip(),
            location=self.location_input.value.strip(),
            audience="public",
            status="draft",
        )

        embed = discord.Embed(
            title=f"Draft Event #{event_id}: {self.title_input.value.strip()}",
            description=self.desc_input.value.strip(),
            color=self.cog.config.community.branding.color,
        )
        embed.add_field(name="🕒 Time", value=self.time_input.value.strip(), inline=True)
        embed.add_field(name="📍 Location", value=self.location_input.value.strip(), inline=True)
        embed.set_footer(text=f"Event ID: {event_id} | Status: Draft")

        await interaction.response.send_message(
            f"✅ **Event draft #{event_id} created!**\nUse `/event publish {event_id}` to broadcast it to the events channel.",
            embed=embed,
            ephemeral=True,
        )


class EventsCog(commands.Cog, name="Events"):
    """Organizer tools for event scheduling, RSVP management, and Q&A."""

    def __init__(self, bot: ClubHubBot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db

    def is_user_organizer(self, user: Union[discord.User, discord.Member]) -> bool:
        if not isinstance(user, discord.Member):
            return False
        if user.guild_permissions.administrator:
            return True
        organizer_roles = self.config.roles.organizer_roles
        for r in user.roles:
            if r.name in organizer_roles or r.id in organizer_roles:
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
        """Process question submitted by member and queue for organizer review."""
        guild = interaction.guild
        if not guild:
            return

        q_id = await self.db.add_event_question(
            event_id=event_id,
            user_id=interaction.user.id,
            user_name=str(interaction.user.display_name),
            question=question,
        )

        review_ch = self._resolve_channel(guild, self.config.channels.event_qa_review_channel)
        if review_ch:
            embed = discord.Embed(
                title=f"New Event Question (Q#{q_id} for Event #{event_id})",
                description=f"**From:** {interaction.user.mention}\n**Question:**\n{question}",
                color=self.config.community.branding.warning_color,
                timestamp=datetime.now(timezone.utc),
            )
            view = EventQuestionReviewView(self, q_id)
            await review_ch.send(embed=embed, view=view)

        await interaction.followup.send(
            "✅ Your question has been submitted to the organizers for review!", ephemeral=True
        )

    async def handle_question_decision(
        self, interaction: discord.Interaction, approved: bool
    ) -> None:
        """Process organizer approval/rejection of member question."""
        if not self.is_user_organizer(interaction.user):
            await interaction.response.send_message(
                "⛔ Only event organizers may review questions.", ephemeral=True
            )
            return

        assert interaction.message is not None
        # Extract Question ID from embed title
        embed = interaction.message.embeds[0]
        q_id = None
        if "Q#" in embed.title:
            try:
                q_id = int(embed.title.split("Q#")[1].split()[0].rstrip(")"))
            except Exception:
                pass

        if not q_id:
            await interaction.response.send_message("Question ID not found.", ephemeral=True)
            return

        status = "approved" if approved else "rejected"
        await self.db.review_event_question(q_id, status=status, reviewer_id=interaction.user.id)

        embed.color = (
            self.config.community.branding.accent_color
            if approved
            else self.config.community.branding.error_color
        )
        embed.add_field(
            name="Review Outcome",
            value=f"{'✅ Approved' if approved else '✖️ Rejected'} by {interaction.user.mention}",
            inline=False,
        )
        await interaction.message.edit(embed=embed, view=None)

        if approved and interaction.guild:
            qa_pub_ch = self._resolve_channel(interaction.guild, "event-questions")
            if qa_pub_ch:
                pub_embed = discord.Embed(
                    title="Community Question",
                    description=embed.description,
                    color=self.config.community.branding.color,
                )
                await qa_pub_ch.send(embed=pub_embed)

        await interaction.response.send_message(
            f"Question marked as {status}.", ephemeral=True
        )

    # =========================================================================
    # Organizer Commands
    # =========================================================================

    @commands.group(name="event", invoke_without_command=True)
    async def event_group(self, ctx: commands.Context) -> None:
        """Event coordination commands."""
        await ctx.send(
            "ClubHub Events Subsystem:\n"
            "`!event create` - Create a new event draft\n"
            "`!event publish <id>` - Publish an event to the events channel\n"
            "`!event cancel <id>` - Cancel an event\n"
            "`!event summary <id>` - View RSVP attendees summary"
        )

    @event_group.command(name="create")
    async def create_event_cmd(self, ctx: commands.Context) -> None:
        """Create a new event draft."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only organizers may create official community events.")
            return

        # Prompt with instructions to use the slash command or modal
        await ctx.send(
            "Use `/event_create` to open the interactive event creation form, or specify details with an organizer."
        )

    @event_group.command(name="publish")
    async def publish_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Publish a draft event to the community events channel."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only organizers may publish community events.")
            return

        event = await self.db.get_event(event_id)
        if not event:
            await ctx.send(f"Event #{event_id} not found.")
            return

        events_ch = self._resolve_channel(ctx.guild, self.config.channels.events_channel)
        if not events_ch:
            await ctx.send("Configured events channel not found!")
            return

        embed = discord.Embed(
            title=f"📅 {event['title']}",
            description=event["description"],
            color=self.config.community.branding.color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="🕒 Date & Time", value=event["event_time"], inline=True)
        embed.add_field(name="📍 Location", value=event["location"], inline=True)
        embed.add_field(name="Organizer", value=f"<@{event['organizer_id']}>", inline=True)
        embed.add_field(name="RSVP Responses", value="*No RSVPs yet. Click below to participate!*", inline=False)
        embed.set_footer(text=f"Event ID: {event_id} | RSVP Status: Active")

        view = EventRsvpView(self, event_id)
        msg = await events_ch.send(embed=embed, view=view)

        await self.db.publish_event(event_id, channel_id=events_ch.id, message_id=msg.id)
        await ctx.send(f"✅ Event #{event_id} published to {events_ch.mention}!")

    @event_group.command(name="summary")
    async def summary_event_cmd(self, ctx: commands.Context, event_id: int) -> None:
        """Show full RSVP breakdown for an event."""
        if not self.is_user_organizer(ctx.author):
            await ctx.send("⛔ Only organizers may view event summaries.")
            return

        event = await self.db.get_event(event_id)
        if not event:
            await ctx.send(f"Event #{event_id} not found.")
            return

        rsvps = await self.db.get_event_rsvps_summary(event_id)
        embed = discord.Embed(
            title=f"RSVP Summary: {event['title']} (#{event_id})",
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


async def setup(bot: ClubHubBot) -> None:
    await bot.add_cog(EventsCog(bot))
