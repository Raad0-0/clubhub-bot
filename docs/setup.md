# ClubHub Setup Guide

This guide walks you through setting up ClubHub from scratch on your Discord server.

---

## 1. Discord Developer Portal Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and enter a name (e.g. `ClubHub`).
3. Navigate to the **Bot** tab on the left menu:
   - Click **Add Bot**.
   - Under **Privileged Gateway Intents**, enable:
     - **Server Members Intent** (Required for welcome greetings and member permission checks)
     - **Message Content Intent** (Required for reading ticket messages and inactivity detection)
   - Click **Reset Token**, copy your bot token, and store it safely in your `.env` file as `DISCORD_TOKEN`.
4. Navigate to **OAuth2 -> URL Generator**:
   - Scopes: Select `bot` and `applications.commands`.
   - Bot Permissions:
     - Manage Channels
     - Manage Roles
     - View Channels
     - Send Messages
     - Embed Links
     - Attach Files
     - Read Message History
     - Mention Everyone
     - Use External Emojis
     - Connect & Speak (for ticket voice channels)
5. Copy the generated invite link and open it in your browser to invite the bot to your server.

---

## 2. Server Structure Setup

You can either adopt the [Server Blueprint](server_blueprint.md) or map ClubHub to existing channels on your server.

Ensure the bot's highest role is positioned **above** any roles it needs to assign or manage (such as temporary ticket roles or support roles) in `Server Settings -> Roles`.

---

## 3. Configuration

1. Copy `config.example.yaml` to `config.yaml`:
   ```bash
   cp config.example.yaml config.yaml
   ```
2. Open `config.yaml` and configure:
   - **Community Identity**: Name, prefix, color scheme.
   - **Roles**: Replace the role names or IDs with your server's roles (e.g., `Support Team`, `Welfare`, `Committee`).
   - **Channels**: Match channel names or IDs (`open-a-ticket`, `support-review`, `private-review`, etc.).
   - **Ticket Categories**: Define each category, its handling roles, and whether it is marked `is_sensitive: true`.
   - **Inactivity Timeout**: Default is 120 minutes (2 hours) with a 15-minute warning.

---

## 4. Running the Bot

1. Ensure dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the bot:
   ```bash
   python -m clubhub.main
   ```
3. In your configured `#open-a-ticket` channel, run the admin command to post the permanent entry panel:
   ```text
   !post_panel
   ```
   or via the slash command `/clubhub post_panel`.
