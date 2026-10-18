# ClubHub — Discord Club Server & Management Bot
## Public Project Proposal

ClubHub is a proposed open-source Discord bot and server blueprint for clubs, societies, student organizations, and community groups. It combines member support, private concern handling, event coordination, and automated ticket cleanup in one configurable project.

*ClubHub is a working project name and can be replaced before publication.*

---

## 1. Project Vision
Provide a reusable foundation that any club can configure without rewriting the bot for its own role names, channels, or organizational structure.

The central design principle is **configurability**: each community defines its support teams, request categories, event organizers, and record destinations.

*This proposal describes the intended functionality. It is not a claim that the features have already been implemented.*

---

## 2. Project Objectives
ClubHub aims to:
- Give members a clear way to request assistance.
- Route requests to the appropriate team before creating private channels.
- Keep support and sensitive concerns separate.
- Automatically remove inactive ticket spaces.
- Record request ownership, staff acceptance, and outcomes.
- Help organizers manage meetings, events, RSVP, and questions.
- Offer a suggested server structure that communities can adopt or adapt.
- Preserve operational state across bot restarts.

---

## 3. Intended Communities
The project is designed for:
- University and school clubs.
- Technical and project communities.
- Hobby and interest groups.
- Volunteer organizations.
- Societies and associations.
- Other role-based Discord communities.

No academic subject, institution, or club-specific workflow will be required.

---

# Part A — Reusable Discord Server Blueprint

## 4. Suggested Server Structure
The blueprint is optional. Communities may connect the bot to existing channels instead of adopting the full layout.

```text
START HERE
├── #welcome
├── #rules
└── #server-guide

COMMUNITY INFORMATION
├── #announcements
├── #events
└── #event-questions

COMMUNITY
├── #general
├── #introductions
├── #resources
├── #showcase
├── #collaboration
└── Community Lounge (Voice Channel)

SUPPORT
└── #open-a-ticket

TICKET-0042 ← Temporary private category
├── #discussion
└── Support Voice (Voice Channel)

TICKET-0043 ← Temporary private category
├── #discussion
└── Support Voice (Voice Channel)

ORGANIZERS ← Restricted
├── #organizer-discussion
├── #meeting-planning
└── Organizer Meeting (Voice Channel)

SUPPORT OPERATIONS ← Restricted
└── #support-review

PRIVATE CONCERNS ← Separately restricted
└── #private-review

BOT OPERATIONS ← Administrators
└── #bot-log
```

Temporary ticket categories will be positioned near the permanent support section. Each accepted ticket receives its own category, text channel, and voice channel.

---

## 5. Configurable Permission Groups
These are functional groups, not mandatory Discord role names.

| Group | Responsibilities |
| :--- | :--- |
| **Administrators** | Configure the bot, role mappings, channels, and integrations |
| **Organizers** | Manage official meetings, events, announcements, and event reminders |
| **Support team** | Review and handle general assistance requests |
| **Private-concern team** | Handle complaints and sensitive requests |
| **Members** | Participate in the community and use member-facing bot features |

A community may map these groups to roles such as Committee, Moderators, Support, HR, Welfare, or Leadership. Permission to manage events will not automatically grant access to private tickets.

---

## 6. Suggested Community Policies
The repository includes editable guideline templates covering:
- Respectful communication.
- Harassment, spam, and misuse.
- Appropriate channel usage.
- Protection of personal information.
- Confidential handling of private requests.
- Responsible use of mentions and voice channels.
- Escalation of sensitive concerns.

Communities remain responsible for approving and enforcing their own policies.

---

# Part B — Bot Functional Specification

## 7. Feature Overview

| Module | Planned Functionality |
| :--- | :--- |
| **Welcome** | Greet new members and link important channels |
| **Tickets** | Submit, review, accept, resolve, and close requests |
| **Automatic cleanup** | Remove inactive ticket spaces |
| **Ticket register** | Optional Google Sheets records |
| **Meetings and events** | Organizer-controlled scheduling and announcements |
| **RSVP** | Member participation responses |
| **Event Q&A** | Question submission and organizer review |
| **Reminders** | Personal and event notifications |

---

## 8. Configurable Ticket Categories
Communities will define request categories and map each to a handling role and review channel.

Example configuration:
| Request Category | Handling Team | Review Destination |
| :--- | :--- | :--- |
| General Assistance | Support | Support review queue |
| Membership Question | Support | Support review queue |
| Activity or Project Help | Support | Support review queue |
| Complaint / Private Concern | Welfare or HR | Restricted private review queue |

Category names and routing will not be hardcoded.

---

## 9. Ticket Submission and Approval

### 9.1 Permanent Entry Panel
A configured channel will contain a persistent panel:
```text
COMMUNITY SUPPORT
Need assistance or want to raise a concern?
Submit a request for the appropriate team to review.
[Create Ticket]
```
Panel text and branding will be customizable.

