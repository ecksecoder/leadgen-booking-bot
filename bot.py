"""Main entry point for the LeadGen & Booking Telegram Bot.

Implements sequential lead collection using aiogram 3.x FSM, dynamic service catalog,
priority-driven context triage loaded from 'business_profile.json', anti-duplicate
self-service, trilingual localization (en, uk, ru), dynamic administrator locale tracking,
on-demand raw commentary translation, strict RAW client input preservation, and
bidirectional CRM synchronization between Telegram and Google Sheets.
"""

import asyncio
import html
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Final, List, Optional, Tuple, Union

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    TelegramObject,
    User,
)
from dotenv import load_dotenv

from context_triage import analyze_lead_context, load_business_profile
from database import (
    cancel_active_lead,
    delete_booking,
    get_active_lead_by_user,
    get_admin_language,
    get_lead_by_id,
    get_user_bookings,
    get_user_language,
    has_user_profile,
    init_db,
    save_lead,
    set_admin_language,
    set_user_language,
    update_lead_status,
)
from locales import (
    detect_locale,
    get_button_variants,
    get_language_inline_kb,
    get_sheet_status,
    get_text,
)
from sheets_sync import append_lead_row, sync_sheet_headers, update_lead_status as update_sheet_status

# Load environment configuration from .env file
load_dotenv()

# Configure logging
LOG_LEVEL_NAME: str = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL_NAME, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("booking_bot")

# Environment variables validation
BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is missing. Please set it in your .env file.")
    raise RuntimeError("BOT_TOKEN is required to start the bot.")

RAW_ADMIN_ID: Optional[str] = os.getenv("ADMIN_ID")
if not RAW_ADMIN_ID or not RAW_ADMIN_ID.strip().lstrip("-").isdigit():
    logger.critical(
        "ADMIN_ID is missing or invalid. Please provide a numeric Telegram ID in .env."
    )
    raise RuntimeError("A valid numeric ADMIN_ID is required to start the bot.")

ADMIN_ID: Final[int] = int(RAW_ADMIN_ID.strip())

GOOGLE_CREDS_PATH: Final[str] = os.getenv("GOOGLE_CREDS_PATH", "credentials.json")
GOOGLE_SHEET_ID: Optional[str] = os.getenv("GOOGLE_SHEET_ID")

# Dynamic Admin Telegram Language tracking state
CURRENT_ADMIN_LANG: str = "en"

# Router initialization
router = Router(name="leadgen_router")


class AdminLanguageMiddleware(BaseMiddleware):
    """Inspects updates from ADMIN_ID and synchronizes admin language dynamically."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        global CURRENT_ADMIN_LANG
        from_user: Optional[User] = getattr(event, "from_user", None)
        if from_user and from_user.id == ADMIN_ID:
            new_lang = detect_locale(from_user.language_code)
            if new_lang != CURRENT_ADMIN_LANG:
                logger.info(
                    "Dynamic Admin language change detected: %s -> %s (raw Telegram code: %s)",
                    CURRENT_ADMIN_LANG,
                    new_lang,
                    from_user.language_code,
                )
                CURRENT_ADMIN_LANG = new_lang
                await set_admin_language(ADMIN_ID, new_lang)
                asyncio.create_task(sync_sheet_headers(new_lang))
        return await handler(event, data)


class LeadGenState(StatesGroup):
    """FSM states for the sequential lead generation sequence."""

    waiting_for_service = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_comment = State()


async def resolve_user_locale(
    user_id: int, telegram_lang: Optional[str]
) -> Tuple[str, bool]:
    """Resolve active interface language and whether it was auto-detected from Telegram.

    Args:
        user_id: Telegram user ID.
        telegram_lang: Raw language code from Telegram client.

    Returns:
        Tuple[str, bool]: (language_code, is_auto).
    """
    db_lang = await get_user_language(user_id)
    if db_lang is not None:
        return (db_lang, False)
    return (detect_locale(telegram_lang), True)


def get_configured_services() -> List[Dict[str, Any]]:
    """Retrieve service definitions dynamically from business_profile.json.

    Returns:
        List[Dict[str, Any]]: List of service definition mappings.
    """
    profile = load_business_profile()
    services = profile.get("services", [])
    if not services:
        return [
            {
                "id": "default_consultation",
                "name": "💼 Consultation",
                "price_hint": "Upon request",
            }
        ]
    return services


def get_main_menu_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Construct persistent reply keyboard for general navigation.

    Args:
        lang: Target locale code.

    Returns:
        ReplyKeyboardMarkup: Main menu keyboard with Book, My Bookings, and Lang.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text("btn_book", lang))],
            [
                KeyboardButton(text=get_text("btn_my_bookings", lang)),
                KeyboardButton(text=get_text("btn_lang", lang)),
            ],
        ],
        resize_keyboard=True,
    )


def get_services_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Build ReplyKeyboardMarkup containing services plus Cancel button.

    Args:
        lang: Target locale code.

    Returns:
        ReplyKeyboardMarkup: Keyboard with dynamic service options and Cancel.
    """
    services = get_configured_services()
    keyboard_buttons = [
        [KeyboardButton(text=str(s.get("name", "Service")))]
        for s in services
        if s.get("name")
    ]
    keyboard_buttons.append([KeyboardButton(text=get_text("btn_cancel", lang))])
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=get_text("placeholder_service", lang),
    )


