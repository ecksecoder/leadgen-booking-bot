# Architecture & Implementation Report: Context Triage Engine, Anti-Duplicate Self-Service & Two-Way Sync

## Executive Summary
This update introduces a production-ready **Context Triage Engine**, **Anti-Duplicate & Self-Service Booking System**, and **Bidirectional Telegram/Google Sheets CRM Synchronization** into the **LeadGen & Booking Bot**.

All architecture rules have been adhered to:
1. **Strict PEP 8 compliance** and full **Production English docstrings** across all modules.
2. **10x Scalability & Re-skinning**: All niche-specific services, pricing hints, context rules, and replies reside in external [`business_profile.json`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/business_profile.json).
3. **Zero Event-Loop Blocking**: All SQLite WAL disk operations and Google Sheets network I/O run off the main event loop via `asyncio.to_thread()`.
4. **Self-Healing Database**: Dynamic schema inspection via `PRAGMA table_info(leads)` automatically adds missing columns (`comment`, `context_tag`, `status`, `updated_at`) and creates performance indexes on startup.

---

## Deliverables & Component Breakdown

### 1. External Business Configuration ([`business_profile.json`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/business_profile.json))
- Decouples business logic from bot source code.
- Defines service offerings, pricing hints, and descriptions.
- Configures priority-ordered triage rules for tags: `URGENT_VIP`, `PRICE_INQUIRY`, `LOW_PRIORITY`, and default `STANDARD`.
- Includes tailored customer-facing confirmation messages and admin alert badges.

### 2. Context Triage Engine ([`context_triage.py`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/context_triage.py))
- Provides [`analyze_lead_context()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/context_triage.py#L86-L194) to evaluate free-form client commentary and selected services against rule patterns.
- Features an extensible hook [`register_llm_classifier()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/context_triage.py#L40-L53) enabling optional LLM classification.
- Returns structured categorization: `{'context_tag': str, 'custom_user_reply': str, 'admin_alert_prefix': str}`.

### 3. Self-Healing SQLite WAL Storage ([`database.py`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/database.py))
- [`_sync_init_db()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/database.py#L112-L172): Inspects existing columns via `PRAGMA table_info` and executes `ALTER TABLE leads ADD COLUMN` for any missing fields without data loss.
- [`get_active_lead_by_user()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/database.py#L384-L397): Retrieves active leads possessing status in `('NEW', 'IN_PROGRESS', 'CONFIRMED')`.
- [`update_lead_status()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/database.py#L400-L417): Updates lead status and sets ISO-8601 `updated_at` timestamps.
- [`cancel_active_lead()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/database.py#L420-L432): Asynchronously marks active leads as `CANCELLED`.
- Full WAL mode enforcement (`journal_mode=WAL`, `synchronous=NORMAL`, 5000ms busy timeout).

### 4. Two-Way Google Sheets CRM Sync ([`sheets_sync.py`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/sheets_sync.py))
- [`export_lead_to_sheets()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/sheets_sync.py#L214-L241): Appends structured 10-column lead rows `[lead_id, timestamp, user_id, username, name, phone, service, comment, context_tag, status]` and initializes header rows if empty.
- [`update_sheet_lead_status()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/sheets_sync.py#L244-L268): Locates the lead row by `lead_id` in Column A and performs an in-place update on the `Status` column without creating duplicate rows.

### 5. Bot Workflow & Micro-CRM ([`bot.py`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/bot.py))
- **Anti-Duplicate & Self-Service**: When a user triggers `/start`, [`get_active_lead_by_user()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/database.py#L384-L397) checks for pending bookings. Existing bookings present inline actions:
  - `user_cancel:{lead_id}`: Marks lead as `CANCELLED` in SQLite and Google Sheets.
  - `user_rebook:{lead_id}`: Cancels old lead across systems and seamlessly restarts onboarding.
- **Context Triage Step**: New FSM state [`LeadGenState.waiting_for_comment`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/bot.py#L86-L90) with a `⏭ Пропустить` button prompts for task details/urgency, runs [`analyze_lead_context()`](file:///c:/Dev/LeadGen%20&%20Booking%20Bot/context_triage.py#L86-L194), delivers tailored feedback, and persists the lead.
- **Admin Micro-CRM**: Admin alerts include context priority badges (`🔥 URGENT_VIP`, etc.) and interactive inline status buttons:
  - `admin_status:{lead_id}:CONFIRMED`: Updates SQLite, updates Google Sheets, updates admin message badge, and automatically notifies the client.
  - `admin_status:{lead_id}:IN_PROGRESS`: Updates status in SQLite, Google Sheets, and the admin message.
  - `admin_status:{lead_id}:REJECTED`: Flags lead as rejected/spam across systems.

---

## Verification & Test Results
A comprehensive 13-case test suite verified all functional pathways:
- **Triage classification**: Verified `URGENT_VIP`, `PRICE_INQUIRY`, `LOW_PRIORITY`, default `STANDARD`, skipped/None commentary, and extensible LLM hooks.
- **Schema self-healing**: Tested on legacy SQLite tables missing new columns; confirmed seamless migration, column addition, and status backfilling.
- **Status updates**: Verified lifecycle transitions across `NEW`, `IN_PROGRESS`, `CONFIRMED`, and `CANCELLED`.
- **In-place Google Sheets updates**: Mocked gspread integration confirming in-place cell updates matching Column A IDs.
- **Syntax validation**: Clean compilation via `python -m py_compile`.
