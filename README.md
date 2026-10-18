# ClubHub 🏛️
### Discord Club Server & Management Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-blue.svg)](https://github.com/Rapptz/discord.py)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**ClubHub** is an open-source, production-ready Discord bot and server management blueprint tailored for student clubs, societies, volunteer organizations, technical interest groups, and role-based communities.

It provides a unified foundation for **triage-first ticket handling**, **private & sensitive concern routing**, **automated voice & text ticket cleanup**, **event coordination with interactive RSVP & Q&A moderation**, and **personal/community reminders**—without hardcoding a single channel, role name, or community identity.

---

## 🌟 Key Features

* **Configurable Triage-First Support**:
  * Persistent entry panel with interactive Modals.
  * Requests are held in a restricted review queue (`#support-review`) for staff acceptance before any channels are created.
* **Segregated Sensitive Concerns**:
  * Separate routing for confidential welfare/HR complaints directly to designated officers (`#private-review`).
  * Automatic neutral category/channel identifiers (e.g. `TICKET-0042`) protect member confidentiality.
* **Strict One-Request-Per-Member Policy**:
  * Prevents duplicate requests across all categories; survives bot restarts via persistent SQLite state.
* **Atomic Staff Acceptance**:
  * Prevents concurrent race conditions when multiple staff members review incoming tickets.
  * Automatically provisions a private category, text discussion channel, and temporary voice channel for the requester and handling team.
* **Intelligent Auto-Cleanup (OR-Based Policy)**:
  * Keeps ticket spaces open as long as a human has sent a text message within the inactivity window **OR** at least one person remains in the ticket voice channel.
  * 15-minute advance warning broadcast with interactive `[Keep Open]` extension button.
  * Clean, automated teardown of text, voice, and category resources upon closure.
* **Resilient Across Downtime & Restarts**:
  * Recovers active ticket controls upon restart.
  * Overdue tickets receive a gentle grace period rather than sudden deletion.
* **Meetings, Events, RSVP & Moderated Q&A**:
  * Committee drafts, schedules, and broadcasts events.
  * Members respond with `[Going]`, `[Maybe]`, `[Can't Attend]` and submit questions through an organizer moderation queue.
* **Personal & Activity Reminders**:
  * Custom time-based reminders delivered to members or designated channels.
* **Optional Google Sheets Audit Register**:
  * Seamless reporting to Google Sheets with an offline local SQLite retry queue so API interruptions never affect ticket support.

---

## 🏗️ Suggested Server Blueprint

ClubHub includes a battle-tested server structure that communities can adopt or map into existing channels:

```text
START HERE
├── #welcome             (Member greeting & resource index)
├── #rules               (Community guidelines & conduct)
└── #server-guide        (Server orientation)

COMMUNITY INFORMATION
├── #announcements       (Official broadcasts)
├── #events              (Upcoming meetings & events with RSVP)
└── #event-questions     (Approved Q&A discussion)

COMMUNITY
├── #general, #introductions, #resources, #showcase, #collaboration
└── Community Lounge (Voice)

SUPPORT
└── #open-a-ticket       (Persistent interactive support panel)

TICKET-XXXX (Temporary Private Spaces generated on acceptance)
├── #discussion          (Text channel for requester & handlers)
└── Support Voice        (Dedicated voice channel)

OPERATIONS & RESTRICTED
├── #organizer-discussion, #meeting-planning, Organizer Meeting (VC)
├── #support-review      (Restricted to Support Team)
├── #private-review      (Restricted to Welfare/HR)
└── #bot-log             (Restricted to Administrators)
```

See [docs/server_blueprint.md](docs/server_blueprint.md) for detailed role permissions.

---

## 🚀 Quick Start

### 1. Requirements
* Python 3.10+
* Discord Bot Token (with `Server Members` and `Message Content` intents enabled)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-org/clubhub.git
cd clubhub

# Create virtual environment
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
```bash
cp .env.example .env
cp config.example.yaml config.yaml
```
1. Add your `DISCORD_TOKEN` in `.env`.
2. Configure roles, channels, and categories in `config.yaml`.

### 4. Running the Bot
```bash
python -m clubhub.main
```
In your server's support channel (e.g., `#open-a-ticket`), deploy the interactive entry panel:
```text
!post_panel
```

---

## 🧪 Testing

ClubHub comes with an automated unit and integration test suite:
```bash
pytest
```

---

## 📚 Documentation

* [Setup & Discord Developer Guide](docs/setup.md)
* [Server Structure & Permissions Blueprint](docs/server_blueprint.md)
* [Production Deployment (systemd & Docker)](docs/deployment.md)
* [Google Sheets Integration Guide](docs/sheets_integration.md)
* [Full Public Project Proposal (PROPOSAL.md)](PROPOSAL.md)

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