def get_cancel_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Build a ReplyKeyboardMarkup containing only the Cancel action.

    Args:
        lang: Target locale code.

    Returns:
        ReplyKeyboardMarkup: Single cancel action keyboard.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_text("btn_cancel", lang))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_phone_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Build ReplyKeyboardMarkup allowing contact card sharing or cancellation.

    Args:
        lang: Target locale code.

    Returns:
        ReplyKeyboardMarkup: Keyboard with contact sharing and Cancel.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=get_text("btn_share_contact", lang), request_contact=True
                )
            ],
            [KeyboardButton(text=get_text("btn_cancel", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=get_text("placeholder_phone", lang),
    )


def get_comment_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Build ReplyKeyboardMarkup for the context triage step with a Skip button.

    Args:
        lang: Target locale code.

    Returns:
        ReplyKeyboardMarkup: Keyboard with Skip and Cancel buttons.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text("btn_skip", lang))],
            [KeyboardButton(text=get_text("btn_cancel", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=get_text("placeholder_comment", lang),
    )


def get_admin_crm_keyboard(
    lead_id: int,
    admin_lang: str = "en",
    show_hide_translate: bool = False,
) -> InlineKeyboardMarkup:
    """Construct inline micro-CRM keyboard for administrator status management and on-demand translation.

    Args:
        lead_id: Primary key ID of the target lead record.
        admin_lang: Administrator's current language code.
        show_hide_translate: If True, renders '↩️ Hide Translation' button, else '🌐 Translate Notes'.

    Returns:
        InlineKeyboardMarkup: Interactive buttons for Confirm, In Progress, Reject, and Translate.
    """
    confirm_text = get_text("crm_btn_confirm", admin_lang)
    in_progress_text = get_text("crm_btn_in_progress", admin_lang)
    reject_text = get_text("crm_btn_reject", admin_lang)

    if show_hide_translate:
        trans_btn = InlineKeyboardButton(
            text=get_text("crm_btn_hide_translation", admin_lang),
            callback_data=f"hide_notes:{lead_id}",
        )
    else:
        trans_btn = InlineKeyboardButton(
            text=get_text("crm_btn_translate", admin_lang),
            callback_data=f"translate_notes:{lead_id}",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=confirm_text,
                    callback_data=f"admin_status:{lead_id}:CONFIRMED",
                ),
                InlineKeyboardButton(
                    text=in_progress_text,
                    callback_data=f"admin_status:{lead_id}:IN_PROGRESS",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=reject_text,
                    callback_data=f"admin_status:{lead_id}:REJECTED",
                ),
                trans_btn,
            ],
        ]
    )


async def translate_text(text: str, target_lang: str = "en") -> str:
    """Translate raw text to target language using Google Translate API asynchronously.

    Args:
        text: Raw text to translate.
        target_lang: Target language code ('en', 'uk', 'ru').

    Returns:
        str: Translated text or original text if translation is skipped/unavailable.
    """
    if not text or not text.strip():
        return ""

    def _sync_translate() -> str:
        import json
        import urllib.parse
        import urllib.request

        tl = target_lang.lower().strip()
        if tl not in ("en", "uk", "ru"):
            tl = "en"

        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl={tl}&dt=t&q=" + urllib.parse.quote(text)
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if (
                    payload
                    and isinstance(payload, list)
                    and len(payload) > 0
                    and isinstance(payload[0], list)
                ):
                    translated = "".join(
                        part[0]
                        for part in payload[0]
                        if part and len(part) > 0 and part[0]
                    )
                    return translated.strip()
        except Exception as exc:
            logger.warning("Translation request failed: %s", exc)
        return text

    return await asyncio.to_thread(_sync_translate)


def format_admin_card(
    lead: Dict[str, Any],
    admin_lang: str,
    badge_text: Optional[str] = None,
    now_time: Optional[str] = None,
    translated_notes: Optional[str] = None,
) -> str:
    """Render the administrator CRM alert card strictly in the admin's language.

    Preserves raw client inputs (name, phone, notes) without corruption.

    Args:
        lead: Lead dictionary retrieved from database.
        admin_lang: Administrator's current language code.
        badge_text: Optional updated status badge text.
        now_time: Optional timestamp string of status transition.
        translated_notes: Optional translated commentary to append.

    Returns:
        str: HTML-formatted administrator card text.
    """
    lead_id = lead.get("id") or lead.get("lead_id", 0)
    service = str(lead.get("service", "N/A"))
    client_name = str(lead.get("full_name") or lead.get("client_name", "N/A"))
    phone = str(lead.get("phone") or lead.get("phone_number", "N/A"))
    raw_comment = lead.get("notes") if lead.get("notes") is not None else lead.get("comment")
    tag = str(lead.get("priority") or lead.get("context_tag") or "STANDARD")
    lead_uid = lead.get("user_id", 0)
    lead_uname = lead.get("username")

    if lead_uname:
        uname_disp = f'<a href="https://t.me/{lead_uname}">@{lead_uname}</a>'
    else:
        uname_disp = f'<a href="tg://user?id={lead_uid}">{html.escape(client_name)}</a>'

    triage = analyze_lead_context(raw_comment, service=service, lang=admin_lang)
    alert_prefix = triage.get("admin_alert_prefix", "📋")

    comment_disp = html.escape(str(raw_comment)) if raw_comment else get_text("no_comment", admin_lang)

    if badge_text:
        card_text = get_text(
            "manager_crm_status_update",
            admin_lang,
            alert_prefix=alert_prefix,
            lead_id=lead_id,
            badge_text=badge_text,
            now_time=now_time or datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            tag=tag,
            service=html.escape(service),
            client_name=html.escape(client_name),
            phone=html.escape(phone),
            uname_disp=uname_disp,
            lead_uid=lead_uid,
            comment=comment_disp,
        )
    else:
        card_text = get_text(
            "manager_crm_alert",
            admin_lang,
            alert_prefix=alert_prefix,
            lead_id=lead_id,
            context_tag=tag,
            service=html.escape(service),
            client_name=html.escape(client_name),
            phone=html.escape(phone),
            username_display=uname_disp,
            user_id=lead_uid,
            comment=comment_disp,
        )

    if translated_notes is not None:
        trans_header = get_text(
            "crm_translation_header",
            admin_lang,
            lang=admin_lang.upper(),
            translated_notes=html.escape(translated_notes),
        )
        card_text += f"\n\n{trans_header}"

    return card_text


