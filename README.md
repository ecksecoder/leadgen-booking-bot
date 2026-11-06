# LeadGen and Booking Telegram Bot (Commercial Micro-CRM)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/wal.html)
[![Google Sheets API](https://img.shields.io/badge/Google%20Sheets-API%20v4-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)](https://developers.google.com/sheets/api)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License MIT](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)](LICENSE)

[English] | [Документация на русском](README_RU.md)

---

## Architecture Overview

LeadGen and Booking Bot is an asynchronous Telegram service designed for structured lead intake, priority qualification, and commercial workflow tracking directly within Telegram, accompanied by in-place bidirectional synchronization with Google Sheets.

```
       TELEGRAM CLIENT
              |
              v
     [aiogram 3.x FSM Intake]
     (Sequential Collection: Service -> Name -> Phone -> Notes)
              |
              v
   [Context Triage Engine]
   Keyword-based Priority Tagging & Scoring:
   - URGENT_VIP     (Score: 100, Priority 1: Emergency routing, 15-min SLA notice)
   - PRICE_INQUIRY  (Score: 70,  Priority 2: Quote/estimate acknowledgment)
   - LOW_PRIORITY   (Score: 30,  Priority 3: Planned scheduling acknowledgment)
   - STANDARD       (Score: 10,  Priority 4: Standard business review)
              |
      +-------+-------------------------------+
      |                                       |
      v                                       v
[SQLite WAL Storage]            [Google Sheets Two-Way Sync]
- Thread-safe via to_thread()   - 9-column structured lead export
- WAL journal & NORMAL sync     - In-place row update by Lead ID (Column H)
- Self-healing schema migrations- Dynamic header & status sync tied to Admin locale
      |                                       |
      +-------+-------------------------------+
              |
              v
   [In-Telegram Manager Micro-CRM]
   - Manager notifications formatted in Administrator's active language
   - Dynamic tracking of Admin client Telegram locale (en, uk, ru)
   - One-click status transitions (CONFIRMED / IN_PROGRESS / REJECTED)
   - On-demand AI translation of raw client commentary directly in CRM cards
   - Push notifications to client formatted strictly in saved client_lang
```

---

## Feature Breakdown

### 1. Multi-Lingual Client Booking (en / uk / ru)
- Trilingual client user interface supporting English (en / GB), Ukrainian (uk / UA), and Russian (ru / RU).
- Strict onboarding gate: When a client executes `/start` for the first time without an initialized profile, the bot presents an interactive trilingual language selector before displaying catalog options.
- Dynamic auto-detection: Detects client Telegram language while allowing explicit manual override at any time via `/lang` or menu buttons.
- Latin-labeled auto button: Explicit indicator displaying `Auto (Telegram)`, `Автоматично (Telegram)`, or `Авто (Telegram)` with `(Telegram)` strictly in Latin characters.

### 2. Decoupled Manager CRM Alerts Rendered in Admin Telegram Language
- Independent locale engine: Client and manager language preferences operate completely decoupled.
- Dynamic Admin Language Tracking: Whenever an update from `ADMIN_ID` arrives (message or callback), the system inspects `event.from_user.language_code`. It maps `uk` to Ukrainian, `ru`/`be` to Russian, and all other codes to English.
- If the administrator changes their Telegram client language, in-memory and database states are updated immediately, and incoming CRM alert cards and status cards are formatted strictly in the administrator's active locale.

### 3. Dynamic Google Sheets Header and Status Synchronization Bound to Admin Locale
- Real-time Column A-I header synchronization: When the administrator's Telegram language changes, a background task (`sync_sheet_headers`) inspects Row 1 via `asyncio.to_thread`. If Row 1 headers differ from `get_sheet_headers(admin_lang)`, Row 1 is updated in-place without altering data rows.
- Localized headers across supported languages:
  - English: `Lead ID`, `Date`, `Name`, `Phone`, `Service`, `Notes (RAW)`, `Priority`, `Status`, `Username`
  - Ukrainian: `ID заявки`, `Дата`, `Ім'я`, `Телефон`, `Послуга`, `Деталі (RAW)`, `Пріоритет`, `Статус`, `Username`
  - Russian: `ID заявки`, `Дата`, `Имя`, `Телефон`, `Услуга`, `Детали (RAW)`, `Приоритет`, `Статус`, `Username`
- Synchronized status and priority values: Status values (`NEW`, `CONFIRMED`, `IN_PROGRESS`, `REJECTED`, `CANCELLED`) and priority tags (`URGENT_VIP`, `PRICE_INQUIRY`, `LOW_PRIORITY`, `STANDARD`) are localized into the administrator's current language upon append and update.

### 4. On-Demand AI Translation of Raw Client Notes Directly in Telegram CRM Cards
- Preserves raw input by default: Manager alert cards show original, unaltered client notes to prevent distortion.
- On-demand translation toggle: Includes an interactive inline button `Translate Notes` (`Перекласти деталі` / `Перевести детали`).
- When tapped, the system fetches the raw notes, calls the translation service into the administrator's current language, appends a translation block to the alert card, and swaps the button to `Hide Translation` (`Приховати переклад` / `Скрыть перевод`).
- Tapping `Hide Translation` removes the translation block and returns the button to `Translate Notes`.

### 5. Strict Raw Client Data Preservation Without Transliteration Corruption
- Client Name, Phone Number, and Project Notes are captured and stored strictly RAW.
- The system enforces zero destructive transliteration, character filtering, or automated pre-translation on client data.
- When an administrator changes lead status, the push notification sent to the client is formatted strictly in the client's saved `client_lang`.

### 6. Context Triage Engine and Priority Qualification
- Deterministic pattern and keyword matching scoring client task descriptions against configured business rules.
- Structured classification into four operational tiers:
  - `URGENT_VIP` (Priority 1, Score 100): Emergency requests, system breakdowns, critical deadlines. 15-minute SLA notice dispatched to client.
  - `PRICE_INQUIRY` (Priority 2, Score 70): Pricing calculations, commercial estimates, budget inquiries.
  - `LOW_PRIORITY` (Priority 3, Score 30): Exploratory inquiries, distant scheduling, non-urgent consultation requests.
  - `STANDARD` (Priority 4, Score 10): Baseline requests routed during regular business hours.
- Tailored auto-replies: Localized auto-reply messages are dispatched to the client in their chosen language.

### 7. In-Place Google Sheets Row Updates by Lead ID
- All network interactions and file I/O operations run inside worker threads via `asyncio.to_thread()`, preventing main event loop blocking.
- When an administrator modifies a lead status inside Telegram, the system searches Column A for the target `Lead ID` and writes the localized status directly to Column H (Column 8).
- Prevents row duplication and maintains spreadsheet integrity.

### 8. Anti-Duplicate and Self-Service Booking Management
- Active booking verification: Upon invoking `/start` or `Book a Consultation`, the bot verifies whether the client already has an active booking in `NEW`, `IN_PROGRESS`, or `CONFIRMED` status.
- Self-service actions: Active booking summaries display inline actions:
  - Cancel Booking: Marks the lead as `CANCELLED` in SQLite and updates Column H in Google Sheets in-place.
  - Reschedule / Update Info: Cancels the previous booking and re-enters the FSM booking flow.

---

## Decoupled Configuration (business_profile.json)

The bot decouples business rules from code. Modifying services, pricing, or scoring rules is done in `business_profile.json` without modifying source files.

```json
{
  "business_name": "TechPro Solutions",
  "currency": "USD",
  "support_contact": "@techpro_support",
  "services": [
    {
      "id": "business_automation",
      "name": "Business Process Automation",
      "price_hint": "From $500",
      "description": "End-to-end automation of operational workflows, CRM integration, and analytics pipelines."
    },
    {
      "id": "telegram_bot",
      "name": "Custom Telegram Bot Development",
      "price_hint": "From $350",
      "description": "High-load AI, LeadGen, and e-commerce bots with payment gateways and Google Sheets sync."
    }
  ],
  "context_triage": {
    "rules": [
      {
        "tag": "URGENT_VIP",
        "priority": 1,
        "keywords": ["urgent", "asap", "critical", "emergency", "sos", "deadline"],
        "admin_alert_prefix": "[URGENT_VIP]"
      },
      {
        "tag": "PRICE_INQUIRY",
        "priority": 2,
        "keywords": ["price", "cost", "how much", "quote", "rate", "budget"],
        "admin_alert_prefix": "[PRICE_INQUIRY]"
      },
      {
        "tag": "LOW_PRIORITY",
        "priority": 3,
        "keywords": ["later", "someday", "low priority", "just asking"],
        "admin_alert_prefix": "[LOW_PRIORITY]"
      }
    ],
    "default": {
      "tag": "STANDARD",
      "admin_alert_prefix": "[STANDARD]"
    }
  }
}
```

---

## Tech Stack

| Layer | Technology | Specification / Role |
| :--- | :--- | :--- |
| Runtime | Python 3.11+ | Standard CPython interpreter with asyncio event loop |
| Bot Framework | aiogram 3.17+ | Asynchronous Telegram Bot API wrapper with FSM |
| Database | SQLite 3 | WAL journal mode, NORMAL sync, busy timeout 5000ms |
| Spreadsheet Sync | gspread 6.2+ | Google Sheets API v4 via Service Account OAuth2 |
| Data Isolation | Custom Engine | Strict RAW storage for client data, decoupled admin locale |
| Containerization | Docker Engine | Multi-stage build running as non-root botuser (UID 10001) |
| Process Manager | Docker Compose v2 | Service orchestration, volume mapping, log-rotation |

---

## Deployment Guide

### Method A: Production Deployment via Docker Compose

1. Clone repository and navigate to project root:
```bash
git clone https://github.com/your-username/leadgen-booking-bot.git
cd leadgen-booking-bot
```

2. Configure environment file:
```bash
cp .env.example .env
```
Edit `.env` and set `BOT_TOKEN`, `ADMIN_ID`, and optional Google Sheets parameters.

3. Place Google Service Account credentials (if using Google Sheets):
Save your JSON keyfile as `credentials.json` in the project root. Ensure the spreadsheet is shared with the `client_email` address found inside the keyfile.

4. Build and start containers:
```bash
docker compose up -d --build
```

5. Monitor runtime logs:
```bash
docker compose logs -f
```

6. Stop service:
```bash
docker compose down
```

### Method B: Bare-Metal Setup

1. Initialize and activate Python virtual environment:
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install runtime dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment parameters in `.env`:
```ini
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_01234567
ADMIN_ID=123456789
DB_PATH=leads.db
LOG_LEVEL=INFO
GOOGLE_CREDS_PATH=credentials.json
GOOGLE_SHEET_ID=your_spreadsheet_id_here
```

4. Launch application:
```bash
python bot.py
```

---

## Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `BOT_TOKEN` | Yes | None | Telegram Bot API token obtained from @BotFather |
| `ADMIN_ID` | Yes | None | Numeric Telegram ID of manager receiving CRM alerts |
| `DB_PATH` | No | `leads.db` | Filesystem path to SQLite database |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `GOOGLE_CREDS_PATH` | No | `credentials.json` | Path to Google Service Account JSON keyfile |
| `GOOGLE_SHEET_ID` | No | None | Unique ID extracted from Google Sheet URL |

---

## Testing and Verification

Verify static syntax and bytecode compilation across all application modules:

```bash
python -m py_compile bot.py context_triage.py database.py sheets_sync.py locales.py
```

Execute runtime verification of triage scoring, database initialization, and localization lookups:

```bash
python -c "from locales import get_sheet_headers, get_text; from context_triage import analyze_lead_context; print('Headers:', get_sheet_headers('en')); print('Triage:', analyze_lead_context('Urgent project', lang='en'))"
```

---

## License

This project is distributed under the [MIT License](LICENSE). Suitable for commercial use, client white-label deployments, and custom extensions.
