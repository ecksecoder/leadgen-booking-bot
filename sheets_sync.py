"""Google Sheets synchronization module for LeadGen & Booking Bot.

Provides non-blocking asynchronous export, localized header synchronization, and
in-place status updates for managing lead records in Google Spreadsheets via gspread,
using asyncio.to_thread to prevent blocking the main event loop. All column headers
and status strings are localized according to the administrator's Telegram language,
while client inputs (Name, Phone, Notes) are preserved strictly in RAW format.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import gspread
from dotenv import load_dotenv
from gspread.exceptions import GSpreadException

from locales import get_sheet_headers, get_sheet_priority, get_sheet_status

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_CREDS_PATH: str = os.getenv("GOOGLE_CREDS_PATH", "credentials.json")
DEFAULT_SHEET_ID: Optional[str] = os.getenv("GOOGLE_SHEET_ID")


def _get_worksheet(
    creds_path: str,
    sheet_id: Optional[str],
    worksheet: Union[int, str] = 0,
) -> Optional[gspread.Worksheet]:
    """Authenticate and retrieve the target worksheet instance."""
    if not sheet_id or not sheet_id.strip():
        logger.warning(
            "GOOGLE_SHEET_ID is not configured. Skipping Google Sheets operation."
        )
        return None

    resolved_creds = Path(creds_path).resolve()
    if not resolved_creds.is_file():
        logger.warning(
            "Service account credentials file not found: '%s'. Skipping operation.",
            resolved_creds,
        )
        return None

    try:
        client = gspread.service_account(filename=str(resolved_creds))
        spreadsheet = client.open_by_key(sheet_id)
        if isinstance(worksheet, int):
            ws = spreadsheet.get_worksheet(worksheet)
        else:
            ws = spreadsheet.worksheet(worksheet)

        if ws is None:
            logger.error(
                "Worksheet '%s' not found in spreadsheet '%s'.", worksheet, sheet_id
            )
            return None
        return ws
    except Exception as exc:
        logger.error(
            "Failed to access Google Spreadsheet '%s': %s",
            sheet_id,
            exc,
            exc_info=True,
        )
        return None


def _sync_sync_sheet_headers(
    admin_lang: str = "en",
    creds_path: str = DEFAULT_CREDS_PATH,
    sheet_id: Optional[str] = DEFAULT_SHEET_ID,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Synchronously inspect Row 1 and update column headers to match admin's language.

    Only alters Row 1 headers without modifying existing lead data rows.

    Args:
        admin_lang: Administrator's current language code ('en', 'uk', 'ru').
        creds_path: Path to Google Service Account JSON keyfile.
        sheet_id: Google Spreadsheet ID.
        worksheet: Target worksheet index or name.

    Returns:
        bool: True if headers are synchronized or up-to-date, False on error.
    """
    ws = _get_worksheet(creds_path, sheet_id, worksheet)
    if ws is None:
        return False

    try:
        target_headers = get_sheet_headers(admin_lang)
        existing_values = ws.row_values(1)

        if existing_values != target_headers:
            logger.info(
                "Updating Google Sheet Row 1 headers to locale '%s' (%s)...",
                admin_lang,
                target_headers,
            )
            ws.update(values=[target_headers], range_name="A1:I1")
            logger.info("Successfully synchronized Google Sheet headers.")
        else:
            logger.debug("Google Sheet headers are already synchronized for locale '%s'.", admin_lang)
        return True
    except (GSpreadException, Exception) as exc:
        logger.error("Failed to synchronize Google Sheet headers: %s", exc, exc_info=True)
        return False


