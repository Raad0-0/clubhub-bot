# Optional Google Sheets Reporting Integration

ClubHub supports an optional Google Sheets audit register. When enabled, completed lifecycle events (submission, acceptance, outcome reason) are asynchronously appended to a central Google Sheet.

**Key Architecture Principle:**
Google Sheets is strictly an **optional audit destination**. If the Google Sheets API is rate-limited, unreachable, or disabled, **ticket management is completely unaffected**. All pending writes are stored in the local SQLite retry queue (`sheets_queue`) and synced automatically when connectivity returns.

---

## 1. Setting Up Google Cloud Service Account

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `ClubHub-Reporting`).
3. Enable the **Google Sheets API** under APIs & Services.
4. Navigate to **Credentials -> Create Credentials -> Service Account**.
5. Once created, click on the service account, go to the **Keys** tab, and select **Add Key -> Create new key -> JSON**.
6. Download the key file and save it as `credentials.json` in your bot's root directory.

---

## 2. Setting Up Your Spreadsheet

1. Create a new Google Spreadsheet in Google Drive.
2. Note the Spreadsheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit`
3. Click the **Share** button on your spreadsheet, and share it with the service account email (found in `credentials.json`, ending in `@...iam.gserviceaccount.com`) as an **Editor**.
4. Set up the header row in your target worksheet (e.g. `Ticket Register`):

| A | B | C | D | E | F | G | H | I | J | K | L |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| **Ticket ID** | **Requester Name** | **Requester ID** | **Category** | **Subject** | **Requested At** | **Handling Role** | **Accepted By** | **Accepted At** | **Status** | **Closed At** | **Outcome Reason** |

---

## 3. Configuring ClubHub

In `config.yaml`:
```yaml
sheets_reporting:
  enabled: true
  spreadsheet_id: "your_spreadsheet_id_here"
  support_worksheet: "Ticket Register"
  sensitive_worksheet: "Sensitive Register" # Can be a separate restricted tab
```

In `.env`:
```env
GOOGLE_SERVICE_ACCOUNT_FILE=credentials.json
```