def is_valid_phone(phone: str) -> bool:
    """Validate whether input string conforms to international phone format.

    Args:
        phone: Raw phone string provided by user.

    Returns:
        bool: True if string contains a valid phone representation, False otherwise.
    """
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone)
    return bool(re.fullmatch(r"^\+?[0-9]{7,15}$", cleaned))


async def show_user_menu_or_booking(
    message: Message,
    state: FSMContext,
    lang: str,
) -> None:
    """Evaluate active bookings and either display existing status or service catalog.

    Args:
        message: Incoming Telegram message.
        state: Active FSM context.
        lang: Resolved interface locale.
    """
    user_id = message.from_user.id if message.from_user else 0
    active_lead = await get_active_lead_by_user(user_id)

    if active_lead:
        lead_id = active_lead.get("id") or active_lead.get("lead_id", 0)
        service = active_lead.get("service", "Consultation")
        client_name = active_lead.get("full_name") or active_lead.get("client_name", "Client")
        phone = active_lead.get("phone") or active_lead.get("phone_number", "—")
        raw_comment = active_lead.get("notes") if active_lead.get("notes") is not None else active_lead.get("comment")
        comment = raw_comment or get_text("no_comment", lang)
        raw_status = active_lead.get("status", "NEW")
        status = get_sheet_status(raw_status, lang)
        tag = active_lead.get("priority") or active_lead.get("context_tag") or "STANDARD"

        existing_prompt = get_text(
            "active_booking_card",
            lang,
            lead_id=lead_id,
            service=html.escape(service),
            client_name=html.escape(client_name),
            phone=html.escape(phone),
            comment=html.escape(comment),
            status=status,
            tag=tag,
        )
        self_service_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("btn_cancel_booking", lang),
                        callback_data=f"user_cancel:{lead_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_text("btn_reschedule", lang),
                        callback_data=f"user_rebook:{lead_id}",
                    )
                ],
            ]
        )
        await message.answer(
            text=existing_prompt,
            reply_markup=self_service_keyboard,
        )
        return

    # Present dynamic services from business_profile.json
    profile = load_business_profile()
    biz_name = profile.get("business_name", "LeadGen & Booking Bot")
    user_name = message.from_user.first_name if message.from_user else "Client"

    welcome_text = get_text(
        "welcome_services",
        lang,
        name=html.escape(user_name),
        biz_name=html.escape(biz_name),
    )
    await message.answer(
        text=welcome_text,
        reply_markup=get_services_keyboard(lang),
    )
    await state.set_state(LeadGenState.waiting_for_service)


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    """Handle /start command, enforcing onboarding gate if user language is unset.

    Args:
        message: Incoming Telegram message.
        state: Active FSM context.
    """
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None

    # Onboarding language gate: check if user settings exist in database
    if not await has_user_profile(user_id):
        detected_lang = detect_locale(telegram_lang)
        banner_text = get_text("onboarding_header", "en")
        markup = get_language_inline_kb(
            active_lang=detected_lang,
            is_auto=True,
            prefix="lang_init",
        )
        await message.answer(
            text=banner_text,
            reply_markup=markup,
        )
        return

    # User already onboarded: resolve locale and proceed
    lang, _ = await resolve_user_locale(user_id, telegram_lang)
    await show_user_menu_or_booking(message, state, lang)