def _sync_append_lead_row(
    lead_data: Dict[str, Any],
    admin_lang: str = "en",
    creds_path: str = DEFAULT_CREDS_PATH,
    sheet_id: Optional[str] = DEFAULT_SHEET_ID,
    worksheet: Union[int, str] = 0,
) -> Optional[Dict[str, Any]]:
    """Synchronously append a structured 9-column lead row to Google Sheets.

    Columns written:
      Col A: Lead ID
      Col B: Timestamp
      Col C: Name (strictly RAW)
      Col D: Phone (strictly RAW)
      Col E: Service
      Col F: Notes (strictly RAW client text, never translated)
      Col G: Priority (localized to admin_lang)
      Col H: Status (localized to admin_lang)
      Col I: Username

    Args:
        lead_data: Dictionary containing lead attributes.
        admin_lang: Administrator's active language code.
        creds_path: Path to credentials JSON.
        sheet_id: Google Spreadsheet ID.
        worksheet: Worksheet identifier.

    Returns:
        Optional[Dict[str, Any]]: gspread response dictionary or None.
    """
    ws = _get_worksheet(creds_path, sheet_id, worksheet)
    if ws is None:
        return None

    try:
        target_headers = get_sheet_headers(admin_lang)
        existing_rows = ws.row_values(1)
        if not existing_rows:
            logger.info("Sheet is empty. Writing Row 1 headers for locale '%s'...", admin_lang)
            ws.update(values=[target_headers], range_name="A1:I1")

        lead_id = str(lead_data.get("lead_id") or lead_data.get("id") or "")
        timestamp = str(
            lead_data.get("timestamp")
            or lead_data.get("created_at")
            or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        )
        # Preserve RAW client inputs without transliteration
        name = str(lead_data.get("full_name") or lead_data.get("client_name") or lead_data.get("name") or "")
        phone = str(lead_data.get("phone") or lead_data.get("phone_number") or "")
        service = str(lead_data.get("service") or "")
        raw_notes = str(lead_data.get("notes") if lead_data.get("notes") is not None else (lead_data.get("comment") or "—"))
        if not raw_notes.strip():
            raw_notes = "—"

        raw_priority = str(lead_data.get("priority") or lead_data.get("context_tag") or "STANDARD")
        priority = get_sheet_priority(raw_priority, admin_lang)

        raw_status = str(lead_data.get("status") or "NEW")
        status = get_sheet_status(raw_status, admin_lang)

        username = str(lead_data.get("username") or "")
        if username and not username.startswith("@") and not username.startswith("http"):
            username = f"@{username}"

        row_values = [
            lead_id,
            timestamp,
            name,
            phone,
            service,
            raw_notes,
            priority,
            status,
            username,
        ]

        logger.info(
            "Appending lead row for #%s to sheet '%s' (admin_lang=%s)...",
            lead_id,
            ws.title,
            admin_lang,
        )
        result = ws.append_row(row_values, value_input_option="USER_ENTERED")
        logger.info("Successfully appended lead #%s to Google Sheets.", lead_id)
        return result
    except (GSpreadException, Exception) as exc:
        logger.error("Failed to append lead row to Google Sheets: %s", exc, exc_info=True)
        return None


