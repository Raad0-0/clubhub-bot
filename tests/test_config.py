"""Unit tests for ClubHub configuration loading and validation."""

import pytest
from clubhub.config import AppConfig, TicketCleanupConfig, TicketCategoryConfig, load_config


def test_default_config_loading(tmp_path):
    """Test loading configuration with fallback defaults."""
    cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
    assert cfg.community.name == "Community ClubHub"
    assert "study_help" in cfg.tickets.categories
    assert "private_concern" in cfg.tickets.categories
    assert cfg.tickets.cleanup.inactivity_timeout_minutes == 120
    assert cfg.tickets.cleanup.warning_lead_time_minutes == 15


def test_validation_missing_token():
    """Validation should fail if DISCORD_TOKEN is empty."""
    cfg = AppConfig(discord_token="")
    cfg.tickets.categories["general"] = TicketCategoryConfig(
        key="general",
        display_name="General",
        description="General Help",
        review_channel="support-review",
        handling_roles=["Support Team"],
    )
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        cfg.validate()


def test_validation_empty_categories():
    """Validation should fail if no ticket categories are configured."""
    cfg = AppConfig(discord_token="fake_token")
    cfg.tickets.categories = {}
    with pytest.raises(ValueError, match="ticket category must be configured"):
        cfg.validate()


def test_validation_invalid_inactivity_warning_threshold():
    """Warning lead time cannot be greater than or equal to total inactivity timeout."""
    cfg = AppConfig(discord_token="fake_token")
    cfg.tickets.categories["general"] = TicketCategoryConfig(
        key="general",
        display_name="General",
        description="General",
        review_channel="support",
        handling_roles=["Support"],
    )
    cfg.tickets.cleanup.inactivity_timeout_minutes = 30
    cfg.tickets.cleanup.warning_lead_time_minutes = 30

    with pytest.raises(ValueError, match="must be less than"):
        cfg.validate()


def test_validation_sheets_without_spreadsheet_id():
    """If sheets reporting is enabled, spreadsheet_id must not be empty."""
    cfg = AppConfig(discord_token="fake_token")
    cfg.tickets.categories["general"] = TicketCategoryConfig(
        key="general",
        display_name="General",
        description="General",
        review_channel="support",
        handling_roles=["Support"],
    )
    cfg.sheets_reporting.enabled = True
    cfg.sheets_reporting.spreadsheet_id = ""

    with pytest.raises(ValueError, match="spreadsheet_id must be provided"):
        cfg.validate()


def test_ticket_entry_view_category_buttons():
    """Verify that TicketEntryView generates a button for each configured category."""
    from unittest.mock import MagicMock
    from clubhub.cogs.ticket_views import TicketEntryView

    mock_cog = MagicMock()
    mock_cog.config.tickets.categories = {
        "cat1": TicketCategoryConfig(
            key="cat1",
            display_name="Category 1",
            description="Desc 1",
            review_channel="ch1",
            handling_roles=["Role1"],
        ),
        "cat2": TicketCategoryConfig(
            key="cat2",
            display_name="Category 2",
            description="Desc 2",
            review_channel="ch2",
            handling_roles=["Role2"],
            is_sensitive=True,
        ),
    }

    view = TicketEntryView(mock_cog)
    assert len(view.children) == 2
    button1 = view.children[0]
    button2 = view.children[1]

    assert button1.label == "Category 1"
    assert button1.custom_id == "clubhub:create_ticket:cat1"
    assert button2.label == "Category 2"
    assert button2.custom_id == "clubhub:create_ticket:cat2"
    assert str(button2.emoji) == "🔒"
    assert button1.row == 0
    assert button2.row == 0


