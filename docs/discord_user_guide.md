# 📖 ClubHub Discord Setup & User Guide

Welcome to the complete, step-by-step Discord setup and usage guide for **ClubHub**. This guide covers everything needed to invite the bot, configure roles and channels, deploy interactive panels, and manage daily operations.

---

## 📑 Table of Contents
1. [Prerequisites & Discord Developer Portal Setup](#1-prerequisites--discord-developer-portal-setup)
2. [Discord Server Setup (Roles & Hierarchy)](#2-discord-server-setup-roles--hierarchy)
3. [Discord Channel Setup](#3-discord-channel-setup)
4. [First-Time Bot Activation (1-Minute Setup)](#4-first-time-bot-activation-1-minute-setup)
5. [Member Experience Guide](#5-member-experience-guide)
6. [Staff & Support Workflow Guide](#6-staff--support-workflow-guide)
7. [Event Organizers Workflow Guide](#7-event-organizers-workflow-guide)
8. [Command Cheat Sheet & Troubleshooting](#8-command-cheat-sheet--troubleshooting)

---

## 1. Prerequisites & Discord Developer Portal Setup

Before inviting the bot to your Discord server, configure its intents and permissions in the [Discord Developer Portal](https://discord.com/developers/applications):

### Step 1.1: Enable Privileged Gateway Intents (CRITICAL)
1. In the Developer Portal, click your application -> navigate to the **Bot** tab on the left menu.
2. Scroll down to **Privileged Gateway Intents**.
3. **Turn ON** both:
   - ✅ **Server Members Intent** (Needed for greeting new members and verifying roles)
   - ✅ **Message Content Intent** (Needed for ticket activity detection and prefix commands `!`)
4. Click **Save Changes**.

> [!CAUTION]
> If **Message Content Intent** or **Server Members Intent** is not enabled, the bot will fail to read `!` commands and cannot detect member joins.

### Step 1.2: Generate the Bot Invite Link
1. In the Developer Portal, go to **OAuth2 -> URL Generator**.
2. Under **Scopes**, select:
   - `bot`
   - `applications.commands`
3. Under **Bot Permissions**, select:
   - `Manage Channels`
   - `Manage Roles`
   - `View Channels`
   - `Send Messages`
   - `Embed Links`
   - `Attach Files`
   - `Read Message History`
   - `Mention Everyone`
   - `Use External Emojis`
   - `Connect` & `Speak` (for private ticket voice channels)
4. Copy the generated URL at the bottom and open it in your browser to invite the bot to your Discord server.

---

## 2. Discord Server Setup (Roles & Hierarchy)

In Discord, go to **Server Settings -> Roles**. Create the following roles (or match existing ones to `config.yaml`):

### Required Roles
| Role Name | Purpose | Assigned To |
|:---|:---|:---|
| **Admin** | Full system control, bot administration, ticket override | Server Owners & Head Admins |
| **Event Management** *(or `Committee`)* | Creating and publishing club events | Event Leads & Coordinators |
| **Support** | Reviewing and handling academic, project, and general questions | Tutors, Mentors, Support Staff |
| **HR** *(or `Welfare Officer`)* | Reviewing confidential concerns & complaints | Trusted Welfare / HR Officers |
| **Member** | General club membership | All regular server members |

### ⚠️ Role Hierarchy Rule (Crucial)
1. In **Server Settings -> Roles**, look at your role list.
2. Drag the **ClubHub bot role** so it is **above** `Event Management`, `Support`, `HR`, and `Member`.
3. Discord enforces strict role hierarchy: a bot cannot create channels or manage permissions for roles placed higher than itself!

---

## 3. Discord Channel Setup

Create the following channels in your server (matching the default `config.yaml`):

```text
📋 START HERE
├── #welcome             (Public: Bot posts new member greetings here)
├── #rules               (Public read-only: Server rules & guidelines)
└── #server-guide        (Public read-only: Club FAQs and orientation)

📢 ANNOUNCEMENTS & EVENTS
├── #announcements       (Public read-only: Broadcasts)
└── #events              (Public read-only: Official event cards with RSVP & Q&A)

💬 COMMUNITY
├── #general             (Public chat)
└── #introductions       (Public chat)

🎫 SUPPORT DESK
└── #open-a-ticket       (Public read-only: Interactive 4-button ticket panel)

🔒 STAFF REVIEW (Restricted)
├── #support-review      (PRIVATE: Visible only to @Admin and @Support)
├── #private-review      (PRIVATE: Visible only to @Admin and @HR)
├── #create-event        (PRIVATE: Visible only to @Admin and @Event Management)
└── #bot-log             (PRIVATE: Visible only to @Admin)
```

> [!TIP]
> You don't have to manually create `#create-event` with permissions! Running `!setup_event_channel` will create and lock it automatically.

---

## 4. First-Time Bot Activation (1-Minute Setup)

Once the bot is running and online in your server, run the following setup commands as an **Administrator**:

### Step 4.1: Sync Slash Commands
In any channel, type:
```text
!clubhub sync
```
*Discord will register all `/event` and `/test_welcome` slash commands.*

### Step 4.2: Setup Event Management Channel
Run:
```text
!setup_event_channel
```
*Creates `#create-event` (if it doesn't exist) and locks it so only `Admin` and `Event Management` roles can access it.*

### Step 4.3: Deploy Event Management Panel
Inside `#create-event`, type:
```text
!post_event_panel
```
*Posts the persistent **Event Management Panel** with the `[➕ Create New Event]` button.*

### Step 4.4: Deploy the Support Ticket Panel
Go to your public `#open-a-ticket` channel and type:
```text
!post_panel
```
*Posts the interactive support panel with 4 colored category buttons:*
- 📖 **Study Help** (Blue)
- 📋 **Membership Question** (Grey)
- 🛠️ **Project Help** (Green)
- 🔒 **Complaint / Private Concern** (Red)

### Step 4.5: Verify Welcome Greetings
In `#welcome`, type:
```text
!test_welcome
```
*Simulates a welcome greeting to verify links to `#rules`, `#server-guide`, and `#open-a-ticket` are functioning.*

---

## 5. Member Experience Guide

### How Members Open a Ticket
1. Go to `#open-a-ticket`.
2. Click any of the 4 category buttons (e.g. `📖 Study Help` or `🔒 Complaint / Private Concern`).
3. A popup modal appears:
   - **Subject / Topic**: Brief title of what you need.
   - **Description**: Detailed explanation of your question or issue.
4. Click **Submit**.
5. The bot responds privately: `"Your request has been submitted for review. Staff will accept your ticket shortly."`

### Inside an Accepted Ticket
Once staff accept the ticket:
- A dedicated category `TICKET-0001` appears on the left sidebar.
- Inside it:
  - `#discussion` (Private text channel between requester and staff).
  - `Support Voice` (Private voice channel for 1-on-1 audio screen-sharing).
- Only the requester, assigned handling role, and admins can view or join.
- When finished, either member or staff can click **`[🔒 Close Ticket]`**.

### How Members Interact with Events
In `#events`:
- **RSVP Buttons**: Members can click:
  - `✅ Attending`
  - `❓ Maybe`
  - `❌ Cannot Attend`
- **Q&A**: Members can click `❓ Ask a Question` to submit a query to event organizers.

### Personal Reminders
Members can set automatic Discord DM reminders:
```text
!remindme 30m Check event workshop links
!remindme 2h Join study group voice call
```

---

## 6. Staff & Support Workflow Guide

### How General Support Tickets Work
1. When a member clicks **Study Help**, **Membership Question**, or **Project Help**, a review card is sent to **`#support-review`**.
2. Support staff see:
   - Requester name & avatar.
   - Category tag.
   - Submitted topic and description.
   - Two buttons: `[✅ Accept Request]` and `[❌ Decline Request]`.
3. When a staff member clicks **`✅ Accept Request`**:
   - The bot creates the temporary `TICKET-XXXX` category with `#discussion` and `Support Voice`.
   - The requester and the `@Support` role are granted access.
   - The review card in `#support-review` updates to show who accepted it and when.
4. When finished, click **`[🔒 Close Ticket]`** in `#discussion` to archive and delete the room.

### How Confidential / HR Tickets Work
- When a member clicks **`🔒 Complaint / Private Concern`**:
  - The review card is routed exclusively to **`#private-review`**.
  - General `@Support` staff **cannot see** this ticket! Only `@HR` / Welfare officers and Administrators have access.
  - Keeps sensitive personal, academic, or conduct complaints completely confidential.

### Automatic Inactivity Protection
- Tickets that remain silent (no text messages and no members in the voice room) for **2 hours** receive an automated **15-minute warning**.
- If still inactive after the warning, the bot automatically closes the ticket and cleans up the channels to keep the server clean.

---

## 7. Event Organizers Workflow Guide

### Creating a New Event
1. Go to the restricted **`#create-event`** channel.
2. Click **`[➕ Create New Event]`** on the panel (or type `!event_create`).
3. Fill out the event modal:
   - **Event Title**: e.g., `Spring Hackathon Kickoff`
   - **Date**: Format `YYYY-MM-DD` (e.g. `2026-11-15`)
   - **Time & Timezone**: Format `HH:MM TZ` (e.g. `18:00 UTC` or `19:30 EST`)
   - **Location / Platform**: e.g. `Room 302 / Discord Stage`
   - **Description**: Details, agenda, what to bring.
4. Click **Submit**.

### Publishing the Event
1. The bot generates an **Event Draft Preview** in `#create-event` with controls:
   - `[📢 Publish Event]`
   - `[✏️ Edit]`
   - `[❌ Cancel]`
2. Review the preview. When ready, click **`[📢 Publish Event]`** (or type `!event_publish <event_id>`).
3. The official, interactive event embed is published to **`#events`** with dynamic countdown timestamps (`<t:...:R>`) and live RSVP counters!

### Tracking RSVPs
To view current attendance numbers:
```text
!event_summary 1
```
*(Shows how many members clicked Attending, Maybe, and Declined).*

### Concluding vs Deleting an Event
- **When an event is over**:
  ```text
  !event_conclude 1
  ```
  *Updates the status in `#events` to "Concluded", disables further RSVPs, but preserves the event history.*
- **If an event was canceled or created in error**:
  ```text
  !event_delete 1
  ```
  *Completely removes the event from the database and removes the announcement.*

---

## 8. Command Cheat Sheet & Troubleshooting

### Command Reference

| Command | Allowed Roles | Description |
|:---|:---|:---|
| `!post_panel` | Admin | Deploys 4-button ticket panel to current or specified channel |
| `!setup_event_channel` | Admin | Automatically creates & locks the `#create-event` channel |
| `!post_event_panel` | Admin, Event Management | Deploys the Event Management panel in `#create-event` |
| `!clubhub sync` | Admin | Synchronizes slash commands with Discord |
| `!clubhub status` | Admin | Displays bot latency, active tickets, and database status |
| `!test_welcome` | Admin | Tests the automated new member greeting in `#welcome` |
| `!event_create` | Event Management, Admin | Opens the Event Creation form |
| `!event_publish <id>` | Event Management, Admin | Publishes an event draft to `#events` |
| `!event_summary <id>` | Event Management, Admin | Displays RSVP summary for an event |
| `!event_list` | Event Management, Admin | Lists all scheduled upcoming events |
| `!event_conclude <id>` | Event Management, Admin | Marks an event as finished |
| `!event_delete <id>` | Event Management, Admin | Completely deletes an event |
| `!remindme <time> <msg>` | Everyone | Sets a private DM reminder (e.g. `!remindme 45m Submit lab`) |

---

### Troubleshooting Common Issues

#### 1. Bot doesn't respond to `!` commands
- **Cause**: **Message Content Intent** is turned off in Discord Developer Portal.
- **Fix**: Go to [Discord Developer Portal](https://discord.com/developers/applications) -> Bot -> Privileged Gateway Intents -> Enable **Message Content Intent** -> Restart the bot.

#### 2. Welcome message doesn't trigger when a new user joins
- **Cause**: **Server Members Intent** is disabled.
- **Fix**: Go to Developer Portal -> Bot -> Privileged Gateway Intents -> Enable **Server Members Intent**.

#### 3. "Missing Permissions" error when accepting a ticket
- **Cause**: The bot's role is lower than the roles it is trying to manage.
- **Fix**: In **Server Settings -> Roles**, drag the bot's role to the top of the list. Also ensure the bot has `Manage Channels` permission.

#### 4. The bot can't find channels (`#open-a-ticket`, `#events`, etc.)
- **Cause**: Channel names on Discord don't match `config.yaml`.
- **Fix**: Either rename the Discord channels to match `config.yaml` or update `config.yaml` with your server's exact channel names or numeric IDs.
