"""Community Cog managing Welcome messages and Personal/Activity Reminders."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from clubhub.bot import ClubHubBot

logger = logging.getLogger("clubhub.community")


def parse_duration_to_seconds(time_str: str) -> Optional[int]:
    """Parse time strings like '10m', '2h', '1d', '30s' into seconds."""
    match = re.match(r"^(\d+)([smhd])$", time_str.lower().strip())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers[unit]


class CommunityCog(commands.Cog, name="Community"):
    """Community onboarding, navigation, and reminders."""

    def __init__(self, bot: ClubHubBot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
        self.reminder_worker.start()

    def cog_unload(self) -> None:
        self.reminder_worker.cancel()

    def _resolve_channel(
        self, guild: discord.Guild, channel_ref: Union[str, int]
    ) -> Optional[discord.TextChannel]:
        if isinstance(channel_ref, int) or (isinstance(channel_ref, str) and channel_ref.isdigit()):
            ch = guild.get_channel(int(channel_ref))
            if isinstance(ch, discord.TextChannel):
                return ch
        name = str(channel_ref).lower().lstrip("#")
        return discord.utils.find(lambda c: c.name.lower() == name, guild.text_channels)

    # =========================================================================
    # Welcome Greetings (Section 14)
    # =========================================================================

    async def send_welcome_greeting(
        self, member: discord.Member, target_channel: Optional[discord.TextChannel] = None
    ) -> tuple[bool, Optional[str]]:
        """Render and dispatch the welcome greeting embed to a target channel."""
        welcome_cfg = self.config.welcome
        guild = member.guild

        welcome_ch = target_channel or self._resolve_channel(guild, self.config.channels.welcome_channel)
        if not welcome_ch:
            return False, f"Configured welcome channel '{self.config.channels.welcome_channel}' could not be resolved."

        rules_ch = self._resolve_channel(guild, welcome_cfg.rules_channel)
        guide_ch = self._resolve_channel(guild, welcome_cfg.guide_channel)
        announcements_ch = self._resolve_channel(guild, welcome_cfg.announcements_channel)
        support_ch = self._resolve_channel(guild, self.config.channels.support_panel_channel)

        rules_mention = rules_ch.mention if rules_ch else f"#{welcome_cfg.rules_channel}"
        guide_mention = guide_ch.mention if guide_ch else f"#{welcome_cfg.guide_channel}"
        ann_mention = announcements_ch.mention if announcements_ch else f"#{welcome_cfg.announcements_channel}"
        support_mention = support_ch.mention if support_ch else f"#{self.config.channels.support_panel_channel}"

        rendered_message = welcome_cfg.message_template.format(
            community_name=self.config.community.name,
            member_mention=member.mention,
            rules_channel_mention=rules_mention,
            guide_channel_mention=guide_mention,
            announcements_channel_mention=ann_mention,
            support_panel_mention=support_mention,
        )

        embed = discord.Embed(
            title=f"Welcome to {self.config.community.name}!",
            description=rendered_message,
            color=self.config.community.branding.color,
            timestamp=datetime.now(timezone.utc),
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await welcome_ch.send(content=member.mention, embed=embed)
            return True, None
        except Exception as e:
            logger.warning(f"Could not send welcome message: {e}")
            return False, str(e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Greet new members and provide links to community orientation channels."""
        if not self.config.welcome.enabled:
            return
        await self.send_welcome_greeting(member)

    @commands.command(name="test_welcome")
    async def test_welcome_cmd(
        self,
        ctx: commands.Context,
        target_member: Optional[discord.Member] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Admin command to simulate and preview a welcome message."""
        admin_roles = self.config.roles.admin_roles
        is_admin = ctx.author.guild_permissions.administrator or any(
            r.name in admin_roles or r.id in admin_roles for r in getattr(ctx.author, "roles", [])
        )
        if not is_admin:
            await ctx.send("⛔ Only Administrators may run the welcome test command.")
            return

        member = target_member or (ctx.author if isinstance(ctx.author, discord.Member) else None)
        if not member:
            await ctx.send("⚠️ Could not determine member context for testing.")
            return

        success, err = await self.send_welcome_greeting(member, target_channel=channel)
        if success:
            dest = channel.mention if channel else f"the configured welcome channel"
            await ctx.send(f"✅ **Welcome message sent to {dest}** for {member.mention}!")
        else:
            await ctx.send(f"⚠️ Failed to send welcome message: {err}")

    @app_commands.command(
        name="test_welcome",
        description="Simulate and preview the welcome greeting card for a member",
    )
    @app_commands.describe(
        member="Optional member to test greeting for (defaults to you)",
        channel="Optional channel to send preview to (defaults to #welcome)",
    )
    async def test_welcome_slash(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Slash command for Admins to simulate and preview the welcome message."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        user_roles = getattr(interaction.user, "roles", [])
        admin_roles = self.config.roles.admin_roles
        is_admin = getattr(interaction.user.guild_permissions, "administrator", False) or any(
            r.name in admin_roles or r.id in admin_roles for r in user_roles
        )
        if not is_admin:
            await interaction.response.send_message(
                "⛔ Only Administrators may test the welcome message.", ephemeral=True
            )
            return

        target_member = member or (interaction.user if isinstance(interaction.user, discord.Member) else None)
        if not target_member:
            await interaction.response.send_message("⚠️ Could not determine member context.", ephemeral=True)
            return

        success, err = await self.send_welcome_greeting(target_member, target_channel=channel)
        if success:
            dest = channel.mention if channel else "the configured welcome channel"
            await interaction.response.send_message(
                f"✅ **Welcome message test sent to {dest}** for {target_member.mention}!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"⚠️ Failed to send welcome message: {err}", ephemeral=True)

    # =========================================================================
    # Reminder System (Section 14)
    # =========================================================================

    @commands.command(name="remindme")
    async def remindme_cmd(self, ctx: commands.Context, duration: str, *, message: str) -> None:
        """Set a personal reminder. Example: !remindme 30m Review project notes"""
        secs = parse_duration_to_seconds(duration)
        if not secs or secs <= 0:
            await ctx.send("⚠️ Invalid duration format. Examples: `10m`, `2h`, `1d`.")
            return

        due_time = datetime.now(timezone.utc) + timedelta(seconds=secs)
        remind_iso = due_time.isoformat()

        rem_id = await self.db.create_reminder(
            guild_id=ctx.guild.id if ctx.guild else 0,
            user_id=ctx.author.id,
            channel_id=ctx.channel.id,
            remind_at=remind_iso,
            message=message,
            is_activity=False,
        )

        await ctx.send(f"⏰ I'll remind you in **{duration}**: \"{message}\" (Reminder #{rem_id})")

    @commands.command(name="remind_event")
    async def remind_event_cmd(
        self, ctx: commands.Context, channel: discord.TextChannel, duration: str, *, message: str
    ) -> None:
        """Organizer command to schedule an activity reminder in a specific channel."""
        # Check organizer permissions
        organizer_roles = self.config.roles.organizer_roles
        is_organizer = ctx.author.guild_permissions.administrator or any(
            r.name in organizer_roles or r.id in organizer_roles for r in ctx.author.roles
        )
        if not is_organizer:
            await ctx.send("⛔ Only organizers may schedule channel activity reminders.")
            return

        secs = parse_duration_to_seconds(duration)
        if not secs or secs <= 0:
            await ctx.send("⚠️ Invalid duration format. Examples: `15m`, `1h`.")
            return

        due_time = datetime.now(timezone.utc) + timedelta(seconds=secs)
        rem_id = await self.db.create_reminder(
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            channel_id=channel.id,
            remind_at=due_time.isoformat(),
            message=message,
            is_activity=True,
        )

        await ctx.send(f"📢 Activity reminder #{rem_id} scheduled for {channel.mention} in **{duration}**.")

    @tasks.loop(seconds=30)
    async def reminder_worker(self) -> None:
        """Poll and deliver due reminders."""
        due_list = await self.db.get_due_reminders()
        for rem in due_list:
            rem_id = rem["reminder_id"]
            channel_id = rem["channel_id"]
            user_id = rem["user_id"]
            msg_text = rem["message"]
            is_activity = bool(rem["is_activity"])

            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    prefix = "📢 **Community Activity Reminder:**" if is_activity else f"⏰ <@{user_id}> **Reminder:**"
                    embed = discord.Embed(
                        description=msg_text,
                        color=self.config.community.branding.color,
                        timestamp=datetime.now(timezone.utc),
                    )
                    await channel.send(content=prefix, embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send reminder #{rem_id} to channel {channel_id}: {e}")
            else:
                # If channel not found, try sending DM to user
                user = self.bot.get_user(user_id)
                if user:
                    try:
                        await user.send(f"⏰ **Reminder:** {msg_text}")
                    except Exception:
                        pass

            await self.db.mark_reminder_delivered(rem_id)

    @reminder_worker.before_loop
    async def before_reminder_worker(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: ClubHubBot) -> None:
    await bot.add_cog(CommunityCog(bot))