@router.callback_query(F.data.startswith("lang_init:"))
async def process_lang_init_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle onboarding language selection, persist choice, and show main greeting.

    Args:
        callback: Incoming callback query from onboarding banner.
        state: Active FSM context.
    """
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    choice = callback.data.split(":", 1)[1] if callback.data else "auto"

    if choice == "auto":
        await set_user_language(user_id, None)
        active_lang = detect_locale(telegram_lang)
    else:
        await set_user_language(user_id, choice)
        active_lang = choice

    await callback.answer(get_text("lang_updated", active_lang))

    profile = load_business_profile()
    biz_name = profile.get("business_name", "LeadGen & Booking Bot")
    user_name = callback.from_user.first_name if callback.from_user else "Client"

    greeting_text = get_text(
        "welcome_menu",
        active_lang,
        name=html.escape(user_name),
        biz_name=html.escape(biz_name),
    )

    if callback.message and isinstance(callback.message, Message):
        await callback.message.delete()
        await callback.message.answer(
            text=greeting_text,
            reply_markup=get_main_menu_keyboard(active_lang),
        )


@router.message(Command("lang"))
@router.message(F.text.in_(get_button_variants("btn_lang")))
async def handle_lang_command(message: Message) -> None:
    """Handle /lang command or 'Change Language' button with trilingual selector.

    Args:
        message: Incoming Telegram message.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    active_lang, is_auto = await resolve_user_locale(user_id, telegram_lang)

    header_text = get_text("onboarding_header", active_lang)
    markup = get_language_inline_kb(
        active_lang=active_lang,
        is_auto=is_auto,
        prefix="lang_set",
    )
    await message.answer(text=header_text, reply_markup=markup)


@router.callback_query(F.data.startswith("lang_set:"))
async def process_lang_set_callback(callback: CallbackQuery) -> None:
    """Handle language update, edit selector markup in-place, and refresh reply keyboard.

    Args:
        callback: Incoming callback query from language selector.
    """
    user_id = callback.from_user.id if callback.from_user else 0
    telegram_lang = callback.from_user.language_code if callback.from_user else None
    choice = callback.data.split(":", 1)[1] if callback.data else "auto"

    if choice == "auto":
        await set_user_language(user_id, None)
        new_lang = detect_locale(telegram_lang)
        is_auto = True
    else:
        await set_user_language(user_id, choice)
        new_lang = choice
        is_auto = False

    new_markup = get_language_inline_kb(
        active_lang=new_lang,
        is_auto=is_auto,
        prefix="lang_set",
    )

    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=new_markup)
        except TelegramAPIError as edit_err:
            logger.debug("Inline markup edit skipped or unchanged: %s", edit_err)

    await callback.answer(get_text("lang_updated", new_lang))

    # Refresh persistent ReplyKeyboardMarkup for the user
    notice_text = get_text("lang_changed_notice", new_lang)
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            text=notice_text,
            reply_markup=get_main_menu_keyboard(new_lang),
        )


@router.message(Command("cancel"))
@router.message(F.text.in_(get_button_variants("btn_cancel")))
@router.message(F.text.casefold().in_({"cancel", "скасувати", "отмена", "/cancel"}))
async def handle_cancellation(message: Message, state: FSMContext) -> None:
    """Cancel active lead generation or display cancellation options for active booking.

    Args:
        message: Incoming Telegram message.
        state: Active FSM context.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            text=get_text("operation_cancelled", lang),
            reply_markup=get_main_menu_keyboard(lang),
        )
        return

    active_lead = await get_active_lead_by_user(user_id)
    if not active_lead:
        await message.answer(
            text=get_text("no_active_bookings", lang),
            reply_markup=get_main_menu_keyboard(lang),
        )
        return

    lead_id = active_lead.get("id") or active_lead.get("lead_id", 0)
    service = active_lead.get("service", "Consultation")
    client_name = active_lead.get("full_name") or active_lead.get("client_name", "Client")
    phone = active_lead.get("phone") or active_lead.get("phone_number", "—")
    raw_comment = active_lead.get("notes") if active_lead.get("notes") is not None else active_lead.get("comment")
    comment = raw_comment or get_text("no_comment", lang)
    status = get_sheet_status(active_lead.get("status", "NEW"), lang)
    tag = active_lead.get("priority") or active_lead.get("context_tag") or "STANDARD"

    card_text = get_text(
        "active_booking_card",
        lang,
        lead_id=lead_id,
        service=html.escape(service),
        client_name=html.escape(client_name),
        phone=html.escape(phone),
        comment=html.escape(comment),
        status=status,
        tag=tag,
    )
    await message.answer(
        text=card_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("btn_cancel_booking", lang),
                        callback_data=f"user_cancel:{lead_id}",
                    )
                ]
            ]
        ),
    )


@router.message(Command("book"))
@router.message(F.text.in_(get_button_variants("btn_book")))
async def handle_book_button(message: Message, state: FSMContext) -> None:
    """Handle 'Book a Consultation' menu action.

    Args:
        message: Incoming Telegram message.
        state: Active FSM context.
    """
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)
    await show_user_menu_or_booking(message, state, lang)


@router.message(Command("my_bookings"))
@router.message(F.text.in_(get_button_variants("btn_my_bookings")))
async def handle_my_bookings_button(message: Message) -> None:
    """Handle 'My Bookings' button, showing active booking details or no-booking notice.

    Args:
        message: Incoming Telegram message.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    active_lead = await get_active_lead_by_user(user_id)
    if not active_lead:
        await message.answer(
            text=get_text("no_active_bookings", lang),
            reply_markup=get_main_menu_keyboard(lang),
        )
        return

    lead_id = active_lead.get("id") or active_lead.get("lead_id", 0)
    service = active_lead.get("service", "Consultation")
    client_name = active_lead.get("full_name") or active_lead.get("client_name", "Client")
    phone = active_lead.get("phone") or active_lead.get("phone_number", "—")
    raw_comment = active_lead.get("notes") if active_lead.get("notes") is not None else active_lead.get("comment")
    comment = raw_comment or get_text("no_comment", lang)
    status = get_sheet_status(active_lead.get("status", "NEW"), lang)
    tag = active_lead.get("priority") or active_lead.get("context_tag") or "STANDARD"

    card_text = get_text(
        "active_booking_card",
        lang,
        lead_id=lead_id,
        service=html.escape(service),
        client_name=html.escape(client_name),
        phone=html.escape(phone),
        comment=html.escape(comment),
        status=status,
        tag=tag,
    )
    self_service_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("btn_cancel_booking", lang),
                    callback_data=f"user_cancel:{lead_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("btn_reschedule", lang),
                    callback_data=f"user_rebook:{lead_id}",
                )
            ],
        ]
    )
    await message.answer(
        text=card_text,
        reply_markup=self_service_keyboard,
    )