def test_ticket_entry_view_symmetrical_rows():
    """Verify that 4 buttons are split symmetrically 2x2 across rows 0 and 1."""
    from unittest.mock import MagicMock
    from clubhub.cogs.ticket_views import TicketEntryView

    mock_cog = MagicMock()
    mock_cog.config.tickets.panel.buttons_per_row = 2
    mock_cog.config.tickets.categories = {
        f"cat{i}": TicketCategoryConfig(
            key=f"cat{i}",
            display_name=f"Cat {i}",
            description=f"Desc {i}",
            review_channel="ch",
            handling_roles=["Role"],
        )
        for i in range(1, 5)
    }

    view = TicketEntryView(mock_cog)
    assert len(view.children) == 4
    assert view.children[0].row == 0
    assert view.children[1].row == 0
    assert view.children[2].row == 1
    assert view.children[3].row == 1


def test_ticket_entry_view_single_row_4_buttons():
    """Verify that 4 buttons are positioned on a single row (row 0) when buttons_per_row is 4."""
    from unittest.mock import MagicMock
    from clubhub.cogs.ticket_views import TicketEntryView

    mock_cog = MagicMock()
    mock_cog.config.tickets.panel.buttons_per_row = 4
    mock_cog.config.tickets.categories = {
        f"cat{i}": TicketCategoryConfig(
            key=f"cat{i}",
            display_name=f"Cat {i}",
            description=f"Desc {i}",
            review_channel="ch",
            handling_roles=["Role"],
        )
        for i in range(1, 5)
    }

    view = TicketEntryView(mock_cog)
    assert len(view.children) == 4
    assert all(child.row == 0 for child in view.children)


def test_ticket_cog_full_width_panel_content():
    """Verify that build_panel_content produces full-width markdown without embed limitations."""
    from unittest.mock import MagicMock
    from clubhub.cogs.ticket_cog import TicketCog

    mock_bot = MagicMock()
    mock_bot.config.tickets.panel.title = "COMMUNITY SUPPORT"
    mock_bot.config.tickets.panel.description = "Need assistance? Click below."
    mock_bot.config.tickets.categories = {
        "study": TicketCategoryConfig(
            key="study",
            display_name="Study Help",
            description="Academic guidance and coursework",
            review_channel="support-review",
            handling_roles=["Support"],
            emoji="📖",
        )
    }

    # Instantiate cog without starting watchdog task in test
    cog = TicketCog.__new__(TicketCog)
    cog.bot = mock_bot
    cog.config = mock_bot.config

    content = cog.build_panel_content()
    assert isinstance(content, str)
    assert "# 🏛️ COMMUNITY SUPPORT" in content
    assert "Need assistance? Click below." in content
    assert "### 📌 Choose a request type below:" in content
    assert "> 📖 **Study Help**" in content
    assert "> *Academic guidance and coursework*" in content
    assert "Click a button below to open a ticket form immediately." in content


def test_ticket_category_button_distinct_colors():
    """Verify that buttons receive distinct colors and styles."""
    import discord
    from unittest.mock import MagicMock
    from clubhub.cogs.ticket_views import TicketCategoryButton

    mock_cog = MagicMock()

    cfg_study = TicketCategoryConfig(
        key="study_help", display_name="Study Help", description="Academic",
        review_channel="ch", handling_roles=["Role"], button_style="primary"
    )
    cfg_member = TicketCategoryConfig(
        key="membership_question", display_name="Membership", description="Status",
        review_channel="ch", handling_roles=["Role"], button_style="grey"
    )
    cfg_project = TicketCategoryConfig(
        key="project_help", display_name="Project Help", description="Projects",
        review_channel="ch", handling_roles=["Role"], button_style="green"
    )
    cfg_concern = TicketCategoryConfig(
        key="private_concern", display_name="Complaint", description="Confidential",
        review_channel="ch", handling_roles=["Role"], button_style="red"
    )

    btn_study = TicketCategoryButton(mock_cog, "study_help", cfg_study)
    btn_member = TicketCategoryButton(mock_cog, "membership_question", cfg_member)
    btn_project = TicketCategoryButton(mock_cog, "project_help", cfg_project)
    btn_concern = TicketCategoryButton(mock_cog, "private_concern", cfg_concern)

    assert btn_study.style == discord.ButtonStyle.primary
    assert btn_member.style == discord.ButtonStyle.secondary
    assert btn_project.style == discord.ButtonStyle.success
    assert btn_concern.style == discord.ButtonStyle.danger