### 9.2 Request Form
Members provide:
- Request category.
- Subject.
- Description.

Every accepted ticket receives both text and voice channels. There is no support-mode selection in the initial design.

### 9.3 One Request Per Member
Each member may have only one pending or active ticket per server.

| Existing Status | Another Request Allowed? |
| :--- | :--- |
| **Pending review** | No |
| **Open** | No |
| **Closing** | No |
| **Closed** | Yes |
| **Declined** | Yes |

The restriction applies across request categories and survives bot restarts.

### 9.4 Review Workflow
```text
Member submits request
       ↓
Bot checks for an existing request
       ↓
Request enters the configured review queue
       ↓
Authorized team member accepts or declines
       ↓
If accepted: create the private ticket space
```

Review controls: `[Accept]` `[Decline]`

Requirements:
- Only the assigned handling role may review the request.
- Acceptance records the individual handler.
- Declining requires a reason.
- The requester receives an outcome notification.
- Concurrent acceptance attempts produce only one ticket space.
- Pending requests are not subject to the active-ticket inactivity timer.

---

## 10. Accepted Ticket Structure
Each accepted ticket creates:
```text
TICKET-0042
├── #discussion
└── Support Voice
```

Intended access:
- The requester.
- The configured handling role.
- The bot.

The accepting staff member is recorded as the handler, while the handling role retains access for team assistance.

The ticket text channel includes a control message:
```text
TICKET #0042
Requester: @Member
Category: General Assistance
Accepted by: @TeamMember
Status: Open

Subject: ...
Description: ...

[Close Ticket]
```
The requester and authorized handling team may close the ticket with confirmation. Private category names use neutral identifiers rather than sensitive subjects.

---

## 11. Automatic Cleanup

### 11.1 Default Rule
The default inactivity period is two hours (configurable).
A ticket stays open when:
> **A human has posted in its text channel within the inactivity period OR at least one human is connected to its voice channel.**

Otherwise, it closes when the inactivity deadline is reached.

```text
Recent human text activity OR human present in VC
                    ↓
                KEEP OPEN

No recent human text activity AND empty VC
                    ↓
        CLOSE after inactivity timeout
```

### 11.2 Activity Handling
| Event | Effect |
| :--- | :--- |
| Human sends a text message | Reset the inactivity deadline |
| Human remains in ticket VC | Suspend automatic closure |
| Last human leaves ticket VC | Start a fresh inactivity window |
| Authorized participant selects Keep Open | Reset the deadline |
| Bot posts a message | Do not reset the deadline |
| Activity occurs outside the ticket | No effect |

The timer begins when the accepted ticket space is ready. A person remaining connected while AFK will keep the ticket open under this policy.

### 11.3 Warning
By default, the bot warns participants 15 minutes before closure:
```text
This ticket will close soon due to inactivity.
Send a message, join the ticket voice channel, or select Keep Open if assistance is still needed.
[Keep Open] [Close Ticket]
```
The bot rechecks activity immediately before automatic deletion.

### 11.4 Cleanup Sequence
Closure will:
1. Mark the ticket as closing.
2. Save the outcome and closure reason.
3. Delete the linked text channel.
4. Delete the linked voice channel.
5. Delete the ticket category.
6. Mark closure as complete.
7. Allow the requester to submit another request.

Resources will be identified by stored IDs, not broad name matching. Partial failures remain recoverable and generate an administrative notice.

---

## 12. Ticket Register
Google Sheets is an optional reporting integration. Ticket operation does not require it to be enabled.

Proposed Fields:
- Ticket ID
- Requester name and ID
- Category
- Subject and description
- Requested at
- Handling role
- Accepted by and handler ID
- Accepted at
- Status
- Closed or declined at
- Closed by
- Outcome reason

Sensitive request categories support separate, restricted register destinations. The initial scope excludes conversation transcripts and voice recordings. Failed register updates are queued for retry without interrupting active tickets.

---

## 13. Meetings and Events
Only configured organizer roles may create or manage official activities.

**Organizer Features:**
- Create drafts.
- Set title, description, time, and location.
- Choose a public or restricted audience.
- Preview and publish.
- Edit or cancel.
- Schedule reminders.
- Review questions.
- View RSVP summaries.

**Member Features:**
Buttons: `[Going]` `[Maybe]` `[Can't Attend]` `[Ask a Question]`
- Members may change their RSVP.
- Questions enter an organizer review queue before public publication.
- RSVP represents intended participation; verified attendance is outside the initial scope.

---

## 14. Welcome and Reminders
### Welcome
Configurable welcome messages direct members to:
- Community rules.
- Server guidance.
- Announcements and events.
- The support panel.

### Reminders
The bot supports:
- Personal reminders created by members.
- Activity reminders created by organizers.
Timezone, delivery channel, and mention behavior are configurable.

---

# Part C — Technical and Open-Source Design