@router.callback_query(F.data.startswith("user_cancel:"))
async def process_user_cancel_lead(callback: CallbackQuery) -> None:
    """Handle self-service cancellation of active lead by the client.

    Args:
        callback: Incoming callback query.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        telegram_lang = callback.from_user.language_code if callback.from_user else None
        lang, _ = await resolve_user_locale(user_id, telegram_lang)

        raw_payload = callback.data.split(":", 1)[1] if callback.data else ""
        if not raw_payload.isdigit():
            await callback.answer(get_text("invalid_data", lang), show_alert=True)
            return

        lead_id = int(raw_payload)
        lead = await get_lead_by_id(lead_id)

        if not lead or lead.get("user_id") != user_id:
            await callback.answer(get_text("not_found", lang), show_alert=True)
            return

        await cancel_active_lead(lead_id)
        asyncio.create_task(
            update_sheet_status(
                lead_id=lead_id,
                new_status_key="CANCELLED",
                admin_lang=CURRENT_ADMIN_LANG,
                creds_path=GOOGLE_CREDS_PATH,
                sheet_id=GOOGLE_SHEET_ID,
            )
        )

        logger.info("User %d cancelled active lead #%d via inline button.", user_id, lead_id)
        await callback.answer(get_text("cancel_alert", lang, lead_id=lead_id), show_alert=True)

        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=get_text("booking_cancelled_success", lang, lead_id=lead_id),
                reply_markup=None,
            )
    except Exception as exc:
        logger.exception("Error processing user cancel callback: %s", exc)


@router.callback_query(F.data.startswith("user_rebook:"))
async def process_user_rebook_lead(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel old lead in SQLite and Google Sheets, then re-enter booking flow.

    Args:
        callback: Incoming callback query.
        state: Active FSM context.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        telegram_lang = callback.from_user.language_code if callback.from_user else None
        lang, _ = await resolve_user_locale(user_id, telegram_lang)

        raw_payload = callback.data.split(":", 1)[1] if callback.data else ""
        if not raw_payload.isdigit():
            await callback.answer(get_text("invalid_data", lang), show_alert=True)
            return

        lead_id = int(raw_payload)
        lead = await get_lead_by_id(lead_id)

        if not lead or lead.get("user_id") != user_id:
            await callback.answer(get_text("not_found", lang), show_alert=True)
            return

        await cancel_active_lead(lead_id)
        asyncio.create_task(
            update_sheet_status(
                lead_id=lead_id,
                new_status_key="CANCELLED",
                admin_lang=CURRENT_ADMIN_LANG,
                creds_path=GOOGLE_CREDS_PATH,
                sheet_id=GOOGLE_SHEET_ID,
            )
        )

        logger.info("User %d rebooking: cancelled previous lead #%d.", user_id, lead_id)
        await callback.answer(get_text("rebook_alert", lang, lead_id=lead_id))

        await state.clear()
        if callback.message and isinstance(callback.message, Message):
            await callback.message.delete()
            await callback.message.answer(
                text=get_text("rebook_prompt", lang),
                reply_markup=get_services_keyboard(lang),
            )
        await state.set_state(LeadGenState.waiting_for_service)
    except Exception as exc:
        logger.exception("Error processing user rebook callback: %s", exc)


@router.message(LeadGenState.waiting_for_service, F.text)
async def process_service_selection(message: Message, state: FSMContext) -> None:
    """Process selected service option and prompt for client full name.

    Args:
        message: Incoming message with service choice.
        state: Active FSM context.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    selected_service = message.text.strip() if message.text else ""
    if not selected_service:
        await message.answer(
            text=get_text("select_service_prompt", lang),
            reply_markup=get_services_keyboard(lang),
        )
        return

    await state.update_data(service=selected_service)
    await state.set_state(LeadGenState.waiting_for_name)

    await message.answer(
        text=get_text("prompt_name", lang, service=html.escape(selected_service)),
        reply_markup=get_cancel_keyboard(lang),
    )


