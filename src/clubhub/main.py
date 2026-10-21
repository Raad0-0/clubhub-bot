"""Main entrypoint for ClubHub."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
import discord

from clubhub.bot import ClubHubBot
from clubhub.config import AppConfig, load_config
from clubhub.web_health import start_web_server, stop_web_server


def setup_logging(log_level: str = "INFO") -> None:
    """Configure formatted logging to stdout."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def run_bot_with_web_server(config: AppConfig) -> None:
    """Run both the HTTP health check server and Discord bot concurrently in the same event loop."""
    port = int(os.environ.get("PORT", 10000))
    host = "0.0.0.0"

    web_runner = await start_web_server(host=host, port=port)
    bot = ClubHubBot(config=config)

    try:
        async with bot:
            await bot.start(config.discord_token)
    finally:
        logging.info("Initiating graceful shutdown of web server and bot...")
        await stop_web_server(web_runner)


def main() -> None:
    """Run the ClubHub Discord bot with concurrent HTTP health server."""
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

    try:
        asyncio.run(run_bot_with_web_server(config))
    except discord.LoginFailure:
        logging.error("Invalid Discord Bot Token provided in DISCORD_TOKEN.")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        logging.critical(
            "\n"
            "================================================================================\n"
            "🚨 DISCORD PRIVILEGED GATEWAY INTENTS REQUIRED 🚨\n"
            "================================================================================\n"
            "Your bot needs Privileged Gateway Intents enabled in the Discord Developer Portal.\n\n"
            "HOW TO FIX (Takes 10 seconds):\n"
            "1. Open https://discord.com/developers/applications/\n"
            "2. Click on your application / bot.\n"
            "3. Select 'Bot' from the left sidebar.\n"
            "4. Scroll down to the 'Privileged Gateway Intents' section.\n"
            "5. Turn ON:\n"
            "   [✓] SERVER MEMBERS INTENT\n"
            "   [✓] MESSAGE CONTENT INTENT\n"
            "6. Click 'Save Changes' at the bottom of the page.\n"
            "7. Run 'python -m clubhub.main' again!\n"
            "================================================================================\n"
        )
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        logging.info("Interrupted by user. Exiting cleanly.")
    except Exception as e:
        logging.critical(f"Fatal error during bot execution: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
