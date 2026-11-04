"""Google Sheets synchronization module for LeadGen & Booking Bot.

Provides an isolated asynchronous export and status update interface for managing
lead records in Google Spreadsheets via gspread, using asyncio.to_thread to prevent
blocking the main event loop.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import gspread
from gspread.exceptions import GSpreadException

logger = logging.getLogger(__name__)

# Standard columns expected in the synchronized Google Spreadsheet
SHEET_HEADERS: List[str] = [
    "Lead ID",
    "Timestamp",
    "User ID",
    "Username",
    "Name",
    "Phone",
    "Service",
    "Comment",
    "Context Tag",
    "Status",
]


def _sync_export_lead_to_sheets(
    creds_path: str,
    sheet_id: Optional[str],
    row_data: Union[List[Any], Dict[str, Any]],
    worksheet: Union[int, str] = 0,
) -> Optional[Dict[str, Any]]:
    """Synchronously authenticate and append a lead row to a Google Spreadsheet.

    Automatically inspects and writes the standard header row if the target
    worksheet is newly initialized or empty.

    Args:
        creds_path: Filesystem path to the Google service account JSON keyfile.
        sheet_id: Unique Google Spreadsheet key/ID.
        row_data: List of cell values or dictionary representing the lead.
            Standard sequence: [lead_id, timestamp, user_id, username, name,
            phone, service, comment, context_tag, status].
        worksheet: Worksheet index (0-based) or title string. Defaults to 0.

    Returns:
        Optional[Dict[str, Any]]: API response dictionary, or None if skipped/failed.
    """
    if not sheet_id or not sheet_id.strip():
        logger.warning(
            "GOOGLE_SHEET_ID is not configured. Skipping Google Sheets export."
        )
        return None

    resolved_creds = Path(creds_path).resolve()
    if not resolved_creds.is_file():
        logger.warning(
            "Service account credentials file not found: '%s'. Skipping export.",
            resolved_creds,
        )
        return None

    try:
        logger.debug("Authenticating service account with keyfile: %s", resolved_creds.name)
        client = gspread.service_account(filename=str(resolved_creds))

        logger.debug("Opening spreadsheet by key: %s", sheet_id)
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

        # Check if worksheet is brand new or empty, and prepend headers
        existing_values = ws.get_all_values()
        if not existing_values:
            logger.info("Initializing new spreadsheet header row in sheet '%s'...", ws.title)
            ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")

        # Normalize row_data into a list of cell values
        if isinstance(row_data, dict):
            values = list(row_data.values())
        else:
            values = list(row_data)

        logger.info(
            "Appending lead row (%d cells) to sheet '%s' [ID: %s]...",
            len(values),
            ws.title,
            sheet_id,
        )
        result = ws.append_row(values, value_input_option="USER_ENTERED")
        logger.info(
            "Successfully exported lead row to Google Sheets ID '%s'.",
            sheet_id,
        )
        return result
    except (GSpreadException, Exception) as exc:
        logger.error(
            "Google Sheets export failed for sheet '%s': %s",
            sheet_id,
            exc,
            exc_info=True,
        )
        return None


def _sync_update_sheet_lead_status(
    creds_path: str,
    sheet_id: Optional[str],
    lead_id: int,
    new_status: str,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Locate a lead record by ID in Column A and update its status in-place.

    Args:
        creds_path: Filesystem path to the Google service account JSON keyfile.
        sheet_id: Unique Google Spreadsheet key/ID.
        lead_id: Primary key ID of the lead to locate in Column A.
        new_status: New status value to write into the Status column.
        worksheet: Worksheet index (0-based) or title string. Defaults to 0.

    Returns:
        bool: True if the cell was updated successfully, False otherwise.
    """
    if not sheet_id or not sheet_id.strip():
        logger.warning(
            "GOOGLE_SHEET_ID is not configured. Skipping Google Sheets status update."
        )
        return False

    resolved_creds = Path(creds_path).resolve()
    if not resolved_creds.is_file():
        logger.warning(
            "Service account credentials file not found: '%s'. Skipping status update.",
            resolved_creds,
        )
        return False

    try:
        logger.debug("Authenticating service account with keyfile: %s", resolved_creds.name)
        client = gspread.service_account(filename=str(resolved_creds))

        logger.debug("Opening spreadsheet by key for status update: %s", sheet_id)
        spreadsheet = client.open_by_key(sheet_id)

        if isinstance(worksheet, int):
            ws = spreadsheet.get_worksheet(worksheet)
        else:
            ws = spreadsheet.worksheet(worksheet)

        if ws is None:
            logger.error(
                "Worksheet '%s' not found in spreadsheet '%s'.", worksheet, sheet_id
            )
            return False

        # Retrieve Column A (Lead ID column) values
        col_a_values = ws.col_values(1)
        target_row: Optional[int] = None
        target_id_str = str(lead_id).strip()

        for row_index, val in enumerate(col_a_values, start=1):
            if val.strip() == target_id_str:
                target_row = row_index
                break

        if target_row is None:
            logger.warning(
                "Lead ID #%d not found in Column A of sheet '%s'. Cannot update status.",
                lead_id,
                sheet_id,
            )
            return False

        # Locate the Status column index dynamically from the header row
        headers = ws.row_values(1)
        status_col_index = 10  # Standard fallback to column 10 (J)
        for col_idx, header_title in enumerate(headers, start=1):
            if header_title.strip().lower() == "status":
                status_col_index = col_idx
                break

        logger.info(
            "Updating Google Sheet cell at row %d, col %d for Lead #%d to status '%s'.",
            target_row,
            status_col_index,
            lead_id,
            new_status,
        )
        ws.update_cell(target_row, status_col_index, new_status)
        logger.info(
            "Successfully updated status for Lead #%d in Google Sheets.",
            lead_id,
        )
        return True
    except (GSpreadException, Exception) as exc:
        logger.error(
            "Failed to update lead status in Google Sheet '%s' for Lead #%d: %s",
            sheet_id,
            lead_id,
            exc,
            exc_info=True,
        )
        return False