@router.message(LeadGenState.waiting_for_name, F.text)
async def process_name_input(message: Message, state: FSMContext) -> None:
    """Process client full name strictly in RAW format and prompt for phone number.

    Args:
        message: Incoming message containing full name.
        state: Active FSM context.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    # Strictly preserve RAW name without transliteration
    client_name = message.text.strip() if message.text else ""
    if len(client_name) < 2 or len(client_name) > 100:
        await message.answer(
            text=get_text("prompt_name_error", lang),
            reply_markup=get_cancel_keyboard(lang),
        )
        return

    await state.update_data(client_name=client_name)
    await state.set_state(LeadGenState.waiting_for_phone)

    await message.answer(
        text=get_text("prompt_phone", lang, name=html.escape(client_name)),
        reply_markup=get_phone_keyboard(lang),
    )


@router.message(LeadGenState.waiting_for_phone, F.contact | F.text)
async def process_phone_input(message: Message, state: FSMContext) -> None:
    """Process phone input strictly in RAW format and advance to context triage.

    Args:
        message: Contact card or phone number string.
        state: Active FSM context.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    lang, _ = await resolve_user_locale(user_id, telegram_lang)

    if message.contact:
        phone_number = message.contact.phone_number
    elif message.text:
        phone_number = message.text.strip()
    else:
        await message.answer(
            text=get_text("prompt_phone_error", lang),
            reply_markup=get_phone_keyboard(lang),
        )
        return

    if not is_valid_phone(phone_number):
        await message.answer(
            text=get_text("prompt_phone_error", lang),
            reply_markup=get_phone_keyboard(lang),
        )
        return

    await state.update_data(phone_number=phone_number)
    await state.set_state(LeadGenState.waiting_for_comment)

    await message.answer(
        text=get_text("prompt_comment", lang),
        reply_markup=get_comment_keyboard(lang),
    )


@router.message(LeadGenState.waiting_for_comment, F.text)
async def process_comment_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Process client commentary (strictly RAW), triage, persist lead, and notify Admin.

    Args:
        message: Message containing task description or skip command.
        state: Active FSM context.
        bot: Bot instance used for administrator dispatch.
    """
    user_id = message.from_user.id if message.from_user else 0
    telegram_lang = message.from_user.language_code if message.from_user else None
    client_lang, _ = await resolve_user_locale(user_id, telegram_lang)

    raw_text = message.text.strip() if message.text else ""
    skip_variants = set(get_button_variants("btn_skip")) | {
        "пропустить",
        "пропустити",
        "skip",
        "/skip",
        "⏭ skip",
        "⏭ пропустить",
        "⏭ пропустити",
    }
    is_skipped = raw_text in skip_variants or raw_text.lower() in skip_variants

    # Strictly preserve RAW commentary without translation or transliteration
    comment_text: Optional[str] = None if is_skipped else raw_text

    # Retrieve collected state data
    data = await state.get_data()
    service = str(data.get("service", "Consultation"))
    client_name = str(data.get("client_name", "Client"))
    phone_number = str(data.get("phone_number", ""))
    username = message.from_user.username if message.from_user else None

    # Context Triage Engine: resolve qualification tier and client localized reply
    triage_result = analyze_lead_context(
        comment_text=comment_text,
        service=service,
        lang=client_lang,
    )
    context_tag = triage_result["context_tag"]
    custom_reply = triage_result["custom_user_reply"]

    # 1. Persist lead into WAL-enabled SQLite database with strictly RAW fields and client_lang
    try:
        lead_id = await save_lead(
            user_id=user_id,
            username=username,
            service=service,
            client_name=client_name,
            phone_number=phone_number,
            comment=comment_text,
            context_tag=context_tag,
            status="NEW",
            client_lang=client_lang,
            language=client_lang,
        )
    except Exception as exc:
        logger.exception("Failed to persist lead for user %d: %s", user_id, exc)
        await message.answer(
            text=get_text("save_error", client_lang),
            reply_markup=get_main_menu_keyboard(client_lang),
        )
        await state.clear()
        return

    # 2. Asynchronous Google Sheets CRM Export via append_lead_row
    lead_dict = {
        "lead_id": lead_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "full_name": client_name,
        "phone": phone_number,
        "service": service,
        "notes": comment_text,
        "priority": context_tag,
        "status": "NEW",
        "username": username or "",
    }
    asyncio.create_task(
        append_lead_row(
            lead_data=lead_dict,
            admin_lang=CURRENT_ADMIN_LANG,
            creds_path=GOOGLE_CREDS_PATH,
            sheet_id=GOOGLE_SHEET_ID,
        )
    )

    # 3. Clear FSM state
    await state.clear()

    # 4. Tailored confirmation summary strictly in client's language
    client_confirmation = get_text(
        "booking_confirmed_card",
        client_lang,
        custom_reply=custom_reply,
        lead_id=lead_id,
        service=html.escape(service),
        client_name=html.escape(client_name),
        phone=html.escape(phone_number),
        comment=html.escape(comment_text) if comment_text else get_text("not_specified", client_lang),
        tag=context_tag,
    )
    await message.answer(
        text=client_confirmation,
        reply_markup=get_main_menu_keyboard(client_lang),
    )

    # 5. Dispatch notification to Administrator strictly formatted in Admin's current language
    admin_lead_data = {
        "id": lead_id,
        "lead_id": lead_id,
        "user_id": user_id,
        "username": username,
        "service": service,
        "full_name": client_name,
        "phone": phone_number,
        "notes": comment_text,
        "priority": context_tag,
        "status": "NEW",
    }
    admin_card_text = format_admin_card(
        lead=admin_lead_data,
        admin_lang=CURRENT_ADMIN_LANG,
    )

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_card_text,
            reply_markup=get_admin_crm_keyboard(
                lead_id, admin_lang=CURRENT_ADMIN_LANG, show_hide_translate=False
            ),
            parse_mode=ParseMode.HTML,
        )
        logger.info(
            "Admin %d notified successfully for lead #%d with tag '%s' in locale '%s'.",
            ADMIN_ID,
            lead_id,
            context_tag,
            CURRENT_ADMIN_LANG,
        )
    except TelegramAPIError as admin_err:
        logger.warning(
            "Could not dispatch notification to admin ID %d: %s.",
            ADMIN_ID,
            admin_err,
        )


@router.callback_query(F.data.startswith("translate_notes:"))
async def process_translate_notes_callback(callback: CallbackQuery) -> None:
    """Handle on-demand translation of raw client commentary into Admin's language.

    Fetches raw notes, translates to CURRENT_ADMIN_LANG, and displays translation block.

    Args:
        callback: Incoming callback query from admin CRM card.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if user_id != ADMIN_ID:
            await callback.answer(get_text("access_denied", "en"), show_alert=True)
            return

        parts = callback.data.split(":") if callback.data else []
        if len(parts) != 2 or not parts[1].isdigit():
            await callback.answer(get_text("invalid_data", CURRENT_ADMIN_LANG), show_alert=True)
            return

        lead_id = int(parts[1])
        lead = await get_lead_by_id(lead_id)
        if not lead:
            await callback.answer(get_text("not_found", CURRENT_ADMIN_LANG), show_alert=True)
            return

        raw_comment = lead.get("notes") if lead.get("notes") is not None else lead.get("comment")
        if not raw_comment or not str(raw_comment).strip():
            translated_text = get_text("crm_translation_empty", CURRENT_ADMIN_LANG)
        else:
            translated_text = await translate_text(str(raw_comment), target_lang=CURRENT_ADMIN_LANG)

        # Determine current status badge text if updated
        lead_status = str(lead.get("status", "NEW"))
        badge_text: Optional[str] = None
        if lead_status != "NEW":
            badge_text = get_text(
                f"crm_btn_{lead_status.lower()}",
                CURRENT_ADMIN_LANG,
            )
            if badge_text == f"crm_btn_{lead_status.lower()}":
                badge_text = lead_status

        updated_card_text = format_admin_card(
            lead=lead,
            admin_lang=CURRENT_ADMIN_LANG,
            badge_text=badge_text,
            translated_notes=translated_text,
        )

        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=updated_card_text,
                reply_markup=get_admin_crm_keyboard(
                    lead_id, admin_lang=CURRENT_ADMIN_LANG, show_hide_translate=True
                ),
                parse_mode=ParseMode.HTML,
            )
        await callback.answer(f"Translated to {CURRENT_ADMIN_LANG.upper()}")
    except Exception as exc:
        logger.exception("Error translating notes on demand: %s", exc)
        await callback.answer("Translation error.", show_alert=True)