def _sync_update_lead_status(
    lead_id: Union[str, int],
    new_status_key: str,
    admin_lang: str = "en",
    creds_path: str = DEFAULT_CREDS_PATH,
    sheet_id: Optional[str] = DEFAULT_SHEET_ID,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Synchronously locate a lead in Column A and update localized status in Column H.

    Args:
        lead_id: Unique Lead ID to locate in Column A.
        new_status_key: Status key ('CONFIRMED', 'IN_PROGRESS', 'REJECTED', 'CANCELLED').
        admin_lang: Administrator's active language code.
        creds_path: Path to credentials JSON.
        sheet_id: Google Spreadsheet ID.
        worksheet: Worksheet identifier.

    Returns:
        bool: True if status cell was updated, False otherwise.
    """
    ws = _get_worksheet(creds_path, sheet_id, worksheet)
    if ws is None:
        return False

    try:
        col_a_values = ws.col_values(1)
        target_id_str = str(lead_id).strip()
        target_row: Optional[int] = None

        for row_index, val in enumerate(col_a_values, start=1):
            if str(val).strip() == target_id_str:
                target_row = row_index
                break

        if target_row is None:
            logger.warning(
                "Lead ID #%s not found in Column A of sheet '%s'. Cannot update status.",
                lead_id,
                sheet_id,
            )
            return False

        # Status is strictly in Column H (Column 8)
        localized_status = get_sheet_status(new_status_key, admin_lang)
        logger.info(
            "Updating cell at Row %d, Col 8 (Status) for Lead #%s -> '%s' (admin_lang=%s)...",
            target_row,
            lead_id,
            localized_status,
            admin_lang,
        )
        ws.update_cell(target_row, 8, localized_status)
        logger.info("Successfully updated lead status in Google Sheets.")
        return True
    except (GSpreadException, Exception) as exc:
        logger.error(
            "Failed to update lead status in Google Sheet for Lead #%s: %s",
            lead_id,
            exc,
            exc_info=True,
        )
        return False


async def sync_sheet_headers(
    admin_lang: str = "en",
    creds_path: Optional[str] = None,
    sheet_id: Optional[str] = None,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Asynchronously synchronize Row 1 headers to match administrator's language.

    Args:
        admin_lang: Administrator's current language code ('en', 'uk', 'ru').
        creds_path: Optional path to credentials JSON.
        sheet_id: Optional Google Spreadsheet ID.
        worksheet: Target worksheet.

    Returns:
        bool: True on success, False on failure.
    """
    return await asyncio.to_thread(
        _sync_sync_sheet_headers,
        admin_lang,
        creds_path or DEFAULT_CREDS_PATH,
        sheet_id or DEFAULT_SHEET_ID,
        worksheet,
    )


async def append_lead_row(
    lead_data: Dict[str, Any],
    admin_lang: str = "en",
    creds_path: Optional[str] = None,
    sheet_id: Optional[str] = None,
    worksheet: Union[int, str] = 0,
) -> Optional[Dict[str, Any]]:
    """Asynchronously append a 9-column lead row with localized priority and status.

    Args:
        lead_data: Lead dictionary.
        admin_lang: Administrator's current language code.
        creds_path: Optional path to credentials JSON.
        sheet_id: Optional Google Spreadsheet ID.
        worksheet: Target worksheet.

    Returns:
        Optional[Dict[str, Any]]: gspread response or None.
    """
    return await asyncio.to_thread(
        _sync_append_lead_row,
        lead_data,
        admin_lang,
        creds_path or DEFAULT_CREDS_PATH,
        sheet_id or DEFAULT_SHEET_ID,
        worksheet,
    )


async def update_lead_status(
    lead_id: Union[str, int],
    new_status_key: str,
    admin_lang: str = "en",
    creds_path: Optional[str] = None,
    sheet_id: Optional[str] = None,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Asynchronously locate lead by ID in Column A and update Column H status.

    Args:
        lead_id: Unique Lead ID.
        new_status_key: Target status identifier ('CONFIRMED', 'IN_PROGRESS', etc.).
        admin_lang: Administrator's current language code.
        creds_path: Optional path to credentials JSON.
        sheet_id: Optional Google Spreadsheet ID.
        worksheet: Target worksheet.

    Returns:
        bool: True if updated, False otherwise.
    """
    return await asyncio.to_thread(
        _sync_update_lead_status,
        lead_id,
        new_status_key,
        admin_lang,
        creds_path or DEFAULT_CREDS_PATH,
        sheet_id or DEFAULT_SHEET_ID,
        worksheet,
    )


# Backwards compatibility wrappers
async def export_lead_to_sheets(
    creds_path: str,
    sheet_id: Optional[str],
    row_data: Union[List[Any], Dict[str, Any]],
    worksheet: Union[int, str] = 0,
) -> Optional[Dict[str, Any]]:
    """Legacy compatibility wrapper for export_lead_to_sheets."""
    if isinstance(row_data, dict):
        return await append_lead_row(row_data, "en", creds_path, sheet_id, worksheet)

    # If row_data is a list: map to lead_data dict
    lead_dict: Dict[str, Any] = {}
    if len(row_data) >= 1:
        lead_dict["lead_id"] = row_data[0]
    if len(row_data) >= 2:
        lead_dict["timestamp"] = row_data[1]
    if len(row_data) >= 5:
        lead_dict["name"] = row_data[4]
    if len(row_data) >= 6:
        lead_dict["phone"] = row_data[5]
    if len(row_data) >= 7:
        lead_dict["service"] = row_data[6]
    if len(row_data) >= 8:
        lead_dict["notes"] = row_data[7]
    if len(row_data) >= 9:
        lead_dict["priority"] = row_data[8]
    if len(row_data) >= 10:
        lead_dict["status"] = row_data[9]
    if len(row_data) >= 4:
        lead_dict["username"] = row_data[3]

    return await append_lead_row(lead_dict, "en", creds_path, sheet_id, worksheet)


async def update_sheet_lead_status(
    creds_path: str,
    sheet_id: Optional[str],
    lead_id: Union[int, str],
    new_status: str,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Legacy compatibility wrapper for update_sheet_lead_status."""
    return await update_lead_status(
        lead_id=lead_id,
        new_status_key=new_status,
        admin_lang="en",
        creds_path=creds_path,
        sheet_id=sheet_id,
        worksheet=worksheet,
    )
