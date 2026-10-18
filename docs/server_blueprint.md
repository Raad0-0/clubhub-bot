# Reusable Discord Server Blueprint

ClubHub provides a structured, role-based layout designed to keep general discussion, official coordination, general support, and private concerns organized and secure.

---

## Blueprint Overview

```text
START HERE
├── #welcome             (Public read-only: Welcomes, community intro)
├── #rules               (Public read-only: Code of conduct & guidelines)
└── #server-guide        (Public read-only: Server orientation & FAQs)

COMMUNITY INFORMATION
├── #announcements       (Public read-only: Official club broadcasts)
├── #events              (Public read-only: Events & interactive RSVPs)
└── #event-questions     (Public chat or thread: Approved event Q&A)

COMMUNITY
├── #general             (Public chat: Main chat for club members)
├── #introductions       (Public chat: New member introductions)
├── #resources           (Public chat: Helpful links and guides)
├── #showcase            (Public chat: Member projects, photos, achievements)
├── #collaboration       (Public chat: Study groups, sub-teams, ideas)
└── Community Lounge     (Public voice channel: General social voice)

SUPPORT
└── #open-a-ticket       (Public read-only + UI: Persistent entry panel)

TICKET-XXXX (Temporary Private Category created dynamically by ClubHub)
├── #discussion          (Private text: Requester + Assigned Handling Role + Bot)
└── Support Voice        (Private voice: Requester + Assigned Handling Role + Bot)

ORGANIZERS (Restricted: Committee / Organizers only)
├── #organizer-discussion(Private text: Event and club planning)
├── #meeting-planning    (Private text: Q&A review queue & drafts)
└── Organizer Meeting    (Private voice: Planning meetings)

SUPPORT OPERATIONS (Restricted: Support Team only)
└── #support-review      (Private text: Incoming general assistance queue)

PRIVATE CONCERNS (Restricted: Welfare / HR Officers only)
└── #private-review      (Private text: Incoming confidential/welfare queue)

BOT OPERATIONS (Restricted: Administrators only)
└── #bot-log             (Private text: Bot activity, errors, audit alerts)
```

---

## Category & Permission Matrix

| Category / Channel | `@everyone` | Handling Team | Organizers | Administrators |
|:---|:---|:---|:---|:---|
| **START HERE** | View: Yes, Send: No | View: Yes, Send: No | View: Yes, Send: No | Full Access |
| **COMMUNITY** | View: Yes, Send: Yes | View: Yes, Send: Yes | View: Yes, Send: Yes | Full Access |
| **SUPPORT (#open-a-ticket)** | View: Yes, Send: No (Use Button) | View: Yes, Send: No | View: Yes, Send: No | Full Access |
| **ORGANIZERS** | View: No | View: No | View: Yes, Send: Yes | Full Access |
| **SUPPORT OPERATIONS** | View: No | View: Yes, Send: Yes | View: No | Full Access |
| **PRIVATE CONCERNS** | View: No | View: No (Welfare only) | View: No | Full Access |
| **BOT OPERATIONS** | View: No | View: No | View: No | Full Access |

---

## Privacy Notice Regarding Server Administrators
In Discord's permission architecture, any user with the `Administrator` permission natively bypasses channel permission overrides. While ClubHub cleanly isolates support and private concern channels from general staff and organizers, the server owner and designated administrators must be trusted custodians of community welfare.