async def export_lead_to_sheets(
    creds_path: str,
    sheet_id: Optional[str],
    row_data: Union[List[Any], Dict[str, Any]],
    worksheet: Union[int, str] = 0,
) -> Optional[Dict[str, Any]]:
    """Asynchronously export a lead record to a Google Spreadsheet.

    Delegates synchronous gspread network and file operations to an executor thread
    via asyncio.to_thread(), preventing event loop blocking in async Telegram bot handlers.

    Args:
        creds_path: Filesystem path to the Google service account JSON keyfile.
        sheet_id: Unique Google Spreadsheet key/ID.
        row_data: Cell values to append:
            [lead_id, timestamp, user_id, username, name, phone, service, comment, context_tag, status].
        worksheet: Target worksheet index (default 0) or title name.

    Returns:
        Optional[Dict[str, Any]]: API response detailing inserted range or None.
    """
    return await asyncio.to_thread(
        _sync_export_lead_to_sheets,
        creds_path,
        sheet_id,
        row_data,
        worksheet,
    )


async def update_sheet_lead_status(
    creds_path: str,
    sheet_id: Optional[str],
    lead_id: int,
    new_status: str,
    worksheet: Union[int, str] = 0,
) -> bool:
    """Asynchronously update lead status in a Google Spreadsheet in-place.

    Finds the row corresponding to lead_id in Column A and updates the Status column,
    delegating network calls to an async worker thread.

    Args:
        creds_path: Filesystem path to the Google service account JSON keyfile.
        sheet_id: Unique Google Spreadsheet key/ID.
        lead_id: Primary key ID of the lead to locate.
        new_status: New status value to write.
        worksheet: Target worksheet index (default 0) or title name.

    Returns:
        bool: True if successfully updated, False otherwise.
    """
    return await asyncio.to_thread(
        _sync_update_sheet_lead_status,
        creds_path,
        sheet_id,
        lead_id,
        new_status,
        worksheet,
    )
