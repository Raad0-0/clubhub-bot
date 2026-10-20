"""Ticket Cog managing submission, triage, space provisioning, and automated cleanup."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands, tasks

from clubhub.cogs.ticket_views import (
    TicketControlView,
    TicketEntryView,
    TicketReviewView,
    TicketWarningView,
)

if TYPE_CHECKING:
    from clubhub.bot import ClubHubBot

logger = logging.getLogger("clubhub.tickets")


class TicketCog(commands.Cog, name="Tickets"):
    """Manages the full lifecycle of community assistance requests."""

    def __init__(self, bot: ClubHubBot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
        self.sheets = bot.sheets
        self._accept_lock = asyncio.Lock()
        self.cleanup_watchdog.start()

    def cog_unload(self) -> None:
        self.cleanup_watchdog.cancel()

    # =========================================================================
    # Authorization Helpers
    # =========================================================================

    def is_user_admin(self, user: Union[discord.User, discord.Member]) -> bool:
        if not isinstance(user, discord.Member):
            return False
        if user.guild_permissions.administrator:
            return True
        admin_roles = self.config.roles.admin_roles
        for role in user.roles:
            if role.name in admin_roles or role.id in admin_roles:
                return True
        return False

    def is_user_authorized_for_ticket(
        self, user: Union[discord.User, discord.Member], ticket: Dict[str, Any]
    ) -> bool:
        """Verify whether a user belongs to the handling role for a specific ticket."""
        if not isinstance(user, discord.Member):
            return False
        if self.is_user_admin(user):
            return True

        cat_key = ticket.get("category_key")
        cat_cfg = self.config.tickets.categories.get(cat_key or "")
        allowed_roles = list(cat_cfg.handling_roles) if cat_cfg else []

        # Include general support/private roles as fallbacks
        if not cat_cfg or not cat_cfg.is_sensitive:
            for r in self.config.roles.support_roles:
                if r not in allowed_roles:
                    allowed_roles.append(r)
        else:
            for r in self.config.roles.private_concern_roles:
                if r not in allowed_roles:
                    allowed_roles.append(r)

        for role in user.roles:
            if role.name in allowed_roles or role.id in allowed_roles:
                return True
        return False

    def _resolve_channel(
        self, guild: discord.Guild, channel_ref: Union[str, int]
    ) -> Optional[discord.TextChannel]:
        """Resolve a channel by either numeric ID or case-insensitive name."""
        if isinstance(channel_ref, int) or (isinstance(channel_ref, str) and channel_ref.isdigit()):
            ch = guild.get_channel(int(channel_ref))
            if isinstance(ch, discord.TextChannel):
                return ch
        name = str(channel_ref).lower().lstrip("#")
        return discord.utils.find(lambda c: c.name.lower() == name, guild.text_channels)

    def _resolve_roles(
        self, guild: discord.Guild, role_refs: List[Union[str, int]]
    ) -> List[discord.Role]:
        """Resolve roles by numeric IDs or names."""
        matched: List[discord.Role] = []
        for r_ref in role_refs:
            if isinstance(r_ref, int) or (isinstance(r_ref, str) and r_ref.isdigit()):
                role = guild.get_role(int(r_ref))
                if role:
                    matched.append(role)
                    continue
            name = str(r_ref).lower()
            role = discord.utils.find(lambda r: r.name.lower() == name, guild.roles)
            if role:
                matched.append(role)
        return matched

    # =========================================================================
    # Request Submission Flow (Section 9)
    # =========================================================================

    async def handle_ticket_submission(
        self,
        interaction: discord.Interaction,
        category_key: str,
        subject: str,
        description: str,
    ) -> None:
        """Process a submitted ticket modal and place it in the review queue."""
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Tickets can only be created in servers.", ephemeral=True)
            return

        # Double check 1-ticket limit per Section 9.3
        has_ticket = await self.db.has_active_or_pending_ticket(guild.id, interaction.user.id)
        if has_ticket:
            await interaction.followup.send(
                "⚠️ You already have a pending or active request on this server.",
                ephemeral=True,
            )
            return

        cat_cfg = self.config.tickets.categories.get(category_key)
        if not cat_cfg:
            await interaction.followup.send("Selected category is invalid.", ephemeral=True)
            return

        ticket_id = await self.db.get_next_ticket_id(
            guild.id, prefix=self.config.tickets.ticket_category_prefix
        )

        review_channel = self._resolve_channel(guild, cat_cfg.review_channel)
        if not review_channel:
            logger.error(
                f"Configured review channel '{cat_cfg.review_channel}' for category '{category_key}' not found!"
            )
            await interaction.followup.send(
                "Support routing error: Review channel not found. Please notify an administrator.",
                ephemeral=True,
            )
            return

        # Prepare review queue embed
        embed = discord.Embed(
            title=f"New Request: {ticket_id}",
            description=f"**Category:** {cat_cfg.display_name}\n"
            f"**Requester:** {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"**Subject:** {subject}\n\n"
            f"**Description:**\n{description}",
            color=self.config.community.branding.warning_color
            if cat_cfg.is_sensitive
            else self.config.community.branding.color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text="Private Concern Review Queue" if cat_cfg.is_sensitive else "Support Review Queue"
        )

        # Resolve handling roles with fallback to general support/HR
        resolved_roles = self._resolve_roles(guild, cat_cfg.handling_roles)
        if not resolved_roles:
            fallback = (
                self.config.roles.private_concern_roles
                if cat_cfg.is_sensitive
                else self.config.roles.support_roles
            )
            resolved_roles = self._resolve_roles(guild, fallback)

        handling_role_id = resolved_roles[0].id if resolved_roles else None

        # Mention the handling role (e.g. @Support or @HR) so they receive the request notification
        notify_pings = " ".join(r.mention for r in resolved_roles) if resolved_roles else ""

        review_view = TicketReviewView(self, ticket_id)
        review_msg = await review_channel.send(
            content=notify_pings if notify_pings else None,
            embed=embed,
            view=review_view,
        )

        # Insert record into SQLite in 'pending_review' state
        await self.db.create_ticket(
            ticket_id=ticket_id,
            guild_id=guild.id,
            requester_id=interaction.user.id,
            requester_name=str(interaction.user),
            category_key=category_key,
            category_name=cat_cfg.display_name,
            subject=subject,
            description=description,
            review_channel_id=review_channel.id,
            review_message_id=review_msg.id,
            handling_role_id=handling_role_id,
        )

        await interaction.followup.send(
            f"✅ **Your request has been submitted ({ticket_id})!**\n"
            "An authorized team member will review it shortly. You will receive a direct notification once accepted.",
            ephemeral=True,
        )

    # =========================================================================
    # Staff Review: Acceptance & Decline (Section 9.4, 10)
    # =========================================================================

    async def handle_ticket_accept(self, interaction: discord.Interaction) -> None:
        """Staff acceptance handler provisioning category, text, and voice channels."""
        assert interaction.message is not None
        guild = interaction.guild
        if not guild:
            return

        ticket = await self.db.get_ticket_by_review_message(interaction.message.id)
        if not ticket:
            await interaction.response.send_message(
                "Ticket record could not be found for this review message.", ephemeral=True
            )
            return

        # Check authorization
        if not self.is_user_authorized_for_ticket(interaction.user, ticket):
            await interaction.response.send_message(
                "⛔ You do not have permission to accept this category of request.",
                ephemeral=True,
            )
            return

        async with self._accept_lock:
            # Recheck status to prevent race conditions
            current_ticket = await self.db.get_ticket(ticket["ticket_id"])
            if not current_ticket or current_ticket["status"] != "pending_review":
                await interaction.response.send_message(
                    "⚠️ This request has already been reviewed or accepted by someone else.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()

            bot_member = guild.me
            if not bot_member.guild_permissions.administrator:
                missing_perms = []
                if not bot_member.guild_permissions.manage_channels:
                    missing_perms.append("Manage Channels")
                if not bot_member.guild_permissions.manage_roles:
                    missing_perms.append("Manage Roles / Permissions")
                if missing_perms:
                    await interaction.followup.send(
                        "❌ **Bot Missing Permissions:** The bot cannot create ticket channels because its role is missing:\n"
                        + "\n".join(f"• **{p}**" for p in missing_perms)
                        + "\n\n👉 **Fix:** Open **Server Settings > Roles > Club-Bot > Permissions** and enable **Manage Channels** & **Manage Roles** (or simply grant **Administrator**).",
                        ephemeral=True,
                    )
                    return

            cat_cfg = self.config.tickets.categories.get(ticket["category_key"])
            handling_roles = (
                self._resolve_roles(guild, cat_cfg.handling_roles)
                if cat_cfg
                else self._resolve_roles(guild, self.config.roles.support_roles)
            )

            requester = guild.get_member(ticket["requester_id"])

            # 1. Build Permission Overwrites
            # Only requester, handling roles, and bot can view, message, and join voice in this space
            overwrites: Dict[
                Union[discord.Role, discord.Member], discord.PermissionOverwrite
            ] = {
                guild.default_role: discord.PermissionOverwrite(
                    read_messages=False,
                    view_channel=False,
                    send_messages=False,
                    connect=False,
                ),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                    view_channel=True,
                    connect=True,
                    speak=True,
                ),
            }

            if requester:
                overwrites[requester] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    read_message_history=True,
                    connect=True,
                    speak=True,
                )

            for h_role in handling_roles:
                if not bot_member.guild_permissions.administrator and h_role >= bot_member.top_role:
                    logger.warning(
                        f"Skipping overwrite for role '{h_role.name}' because it ranks above or equal to bot role '{bot_member.top_role.name}'."
                    )
                    continue
                overwrites[h_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    read_message_history=True,
                    connect=True,
                    speak=True,
                )

            # 2. Determine Parent Category (if existing category configured or category creation enabled)
            parent_category: Optional[discord.CategoryChannel] = None
            discord_category: Optional[discord.CategoryChannel] = None
            
            if self.config.tickets.create_category:
                try:
                    discord_category = await guild.create_category(
                        name=ticket["ticket_id"], overwrites=overwrites, reason=f"ClubHub ticket {ticket['ticket_id']}"
                    )
                    parent_category = discord_category
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ **Discord 403 Forbidden:** The bot does not have permission to create categories. "
                        "Please give the `Club-Bot` role the **Manage Channels** or **Administrator** permission.",
                        ephemeral=True,
                    )
                    return
            elif self.config.tickets.parent_category:
                cat_ref = self.config.tickets.parent_category
                if isinstance(cat_ref, int) or (isinstance(cat_ref, str) and str(cat_ref).isdigit()):
                    found_cat = guild.get_channel(int(cat_ref))
                    if isinstance(found_cat, discord.CategoryChannel):
                        parent_category = found_cat
                else:
                    parent_category = discord.utils.find(
                        lambda c: isinstance(c, discord.CategoryChannel) and c.name.lower() == str(cat_ref).lower(),
                        guild.categories,
                    )

            # 3. Create text channel
            channel_name = "discussion" if discord_category else ticket["ticket_id"].lower()
            try:
                text_channel = await guild.create_text_channel(
                    name=channel_name,
                    category=parent_category,
                    overwrites=overwrites,
                    topic=f"Ticket {ticket['ticket_id']} | Requester: {ticket['requester_name']}",
                    reason=f"ClubHub ticket {ticket['ticket_id']}",
                )
            except discord.Forbidden as e:
                logger.error(f"Missing permissions while creating text channel: {e}")
                await interaction.followup.send(
                    "❌ **Discord 403 Forbidden (Missing Permissions):** The bot was denied permission to create this channel.\n\n"
                    "👉 **How to fix:**\n"
                    "1. Go to **Server Settings > Roles > Club-Bot > Permissions**.\n"
                    "2. Enable **Administrator**.\n"
                    "3. Click **Save Changes** and try accepting again!",
                    ephemeral=True,
                )
                return

            # 4. Support Voice channel
            voice_channel: Optional[discord.VoiceChannel] = None
            if self.config.tickets.create_voice_channel and parent_category:
                try:
                    voice_channel = await parent_category.create_voice_channel(
                        name="Support Voice",
                        overwrites=overwrites,
                        reason=f"ClubHub ticket {ticket['ticket_id']}",
                    )
                except Exception as e:
                    logger.warning(f"Could not create voice channel: {e}")

            # 5. Send pinned Control Message in the ticket channel
            control_embed = discord.Embed(
                title=f"{ticket['ticket_id']}",
                color=self.config.community.branding.color,
                timestamp=datetime.now(timezone.utc),
            )
            control_embed.add_field(name="Requester", value=f"<@{ticket['requester_id']}>", inline=True)
            control_embed.add_field(name="Category", value=ticket["category_name"], inline=True)
            control_embed.add_field(name="Accepted by", value=interaction.user.mention, inline=True)
            control_embed.add_field(name="Status", value="🟢 Open", inline=True)
            control_embed.add_field(name="Subject", value=ticket["subject"], inline=False)
            control_embed.add_field(name="Description", value=ticket["description"], inline=False)
            control_embed.set_footer(
                text="Use the button below when finished to safely close this ticket space."
            )

            control_view = TicketControlView(self)
            control_msg = await text_channel.send(
                content=f"<@{ticket['requester_id']}> your ticket has been accepted by {interaction.user.mention}!",
                embed=control_embed,
                view=control_view,
            )
            try:
                await control_msg.pin()
            except Exception:
                pass

            # 6. Atomic transition in DB
            discord_category_id = discord_category.id if discord_category else None
            discord_voice_channel_id = voice_channel.id if voice_channel else None

            success = await self.db.accept_ticket_atomic(
                ticket_id=ticket["ticket_id"],
                accepted_by_id=interaction.user.id,
                accepted_by_name=str(interaction.user),
                discord_category_id=discord_category_id,
                discord_text_channel_id=text_channel.id,
                discord_voice_channel_id=discord_voice_channel_id,
                control_message_id=control_msg.id,
            )

            if not success:
                logger.error(f"Race condition encountered during acceptance of {ticket['ticket_id']}")
                return

            # 7. Update Review Message in Queue
            review_embed = interaction.message.embeds[0]
            review_embed.color = self.config.community.branding.accent_color
            review_embed.add_field(
                name="Outcome",
                value=f"✅ Accepted by {interaction.user.mention} -> {text_channel.mention}",
                inline=False,
            )
            await interaction.message.edit(embed=review_embed, view=None)

            # 8. Notify Requester via DM
            if requester:
                try:
                    dm_embed = discord.Embed(
                        title=f"Request Accepted: {ticket['ticket_id']}",
                        description=f"Your ticket has been accepted by **{interaction.user.display_name}**!\n"
                        f"Please head to {text_channel.mention} to proceed.",
                        color=self.config.community.branding.accent_color,
                    )
                    await requester.send(embed=dm_embed)
                except Exception:
                    pass

    async def handle_ticket_decline(
        self, interaction: discord.Interaction, ticket_id: str, reason: str
    ) -> None:
        """Staff decline handler."""
        ticket = await self.db.get_ticket(ticket_id)
        if not ticket or ticket["status"] != "pending_review":
            await interaction.followup.send(
                "This ticket has already been processed.", ephemeral=True
            )
            return

        await self.db.decline_ticket_atomic(
            ticket_id=ticket_id, declined_by_id=interaction.user.id, reason=reason
        )

        # Update review message
        if interaction.message:
            review_embed = interaction.message.embeds[0]
            review_embed.color = self.config.community.branding.error_color
            review_embed.add_field(
                name="Outcome",
                value=f"✖️ Declined by {interaction.user.mention}\n**Reason:** {reason}",
                inline=False,
            )
            await interaction.message.edit(embed=review_embed, view=None)

        # Notify requester
        guild = interaction.guild
        if guild:
            requester = guild.get_member(ticket["requester_id"])
            if requester:
                try:
                    dm_embed = discord.Embed(
                        title=f"Request Update: {ticket_id}",
                        description=f"Your request has been declined.\n**Reason:** {reason}",
                        color=self.config.community.branding.error_color,
                    )
                    await requester.send(embed=dm_embed)
                except Exception:
                    pass

        # Queue Sheets sync if enabled
        ticket["status"] = "declined"
        ticket["outcome_reason"] = reason
        ticket["closed_by_id"] = interaction.user.id
        await self.sheets.record_ticket_event(ticket, is_sensitive=ticket.get("category_key") == "private_concern")

        await interaction.followup.send(f"Ticket {ticket_id} declined.", ephemeral=True)

    # =========================================================================
    # Ticket Cleanup & Deletion Sequence (Section 11.4)
    # =========================================================================

    async def execute_ticket_closure(
        self,
        ticket_id: str,
        closed_by_user: Optional[Union[discord.User, discord.Member]],
        reason: str,
    ) -> None:
        """Execute the exact 7-step cleanup sequence specified in Section 11.4."""
        ticket = await self.db.get_ticket(ticket_id)
        if not ticket or ticket["status"] not in ("open", "closing"):
            return

        closed_by_id = closed_by_user.id if closed_by_user else 0
        guild = self.bot.get_guild(ticket["guild_id"])

        # 1. Mark the ticket as closing.
        # 2. Save the outcome and closure reason.
        await self.db.mark_ticket_closing(ticket_id, closed_by_id, reason)

        # 3. Delete the linked text channel (by stored ID).
        if guild and ticket["discord_text_channel_id"]:
            t_channel = guild.get_channel(ticket["discord_text_channel_id"])
            if t_channel:
                try:
                    await t_channel.delete(reason=f"ClubHub ticket {ticket_id} cleanup: {reason}")
                except Exception as e:
                    logger.warning(f"Error deleting text channel {t_channel.id}: {e}")

        # 4. Delete the linked voice channel (by stored ID).
        if guild and ticket["discord_voice_channel_id"]:
            v_channel = guild.get_channel(ticket["discord_voice_channel_id"])
            if v_channel:
                try:
                    await v_channel.delete(reason=f"ClubHub ticket {ticket_id} cleanup: {reason}")
                except Exception as e:
                    logger.warning(f"Error deleting voice channel {v_channel.id}: {e}")

        # 5. Delete the ticket category (by stored ID).
        if guild and ticket["discord_category_id"]:
            cat = guild.get_channel(ticket["discord_category_id"])
            if isinstance(cat, discord.CategoryChannel):
                try:
                    await cat.delete(reason=f"ClubHub ticket {ticket_id} cleanup: {reason}")
                except Exception as e:
                    logger.warning(f"Error deleting category {cat.id}: {e}")

        # 6. Mark closure as complete.
        # 7. Requester is now automatically unblocked since status is 'closed'.
        await self.db.mark_ticket_closed(ticket_id)

        # Log to bot log channel
        if guild:
            log_ch = self._resolve_channel(guild, self.config.channels.bot_log_channel)
            if log_ch:
                closer_str = closed_by_user.mention if closed_by_user else "System (Auto-cleanup)"
                log_embed = discord.Embed(
                    title=f"Ticket Closed: {ticket_id}",
                    description=f"**Requester:** <@{ticket['requester_id']}>\n"
                    f"**Closed By:** {closer_str}\n"
                    f"**Reason:** {reason}",
                    color=self.config.community.branding.color,
                    timestamp=datetime.now(timezone.utc),
                )
                try:
                    await log_ch.send(embed=log_embed)
                except Exception:
                    pass

        # DM Requester if closed by system
        if guild and not closed_by_user:
            requester = guild.get_member(ticket["requester_id"])
            if requester:
                try:
                    dm_embed = discord.Embed(
                        title=f"Ticket Closed: {ticket_id}",
                        description=f"Your ticket space was automatically closed due to inactivity.\n"
                        "You are now free to submit a new request whenever needed.",
                        color=self.config.community.branding.color,
                    )
                    await requester.send(embed=dm_embed)
                except Exception:
                    pass

        # Queue Sheets sync if enabled
        ticket["status"] = "closed"
        ticket["outcome_reason"] = reason
        ticket["closed_by_id"] = closed_by_id
        await self.sheets.record_ticket_event(
            ticket, is_sensitive=ticket.get("category_key") == "private_concern"
        )

    # =========================================================================
    # Activity Detection Listeners (Section 11)
    # =========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Text activity handler implementing Section 11.2 rules."""
        if message.author.bot:
            return  # Rule: Bot posts do NOT reset deadline

        if not message.guild:
            return

        ticket = await self.db.get_ticket_by_text_channel(message.channel.id)
        if ticket and ticket["status"] == "open":
            await self.db.update_ticket_activity(ticket["ticket_id"])

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Voice activity handler implementing Section 11.2 rules."""
        if member.bot:
            return

        # Check if left a ticket voice channel
        if before.channel and before.channel != after.channel:
            active_tickets = await self.db.get_active_tickets(member.guild.id)
            for t in active_tickets:
                if t["discord_voice_channel_id"] == before.channel.id:
                    # Check how many humans remain in VC
                    humans = [m for m in before.channel.members if not m.bot]
                    if len(humans) == 0:
                        # Rule: Last human leaves ticket VC -> start a fresh inactivity window
                        await self.db.update_ticket_activity(t["ticket_id"])

    # =========================================================================
    # Auto-Cleanup Watchdog Loop (Section 11)
    # =========================================================================

    @tasks.loop(seconds=60)
    async def cleanup_watchdog(self) -> None:
        """Periodic task that verifies tickets against the OR-based activity policy."""
        cleanup_cfg = self.config.tickets.cleanup
        if not cleanup_cfg.enabled:
            return

        active_tickets = await self.db.get_active_tickets()
        now = datetime.now(timezone.utc)

        for ticket in active_tickets:
            ticket_id = ticket["ticket_id"]
            guild = self.bot.get_guild(ticket["guild_id"])
            if not guild:
                continue

            text_ch = guild.get_channel(ticket["discord_text_channel_id"]) if ticket["discord_text_channel_id"] else None
            voice_ch = guild.get_channel(ticket["discord_voice_channel_id"]) if ticket["discord_voice_channel_id"] else None

            # If both channels have been manually deleted, close out DB state
            if not text_ch and not voice_ch:
                await self.db.mark_ticket_closed(ticket_id)
                continue

            # Check VC occupancy (OR-condition: human in VC suspends automatic closure)
            human_in_vc = False
            if isinstance(voice_ch, discord.VoiceChannel):
                humans_in_voice = [m for m in voice_ch.members if not m.bot]
                if humans_in_voice:
                    human_in_vc = True

            if human_in_vc:
                # Suspend automatic closure while at least one human is connected
                continue

            # Calculate inactivity
            try:
                last_active = datetime.fromisoformat(ticket["last_activity_at"])
            except Exception:
                last_active = now

            elapsed_minutes = (now - last_active).total_seconds() / 60.0
            timeout_min = cleanup_cfg.inactivity_timeout_minutes
            warn_lead_min = cleanup_cfg.warning_lead_time_minutes

            # 1. Timeout reached -> Safe Deletion Sequence
            if elapsed_minutes >= timeout_min:
                # Recheck activity immediately before deletion (Section 11.3)
                recheck_active = False
                if isinstance(text_ch, discord.TextChannel):
                    try:
                        async for msg in text_ch.history(limit=5):
                            if not msg.author.bot:
                                msg_elapsed = (now - msg.created_at).total_seconds() / 60.0
                                if msg_elapsed < timeout_min:
                                    recheck_active = True
                                    break
                    except Exception:
                        pass

                if recheck_active:
                    await self.db.update_ticket_activity(ticket_id)
                    continue

                logger.info(f"Ticket {ticket_id} exceeded inactivity threshold ({timeout_min}m). Cleaning up.")
                await self.execute_ticket_closure(
                    ticket_id=ticket_id,
                    closed_by_user=None,
                    reason=f"Closed due to inactivity ({timeout_min} minutes without activity)",
                )

            # 2. Warning window reached (15m before deadline)
            elif elapsed_minutes >= (timeout_min - warn_lead_min):
                if ticket.get("warned_at") is None and isinstance(text_ch, discord.TextChannel):
                    warn_embed = discord.Embed(
                        title="⚠️ Ticket Inactivity Warning",
                        description=(
                            "This ticket will close soon due to inactivity.\n\n"
                            "Send a message, join the ticket voice channel, "
                            "or select **Keep Open** below if assistance is still needed."
                        ),
                        color=self.config.community.branding.warning_color,
                    )
                    warn_view = TicketWarningView(self, ticket_id)
                    try:
                        await text_ch.send(embed=warn_embed, view=warn_view)
                        await self.db.set_ticket_warned(ticket_id)
                    except Exception as e:
                        logger.warning(f"Failed to post inactivity warning in {text_ch.id}: {e}")

    @cleanup_watchdog.before_loop
    async def before_cleanup_watchdog(self) -> None:
        await self.bot.wait_until_ready()

    # =========================================================================
    # Downtime Recovery (Section 17)
    # =========================================================================

    async def reconcile_tickets_on_startup(self) -> None:
        """Preserve state across bot restarts and grant grace period to overdue tickets."""
        cleanup_cfg = self.config.tickets.cleanup
        if not cleanup_cfg.enabled:
            return

        active_tickets = await self.db.get_active_tickets()
        now = datetime.now(timezone.utc)
        grace_min = cleanup_cfg.restart_grace_period_minutes

        for t in active_tickets:
            try:
                last_active = datetime.fromisoformat(t["last_activity_at"])
                elapsed = (now - last_active).total_seconds() / 60.0
                if elapsed >= cleanup_cfg.inactivity_timeout_minutes:
                    # Grant restart grace period
                    logger.info(
                        f"Ticket {t['ticket_id']} was overdue during downtime. Granting {grace_min}m grace period."
                    )
                    await self.db.update_ticket_activity(t["ticket_id"])
            except Exception:
                pass    # =========================================================================
    # Support Entry Panel Generation (Full-Width Message)
    # =========================================================================

    def build_panel_content(self) -> str:
        """Construct full-width Markdown text for the permanent support entry panel.

        This format replaces narrow discord.Embed boxes so the content flows naturally
        across the full width of the Discord chat window without artificial ~500px limits.
        """
        panel_cfg = self.config.tickets.panel

        lines = [
            f"# 🏛️ {panel_cfg.title}",
        ]
        if panel_cfg.description:
            lines.append(panel_cfg.description)
            lines.append("")

        lines.append("### 📌 Choose a request type below:")

        for cat_cfg in self.config.tickets.categories.values():
            emoji = cat_cfg.emoji or ("🔒" if cat_cfg.is_sensitive else "💬")
            lines.append(f"> {emoji} **{cat_cfg.display_name}**")
            if cat_cfg.description:
                lines.append(f"> *{cat_cfg.description}*")
            lines.append(">")

        if lines and lines[-1] == ">":
            lines.pop()

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ **Click a button below to open a ticket form immediately.**")

        return "\n".join(lines)

    async def post_panel(
        self, channel: discord.abc.Messageable
    ) -> discord.Message:
        """Post the permanent interactive Support Entry Panel as full-width chat content."""
        content = self.build_panel_content()
        view = TicketEntryView(self)
        return await channel.send(content=content, view=view)

    @app_commands.command(
        name="post_support_panel",
        description="Deploy the full-width support entry panel to a channel",
    )
    @app_commands.default_permissions(administrator=True)
    async def post_panel_slash(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Slash command to deploy the full-width support entry panel."""
        if not self.is_user_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Administrator privileges required.", ephemeral=True
            )
            return

        target_ch = channel or interaction.channel
        if not isinstance(target_ch, discord.TextChannel):
            await interaction.response.send_message(
                "⛔ Target must be a standard text channel.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self.post_panel(target_ch)
        await interaction.followup.send(
            f"✅ Full-width support entry panel deployed in {target_ch.mention}!",
            ephemeral=True,
        )


async def setup(bot: ClubHubBot) -> None:
    await bot.add_cog(TicketCog(bot))
