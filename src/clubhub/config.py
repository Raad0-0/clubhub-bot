"""Configuration manager and schema validation for ClubHub."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from dotenv import load_dotenv


@dataclass
class CommunityBranding:
    color: int = 0x5865F2
    accent_color: int = 0x57F287
    warning_color: int = 0xFEE75C
    error_color: int = 0xED4245


@dataclass
class CommunityConfig:
    name: str = "Community ClubHub"
    prefix: str = "!"
    branding: CommunityBranding = field(default_factory=CommunityBranding)


@dataclass
class RolesConfig:
    admin_roles: List[Union[str, int]] = field(default_factory=lambda: ["Administrator"])
    organizer_roles: List[Union[str, int]] = field(default_factory=lambda: ["Organizer", "Committee"])
    support_roles: List[Union[str, int]] = field(default_factory=lambda: ["Support Team"])
    private_concern_roles: List[Union[str, int]] = field(default_factory=lambda: ["Welfare Officer", "HR"])


@dataclass
class ChannelsConfig:
    welcome_channel: Union[str, int] = "welcome"
    events_channel: Union[str, int] = "events"
    event_qa_review_channel: Union[str, int] = "meeting-planning"
    bot_log_channel: Union[str, int] = "bot-log"
    support_panel_channel: Union[str, int] = "open-a-ticket"


@dataclass
class TicketCategoryConfig:
    key: str
    display_name: str
    description: str
    review_channel: Union[str, int]
    handling_roles: List[Union[str, int]]
    is_sensitive: bool = False


@dataclass
class TicketCleanupConfig:
    enabled: bool = True
    inactivity_timeout_minutes: int = 120
    warning_lead_time_minutes: int = 15
    restart_grace_period_minutes: int = 30
    check_interval_seconds: int = 60


@dataclass
class TicketPanelConfig:
    title: str = "COMMUNITY SUPPORT"
    description: str = "Need assistance or want to raise a concern?\nSubmit a request for the appropriate team to review."
    button_label: str = "Create Ticket"
    button_emoji: str = "📩"


@dataclass
class TicketsConfig:
    one_ticket_per_member: bool = True
    ticket_category_prefix: str = "TICKET"
    cleanup: TicketCleanupConfig = field(default_factory=TicketCleanupConfig)
    panel: TicketPanelConfig = field(default_factory=TicketPanelConfig)
    categories: Dict[str, TicketCategoryConfig] = field(default_factory=dict)


@dataclass
class SheetsConfig:
    enabled: bool = False
    spreadsheet_id: str = ""
    support_worksheet: str = "Ticket Register"
    sensitive_worksheet: str = "Sensitive Register"
    credentials_file: Optional[str] = None


@dataclass
class WelcomeConfig:
    enabled: bool = True
    rules_channel: Union[str, int] = "rules"
    guide_channel: Union[str, int] = "server-guide"
    announcements_channel: Union[str, int] = "announcements"
    message_template: str = (
        "Welcome to **{community_name}**, {member_mention}! 👋\n\n"
        "Please take a moment to review:\n"
        "• {rules_channel_mention} for our community guidelines\n"
        "• {guide_channel_mention} for getting started\n"
        "• {announcements_channel_mention} for current news\n\n"
        "Need help? Visit {support_panel_mention} to request assistance."
    )


@dataclass
class EventsConfig:
    default_timezone: str = "UTC"
    allow_member_questions: bool = True
    reminder_lead_times_minutes: List[int] = field(default_factory=lambda: [60, 15])


@dataclass
class AppConfig:
    discord_token: str
    database_path: str = "clubhub.db"
    log_level: str = "INFO"
    community: CommunityConfig = field(default_factory=CommunityConfig)
    roles: RolesConfig = field(default_factory=RolesConfig)
    channels: ChannelsConfig = field(default_factory=ChannelsConfig)
    tickets: TicketsConfig = field(default_factory=TicketsConfig)
    sheets_reporting: SheetsConfig = field(default_factory=SheetsConfig)
    welcome: WelcomeConfig = field(default_factory=WelcomeConfig)
    events: EventsConfig = field(default_factory=EventsConfig)

    def validate(self) -> None:
        """Validate startup configuration integrity according to proposal specifications."""
        if not self.discord_token:
            raise ValueError("DISCORD_TOKEN must be specified in the environment or .env file.")

        if not self.tickets.categories:
            raise ValueError("At least one ticket category must be configured in tickets.categories.")

        cleanup = self.tickets.cleanup
        if cleanup.enabled:
            if cleanup.inactivity_timeout_minutes <= 0:
                raise ValueError("inactivity_timeout_minutes must be greater than 0.")
            if cleanup.warning_lead_time_minutes <= 0:
                raise ValueError("warning_lead_time_minutes must be greater than 0.")
            if cleanup.warning_lead_time_minutes >= cleanup.inactivity_timeout_minutes:
                raise ValueError(
                    f"warning_lead_time_minutes ({cleanup.warning_lead_time_minutes}) must be less than "
                    f"inactivity_timeout_minutes ({cleanup.inactivity_timeout_minutes})."
                )

        if self.sheets_reporting.enabled:
            if not self.sheets_reporting.spreadsheet_id:
                raise ValueError("spreadsheet_id must be provided when sheets_reporting is enabled.")


def load_config(config_path: Union[str, Path] = "config.yaml", env_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML file and merge with environment variables."""
    load_dotenv(dotenv_path=env_path)

    discord_token = os.getenv("DISCORD_TOKEN", "")
    database_path = os.getenv("DATABASE_PATH", "clubhub.db")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    google_creds = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

    path = Path(config_path)
    raw_cfg: Dict[str, Any] = {}
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}

    # Community
    comm_data = raw_cfg.get("community", {})
    branding_data = comm_data.get("branding", {})
    branding = CommunityBranding(
        color=branding_data.get("color", 0x5865F2),
        accent_color=branding_data.get("accent_color", 0x57F287),
        warning_color=branding_data.get("warning_color", 0xFEE75C),
        error_color=branding_data.get("error_color", 0xED4245),
    )
    community = CommunityConfig(
        name=comm_data.get("name", "Community ClubHub"),
        prefix=comm_data.get("prefix", "!"),
        branding=branding,
    )

    # Roles
    roles_data = raw_cfg.get("roles", {})
    roles = RolesConfig(
        admin_roles=roles_data.get("admin_roles", ["Administrator"]),
        organizer_roles=roles_data.get("organizer_roles", ["Organizer", "Committee"]),
        support_roles=roles_data.get("support_roles", ["Support Team"]),
        private_concern_roles=roles_data.get("private_concern_roles", ["Welfare Officer", "HR"]),
    )

    # Channels
    channels_data = raw_cfg.get("channels", {})
    channels = ChannelsConfig(
        welcome_channel=channels_data.get("welcome_channel", "welcome"),
        events_channel=channels_data.get("events_channel", "events"),
        event_qa_review_channel=channels_data.get("event_qa_review_channel", "meeting-planning"),
        bot_log_channel=channels_data.get("bot_log_channel", "bot-log"),
        support_panel_channel=channels_data.get("support_panel_channel", "open-a-ticket"),
    )

    # Tickets
    tickets_data = raw_cfg.get("tickets", {})
    cleanup_data = tickets_data.get("cleanup", {})
    cleanup = TicketCleanupConfig(
        enabled=cleanup_data.get("enabled", True),
        inactivity_timeout_minutes=int(cleanup_data.get("inactivity_timeout_minutes", 120)),
        warning_lead_time_minutes=int(cleanup_data.get("warning_lead_time_minutes", 15)),
        restart_grace_period_minutes=int(cleanup_data.get("restart_grace_period_minutes", 30)),
        check_interval_seconds=int(cleanup_data.get("check_interval_seconds", 60)),
    )

    panel_data = tickets_data.get("panel", {})
    panel = TicketPanelConfig(
        title=panel_data.get("title", "COMMUNITY SUPPORT"),
        description=panel_data.get("description", "Need assistance or want to raise a concern?\nSubmit a request for the appropriate team to review."),
        button_label=panel_data.get("button_label", "Create Ticket"),
        button_emoji=panel_data.get("button_emoji", "📩"),
    )

    # Categories
    categories: Dict[str, TicketCategoryConfig] = {}
    raw_cats = tickets_data.get("categories", {})
    if not raw_cats:
        # Default starter categories if none supplied in yaml
        categories["general_assistance"] = TicketCategoryConfig(
            key="general_assistance",
            display_name="General Assistance",
            description="General questions and support",
            review_channel="support-review",
            handling_roles=["Support Team"],
            is_sensitive=False,
        )
        categories["private_concern"] = TicketCategoryConfig(
            key="private_concern",
            display_name="Complaint / Private Concern",
            description="Confidential complaints or welfare concerns",
            review_channel="private-review",
            handling_roles=["Welfare Officer", "HR"],
            is_sensitive=True,
        )
    else:
        for cat_key, cat_val in raw_cats.items():
            categories[cat_key] = TicketCategoryConfig(
                key=cat_key,
                display_name=cat_val.get("display_name", cat_key),
                description=cat_val.get("description", ""),
                review_channel=cat_val.get("review_channel", "support-review"),
                handling_roles=cat_val.get("handling_roles", ["Support Team"]),
                is_sensitive=bool(cat_val.get("is_sensitive", False)),
            )

    tickets = TicketsConfig(
        one_ticket_per_member=tickets_data.get("one_ticket_per_member", True),
        ticket_category_prefix=tickets_data.get("ticket_category_prefix", "TICKET"),
        cleanup=cleanup,
        panel=panel,
        categories=categories,
    )

    # Sheets
    sheets_data = raw_cfg.get("sheets_reporting", {})
    sheets = SheetsConfig(
        enabled=sheets_data.get("enabled", False),
        spreadsheet_id=sheets_data.get("spreadsheet_id", ""),
        support_worksheet=sheets_data.get("support_worksheet", "Ticket Register"),
        sensitive_worksheet=sheets_data.get("sensitive_worksheet", "Sensitive Register"),
        credentials_file=google_creds or sheets_data.get("credentials_file"),
    )

    # Welcome
    welcome_data = raw_cfg.get("welcome", {})
    welcome = WelcomeConfig(
        enabled=welcome_data.get("enabled", True),
        rules_channel=welcome_data.get("rules_channel", "rules"),
        guide_channel=welcome_data.get("guide_channel", "server-guide"),
        announcements_channel=welcome_data.get("announcements_channel", "announcements"),
        message_template=welcome_data.get(
            "message_template",
            WelcomeConfig.message_template,
        ),
    )

    # Events
    events_data = raw_cfg.get("events", {})
    events = EventsConfig(
        default_timezone=events_data.get("default_timezone", "UTC"),
        allow_member_questions=events_data.get("allow_member_questions", True),
        reminder_lead_times_minutes=events_data.get("reminder_lead_times_minutes", [60, 15]),
    )

    app_config = AppConfig(
        discord_token=discord_token,
        database_path=database_path,
        log_level=log_level,
        community=community,
        roles=roles,
        channels=channels,
        tickets=tickets,
        sheets_reporting=sheets,
        welcome=welcome,
        events=events,
    )

    return app_config
