"""Unit tests for ClubHub configuration loading and validation."""

import pytest
from clubhub.config import AppConfig, TicketCleanupConfig, TicketCategoryConfig, load_config


def test_default_config_loading(tmp_path):
    """Test loading configuration with fallback defaults."""
    cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
    assert cfg.community.name == "Community ClubHub"
    assert "general_assistance" in cfg.tickets.categories
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