def test_event_channel_and_management_role_config(tmp_path):
    """Verify event_management_channel configuration and Event Management role inclusion."""
    cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
    assert cfg.channels.event_management_channel == "create-event"
    assert "Event Management" in cfg.roles.organizer_roles
    assert "Admin" in cfg.roles.admin_roles or "Administrator" in cfg.roles.admin_roles


def test_event_management_panel_content():
    """Verify the event creation instructions panel contains comprehensive command syntax and role restrictions."""
    from unittest.mock import MagicMock
    from clubhub.cogs.events_cog import EventsCog

    mock_bot = MagicMock()
    mock_bot.config.community.branding.color = 0x5865F2
    mock_bot.config.roles.organizer_roles = ["Event Management", "Organizer"]
    mock_bot.config.roles.admin_roles = ["Admin", "Administrator"]

    cog = EventsCog(mock_bot)
    panel = cog.build_event_management_panel()

    # Role restriction mentions
    assert "Administrators" in panel
    assert "Event Management" in panel

    # Command instructions
    assert "!event create" in panel
    assert "!event publish" in panel
    assert "!event conclude" in panel
    assert "!event delete" in panel
    assert "!event manage" in panel
    assert "!event summary" in panel
    assert "!event list" in panel
    assert "!event cancel" in panel

    # Syntax examples & details
    assert "YYYY-MM-DD" in panel
    assert "Open Event Creation Form" in panel

    # Discord message length limit (must be <= 2,000 characters)
    assert len(panel) <= 1950


def test_event_standalone_command_shortcuts():
    """Verify that standalone command shortcuts like !event_create exist."""
    from unittest.mock import MagicMock
    from clubhub.cogs.events_cog import EventsCog

    mock_bot = MagicMock()
    cog = EventsCog(mock_bot)
    commands_map = {cmd.name: cmd for cmd in cog.get_commands()}

    assert "event_create" in commands_map
    assert "event_publish" in commands_map
    assert "event_conclude" in commands_map
    assert "event_delete" in commands_map
    assert "event_manage" in commands_map
    assert "event_summary" in commands_map
    assert "event_list" in commands_map
    assert "event_cancel" in commands_map
    assert "post_event_panel" in commands_map
    assert "setup_event_channel" in commands_map


def test_event_creation_launch_view_buttons():
    """Verify EventCreateLaunchView persistent custom_ids and button presence."""
    from unittest.mock import MagicMock
    from clubhub.cogs.events_cog import EventCreateLaunchView

    mock_cog = MagicMock()
    view = EventCreateLaunchView(mock_cog)

    custom_ids = [child.custom_id for child in view.children if hasattr(child, "custom_id")]
    assert "clubhub:launch_event_create" in custom_ids
    assert "clubhub:launch_event_list" in custom_ids


def test_is_user_organizer_permissions():
    """Verify that only Admin and Event Management are granted organizer rights."""
    from unittest.mock import MagicMock
    from clubhub.cogs.events_cog import EventsCog

    mock_bot = MagicMock()
    mock_bot.config.roles.admin_roles = ["Admin", "Administrator"]
    mock_bot.config.roles.organizer_roles = ["Event Management", "Organizer"]

    cog = EventsCog(mock_bot)

    # 1. Administrator via guild permission
    admin_member = MagicMock()
    admin_member.guild_permissions.administrator = True
    assert cog.is_user_organizer(admin_member) is True

    # 2. Member with 'Event Management' role
    event_mgr_role = MagicMock()
    event_mgr_role.name = "Event Management"
    event_mgr_role.id = 12345
    event_mgr_member = MagicMock()
    event_mgr_member.guild_permissions.administrator = False
    event_mgr_member.roles = [event_mgr_role]
    assert cog.is_user_organizer(event_mgr_member) is True

    # 3. Member with 'Admin' role (case-insensitive)
    admin_role = MagicMock()
    admin_role.name = "admin"
    admin_role.id = 54321
    admin_role_member = MagicMock()
    admin_role_member.guild_permissions.administrator = False
    admin_role_member.roles = [admin_role]
    assert cog.is_user_organizer(admin_role_member) is True

    # 4. Regular member with no organizer/admin roles
    regular_role = MagicMock()
    regular_role.name = "Member"
    regular_role.id = 99999
    regular_member = MagicMock()
    regular_member.guild_permissions.administrator = False
    regular_member.roles = [regular_role]
    assert cog.is_user_organizer(regular_member) is False