## 15. Technical Architecture
| Component | Proposed Approach |
| :--- | :--- |
| Language | Python |
| Discord library | discord.py |
| Interface | Buttons, forms, and restricted commands |
| Operational storage | SQLite |
| Optional reporting | Google Sheets |
| Development runtime | Local computer |
| Production runtime | Self-hosted or hosted environment |

```text
Discord
   ↕
Python Bot
├── Operational Database
│   ├── Configuration
│   ├── Requests and assignments
│   ├── Category/channel IDs
│   ├── Inactivity deadlines
│   ├── Events and reminders
│   └── Pending integration updates
└── Optional Google Sheets Integration
    └── Ticket register
```

The initial deployment target is one community server per bot instance. Configuration and records include server identifiers so future multi-server support can be developed without mixing community data.

---

## 16. Configuration Requirements
Community-specific values must be configurable rather than embedded in source code.
- Identity: Community name, panel wording, message branding
- Roles: Administrators, organizers, handling teams
- Channels: Welcome, events, review queues, logs, support panel
- Ticket routing: Categories, handling roles, review destinations
- Ticket placement: Where temporary categories should appear
- Cleanup: Inactivity duration and warning lead time
- Reporting: Enable/disable Sheets and choose register destinations
- Events: Timezone and reminder defaults
- Privacy: Which request details may appear in reports

Credentials will be separated from non-secret community configuration.

---

## 17. Reliability and Privacy Requirements
The implementation must:
- Validate configuration at startup.
- Check authorization for restricted actions.
- Prevent duplicate requests and acceptance.
- Restore open tickets and controls after restart.
- Recover incomplete cleanup operations.
- Handle missing channels, roles, or permissions gracefully.
- Avoid placing sensitive request content in general logs.
- Preserve failed reporting updates for retry.
- Keep separate communities' records isolated.
- Recheck activity before deletion.
- After downtime, overdue tickets receive a warning/grace period instead of being deleted immediately.
- The documentation explains intended ticket access without promising confidentiality from server administrators.

---

## 18. Public Repository Deliverables
The repository includes:
- `README.md`: Project purpose, status, features, and quick start
- `PROPOSAL.md`: This project specification
- `LICENSE`: Approved open-source license (MIT)
- `CONTRIBUTING.md`: Contribution and development workflow
- `CODE_OF_CONDUCT.md`: Contributor interaction expectations
- `SECURITY.md`: Private vulnerability-reporting instructions
- `.env.example`: Credential placeholders only
- `config.example.yaml`: Sample roles, routing, and channel settings
- Source directory: Bot implementation
- Tests: Workflow, permission, and recovery tests
- Documentation: Setup, server blueprint, integrations, and deployment

---

## 19. Documentation for Reuse
A new community will be able to follow documentation covering:
1. Creating and inviting its bot.
2. Configuring roles and permissions.
3. Connecting existing channels or adopting the server blueprint.
4. Defining request categories and handling teams.
5. Enabling Google Sheets, if desired.
6. Running locally.
7. Testing acceptance, privacy, and cleanup.
8. Deploying to its chosen host.
9. Backing up and recovering operational data.
10. Updating the bot safely.

---

## 20. Development Roadmap
| Phase | Deliverables |
| :--- | :--- |
| **Phase 1 — Foundation** | Repository structure, configuration, database, bot connection |
| **Phase 2 — Requests** | Panel, forms, routing, one-ticket restriction, review queues |
| **Phase 3 — Ticket spaces** | Acceptance, private category/text/VC creation, notifications |
| **Phase 4 — Cleanup** | Manual closure, OR-based activity policy, warnings, safe deletion |
| **Phase 5 — Recovery and reporting** | Restart recovery, optional Sheets integration, retries |
| **Phase 6 — Community features** | Welcome, events, RSVP, Q&A, reminders |
| **Phase 7 — Public release** | Tests, setup guides, example configuration, security review |

---

## 21. Acceptance Criteria
The release is ready when:
- Community-specific roles and channels can be changed without editing bot logic.
- Requests create no ticket channels before acceptance.
- Each member is limited to one pending/open request per server.
- Requests reach only their configured review teams.
- Unauthorized acceptance and closure are rejected.
- Acceptance creates exactly one category, text channel, and VC.
- The requester and handling team receive intended access.
- Recent text activity OR VC occupancy prevents automatic closure.
- Inactive tickets are warned and completely removed.
- Closing one ticket does not affect another.
- Restarts preserve restrictions, assignments, and controls.
- Disabling Sheets does not disable ticket management.
- Reporting failures do not interrupt support.
- A second community can configure the project without inheriting the original community's names or private data.

---

## 22. Initial Scope Exclusions
The initial release will **not** include:
- AI chat.
- Music playback.
- XP or leveling.
- A full moderation suite.
- Attendance verification.
- Conversation transcripts.
- Voice recording.
- A web administration dashboard.
- A centrally operated public multi-server bot service.

---

## 23. Project Status and Release Decisions
This document serves as the canonical specification for the ClubHub open-source project.
