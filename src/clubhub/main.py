"""Main entrypoint for ClubHub."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
import discord

from clubhub.bot import ClubHubBot
from clubhub.config import load_config


def setup_logging(log_level: str = "INFO") -> None:
    """Configure formatted logging to stdout."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> None:
    """Run the ClubHub Discord bot."""
    config_file = "config.yaml"
    if not Path(config_file).exists() and Path("config.example.yaml").exists():
        config_file = "config.example.yaml"

    try:
        config = load_config(config_path=config_file)
        setup_logging(config.log_level)
    except Exception as e:
        print(f"Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        config.validate()
    except ValueError as e:
        logging.error(f"Configuration Validation Error: {e}")
        logging.error("Please review your config.yaml and .env settings.")
        sys.exit(1)

    bot = ClubHubBot(config=config)

    try:
        bot.run(config.discord_token)
    except discord.LoginFailure:
        logging.error("Invalid Discord Bot Token provided in DISCORD_TOKEN.")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Exiting cleanly.")
    except Exception as e:
        logging.critical(f"Fatal error during bot execution: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