def test_calendar_date_and_time_validation():
    """Verify that parse_and_validate_calendar_event strictly validates calendar dates and generates Discord timestamps."""
    from clubhub.cogs.events_cog import parse_and_validate_calendar_event

    # 1. Valid official calendar date and time
    is_valid, formatted, ts, err = parse_and_validate_calendar_event("2026-11-20", "06:30 PM UTC")
    assert is_valid is True
    assert err is None
    assert ts is not None
    assert f"<t:{ts}:F>" in formatted
    assert f"<t:{ts}:R>" in formatted
    assert "2026-11-20" in formatted

    # 2. Invalid calendar day (e.g. Feb 30 does not exist in any calendar)
    is_valid, formatted, ts, err = parse_and_validate_calendar_event("2026-02-30", "10:00 AM UTC")
    assert is_valid is False
    assert err is not None
    assert "Invalid Calendar Date" in err

    # 3. Invalid month (e.g. month 13)
    is_valid, formatted, ts, err = parse_and_validate_calendar_event("2026-13-01", "12:00 PM")
    assert is_valid is False
    assert err is not None

    # 4. Empty inputs
    is_valid, formatted, ts, err = parse_and_validate_calendar_event("", "")
    assert is_valid is False
    assert err is not None
    assert "required" in err.lower()


def test_event_create_launch_view_buttons():
    """Verify that EventCreateLaunchView includes Create, List, and Manage buttons."""
    from unittest.mock import MagicMock
    from clubhub.cogs.events_cog import EventCreateLaunchView

    mock_cog = MagicMock()
    view = EventCreateLaunchView(mock_cog)
    assert len(view.children) == 3

    custom_ids = [child.custom_id for child in view.children]
    assert "clubhub:launch_event_create" in custom_ids
    assert "clubhub:launch_event_list" in custom_ids
    assert "clubhub:launch_event_manage" in custom_ids


@pytest.mark.asyncio
async def test_send_welcome_greeting():
    """Verify send_welcome_greeting properly formats and dispatches the welcome embed."""
    from unittest.mock import AsyncMock, MagicMock
    from clubhub.cogs.community_cog import CommunityCog

    mock_bot = MagicMock()
    mock_bot.config.community.name = "Test Community"
    mock_bot.config.community.branding.color = 0x5865F2
    mock_bot.config.channels.welcome_channel = "welcome"
    mock_bot.config.channels.support_panel_channel = "open-a-ticket"
    mock_bot.config.welcome.rules_channel = "rules"
    mock_bot.config.welcome.guide_channel = "server-guide"
    mock_bot.config.welcome.announcements_channel = "announcements"
    mock_bot.config.welcome.message_template = "Welcome to {community_name}, {member_mention}!"

    cog = CommunityCog(mock_bot)
    cog.reminder_worker.cancel()

    mock_member = MagicMock()
    mock_member.mention = "<@12345>"
    mock_member.display_avatar = None
    mock_member.guild = MagicMock()
    mock_member.guild.text_channels = []
    mock_member.guild.get_channel = MagicMock(return_value=None)

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()

    success, err = await cog.send_welcome_greeting(mock_member, target_channel=mock_channel)
    assert success is True
    assert err is None
    mock_channel.send.assert_called_once()
    _, kwargs = mock_channel.send.call_args
    assert kwargs["content"] == "<@12345>"
    assert "Welcome to Test Community" in kwargs["embed"].description