@router.callback_query(F.data.startswith("hide_notes:"))
async def process_hide_notes_callback(callback: CallbackQuery) -> None:
    """Hide on-demand translation block and revert button to 'Translate Notes'.

    Args:
        callback: Incoming callback query from admin CRM card.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if user_id != ADMIN_ID:
            await callback.answer(get_text("access_denied", "en"), show_alert=True)
            return

        parts = callback.data.split(":") if callback.data else []
        if len(parts) != 2 or not parts[1].isdigit():
            await callback.answer(get_text("invalid_data", CURRENT_ADMIN_LANG), show_alert=True)
            return

        lead_id = int(parts[1])
        lead = await get_lead_by_id(lead_id)
        if not lead:
            await callback.answer(get_text("not_found", CURRENT_ADMIN_LANG), show_alert=True)
            return

        lead_status = str(lead.get("status", "NEW"))
        badge_text: Optional[str] = None
        if lead_status != "NEW":
            badge_text = get_text(
                f"crm_btn_{lead_status.lower()}",
                CURRENT_ADMIN_LANG,
            )
            if badge_text == f"crm_btn_{lead_status.lower()}":
                badge_text = lead_status

        original_card_text = format_admin_card(
            lead=lead,
            admin_lang=CURRENT_ADMIN_LANG,
            badge_text=badge_text,
            translated_notes=None,
        )

        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=original_card_text,
                reply_markup=get_admin_crm_keyboard(
                    lead_id, admin_lang=CURRENT_ADMIN_LANG, show_hide_translate=False
                ),
                parse_mode=ParseMode.HTML,
            )
        await callback.answer()
    except Exception as exc:
        logger.exception("Error hiding translated notes: %s", exc)
        await callback.answer("Error hiding translation.", show_alert=True)


@router.callback_query(F.data.startswith("admin_status:"))
async def process_admin_status_action(callback: CallbackQuery, bot: Bot) -> None:
    """Handle administrative status changes from micro-CRM inline buttons.

    Updates SQLite, synchronizes status to Google Sheets in-place (in Admin's language),
    updates the manager message with an updated status badge, and sends a push notification
    strictly in the client's saved interface language.

    Args:
        callback: Incoming callback query from admin.
        bot: Bot instance.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if user_id != ADMIN_ID:
            await callback.answer(get_text("access_denied", "en"), show_alert=True)
            return

        parts = callback.data.split(":") if callback.data else []
        if len(parts) != 3:
            await callback.answer(get_text("invalid_data", CURRENT_ADMIN_LANG), show_alert=True)
            return

        lead_id = int(parts[1])
        new_status = parts[2].strip().upper()

        # 1. Update SQLite
        updated = await update_lead_status(lead_id, new_status)
        if not updated:
            await callback.answer("Lead record not found.", show_alert=True)
            return

        # 2. Background Google Sheets status synchronization in Admin's language
        asyncio.create_task(
            update_sheet_status(
                lead_id=lead_id,
                new_status_key=new_status,
                admin_lang=CURRENT_ADMIN_LANG,
                creds_path=GOOGLE_CREDS_PATH,
                sheet_id=GOOGLE_SHEET_ID,
            )
        )

        # 3. Retrieve lead record to access client info and language
        lead = await get_lead_by_id(lead_id)

        # 4. Notify client strictly in their saved interface language
        if lead and lead.get("user_id"):
            client_user_id = int(lead["user_id"])
            saved_lang = await get_user_language(client_user_id)
            client_lang = lead.get("client_lang") or saved_lang or lead.get("language") or "en"

            notice_key_map = {
                "CONFIRMED": "client_status_confirmed",
                "IN_PROGRESS": "client_status_in_progress",
                "REJECTED": "client_status_rejected",
                "CANCELLED": "client_status_cancelled",
            }
            notice_key = notice_key_map.get(new_status)
            if notice_key:
                client_notice = get_text(
                    notice_key,
                    client_lang,
                    lead_id=lead_id,
                    service=html.escape(str(lead.get("service", ""))),
                )
                try:
                    await bot.send_message(
                        chat_id=client_user_id,
                        text=client_notice,
                        parse_mode=ParseMode.HTML,
                    )
                    logger.info(
                        "Dispatched '%s' push notification to client %d in locale '%s'.",
                        new_status,
                        client_user_id,
                        client_lang,
                    )
                except TelegramAPIError as client_err:
                    logger.warning(
                        "Failed to dispatch status notice to client %d: %s",
                        client_user_id,
                        client_err,
                    )

        # 5. Refresh Admin Message with current status badge strictly in Admin's language
        badge_map = {
            "CONFIRMED": get_text("crm_btn_confirm", CURRENT_ADMIN_LANG),
            "IN_PROGRESS": get_text("crm_btn_in_progress", CURRENT_ADMIN_LANG),
            "REJECTED": get_text("crm_btn_reject", CURRENT_ADMIN_LANG),
            "CANCELLED": "❌ CANCELLED",
            "NEW": "🟡 NEW",
        }
        badge_text = badge_map.get(new_status, new_status)
        now_time = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

        if callback.message and isinstance(callback.message, Message) and lead:
            updated_admin_text = format_admin_card(
                lead=lead,
                admin_lang=CURRENT_ADMIN_LANG,
                badge_text=badge_text,
                now_time=now_time,
                translated_notes=None,
            )

            try:
                await callback.message.edit_text(
                    text=updated_admin_text,
                    reply_markup=get_admin_crm_keyboard(
                        lead_id, admin_lang=CURRENT_ADMIN_LANG, show_hide_translate=False
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except TelegramAPIError as edit_err:
                logger.debug("Admin message edit skipped: %s", edit_err)

        await callback.answer(f"Status: #{lead_id} -> {new_status}")
    except Exception as exc:
        logger.exception("Error during admin CRM status update: %s", exc)
        await callback.answer("Error updating status.", show_alert=True)


async def main() -> None:
    """Initialize resources, apply database migrations, and launch polling."""
    global CURRENT_ADMIN_LANG
    logger.info("Initializing LeadGen & Booking Bot...")

    # Initialize SQLite database with WAL mode and self-healing migrations
    await init_db()

    # Load initial administrator language preference
    CURRENT_ADMIN_LANG = await get_admin_language(ADMIN_ID, "en")
    logger.info("Initial administrator language loaded: '%s'", CURRENT_ADMIN_LANG)

    # Trigger background Google Sheets header sync to align with admin language
    asyncio.create_task(
        sync_sheet_headers(
            admin_lang=CURRENT_ADMIN_LANG,
            creds_path=GOOGLE_CREDS_PATH,
            sheet_id=GOOGLE_SHEET_ID,
        )
    )

    # Initialize Bot and Dispatcher with HTML parse mode and in-memory FSM storage
    bot = Bot(
        token=BOT_TOKEN,  # type: ignore[arg-type]
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register admin language synchronization middleware
    admin_middleware = AdminLanguageMiddleware()
    dp.message.middleware(admin_middleware)
    dp.callback_query.middleware(admin_middleware)

    dp.include_router(router)

    logger.info("Bot successfully initialized. Starting long-polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Closing bot session...")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution terminated by user.")
