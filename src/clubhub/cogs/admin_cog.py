"""Admin Cog for deployment of UI panels, status reports, and maintenance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands
from clubhub.cogs.ticket_views import TicketEntryView

if TYPE_CHECKING:
    from clubhub.bot import ClubHubBot

logger = logging.getLogger("clubhub.admin")


class AdminCog(commands.Cog, name="Admin"):
    """Administrative maintenance and setup tools for server administrators."""

    def __init__(self, bot: ClubHubBot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db

    def is_admin(self, user: Union[discord.User, discord.Member]) -> bool:
        if not isinstance(user, discord.Member):
            return False
        if user.guild_permissions.administrator:
            return True
        admin_roles = self.config.roles.admin_roles
        for role in user.roles:
            if role.name in admin_roles or role.id in admin_roles:
                return True
        return False

    @commands.command(name="post_panel")
    async def post_panel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        """Post the permanent interactive Support Entry Panel with the [Create Ticket] button."""
        if not self.is_admin(ctx.author):
            await ctx.send("⛔ Only community administrators may post the support panel.")
            return

        target_ch = channel or ctx.channel
        panel_cfg = self.config.tickets.panel

        embed = discord.Embed(
            title=panel_cfg.title,
            description=panel_cfg.description,
            color=self.config.community.branding.color,
        )

        # List available categories with their descriptions
        cat_lines = []
        for cat_cfg in self.config.tickets.categories.values():
            emoji = cat_cfg.emoji or ("🔒" if cat_cfg.is_sensitive else "💬")
            cat_lines.append(f"{emoji} **{cat_cfg.display_name}**\n*{cat_cfg.description}*")

        if cat_lines:
            embed.add_field(
                name="Choose a request type below:",
                value="\n\n".join(cat_lines),
                inline=False,
            )
        embed.set_footer(text="Click a button below to open a ticket form immediately.")

        ticket_cog = self.bot.get_cog("Tickets")
        view = TicketEntryView(ticket_cog)  # type: ignore

        await target_ch.send(embed=embed, view=view)
        if target_ch != ctx.channel:
            await ctx.send(f"✅ Support entry panel deployed in {target_ch.mention}!")

    @commands.group(name="clubhub", invoke_without_command=True)
    async def clubhub_group(self, ctx: commands.Context) -> None:
        """ClubHub administration tools."""
        await ctx.send(
            "ClubHub Admin Commands:\n"
            "`!post_panel` - Deploy the permanent ticket entry panel\n"
            "`!clubhub status` - View operational statistics\n"
            "`!clubhub sync` - Sync slash commands with Discord"
        )

    @clubhub_group.command(name="status")
    async def status_cmd(self, ctx: commands.Context) -> None:
        """View operational statistics and database health."""
        if not self.is_admin(ctx.author):
            await ctx.send("⛔ Administrator access required.")
            return

        active_tickets = await self.db.get_active_tickets()
        pending_tickets = await self.db.get_pending_tickets()

        embed = discord.Embed(
            title="ClubHub Operational Status",
            color=self.config.community.branding.color,
        )
        embed.add_field(name="Community", value=self.config.community.name, inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Active Tickets", value=str(len(active_tickets)), inline=True)
        embed.add_field(name="Pending Review", value=str(len(pending_tickets)), inline=True)
        embed.add_field(
            name="Google Sheets Sync",
            value="Enabled" if self.config.sheets_reporting.enabled else "Disabled",
            inline=True,
        )
        await ctx.send(embed=embed)

    @clubhub_group.command(name="sync")
    async def sync_cmd(self, ctx: commands.Context) -> None:
        """Synchronize application commands with Discord."""
        if not self.is_admin(ctx.author):
            await ctx.send("⛔ Administrator access required.")
            return

        synced = await self.bot.tree.sync()
        await ctx.send(f"✅ Successfully synchronized {len(synced)} application commands.")


async def setup(bot: ClubHubBot) -> None:
    await bot.add_cog(AdminCog(bot))
