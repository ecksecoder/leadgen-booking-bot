"""Main entry point for the LeadGen & Booking Telegram Bot.

Implements sequential lead collection using aiogram 3.x FSM, dynamic service catalog
and context triage loaded from 'business_profile.json', anti-duplicate self-service,
and bidirectional CRM synchronization between Telegram and Google Sheets.
"""

import asyncio
import html
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Final, List, Optional, Union

from aiogram import Bot, Dispatcher, F, Router, types
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
)
from dotenv import load_dotenv

from context_triage import analyze_lead_context, load_business_profile
from database import (
    cancel_active_lead,
    delete_booking,
    get_active_lead_by_user,
    get_lead_by_id,
    get_user_bookings,
    init_db,
    save_lead,
    update_lead_status,
)
from sheets_sync import export_lead_to_sheets, update_sheet_lead_status

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

CANCEL_BUTTON_TEXT: Final[str] = "❌ Отмена"
SKIP_BUTTON_TEXT: Final[str] = "⏭ Пропустить"

# Router initialization
router = Router(name="leadgen_router")


class LeadGenState(StatesGroup):
    """FSM states for the sequential lead generation sequence."""

    waiting_for_service = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_comment = State()


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
                "name": "💼 Консультация специалиста",
                "price_hint": "По запросу",
            }
        ]
    return services


def get_services_keyboard() -> ReplyKeyboardMarkup:
    """Build ReplyKeyboardMarkup containing services from business_profile.json.

    Returns:
        ReplyKeyboardMarkup: Keyboard with dynamic service options plus Cancel.
    """
    services = get_configured_services()
    keyboard_buttons = [
        [KeyboardButton(text=str(s.get("name", "Услуга")))]
        for s in services
        if s.get("name")
    ]
    keyboard_buttons.append([KeyboardButton(text=CANCEL_BUTTON_TEXT)])
    return ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выберите услугу из предложенных ниже...",
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Build a standard ReplyKeyboardMarkup containing only the Cancel action.

    Returns:
        ReplyKeyboardMarkup: Keyboard with a single Cancel button.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_BUTTON_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Build ReplyKeyboardMarkup allowing contact card sharing or cancellation.

    Returns:
        ReplyKeyboardMarkup: Keyboard with a contact request button and Cancel button.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
            [KeyboardButton(text=CANCEL_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Нажмите кнопку или введите номер вручную...",
    )


def get_comment_keyboard() -> ReplyKeyboardMarkup:
    """Build ReplyKeyboardMarkup for the context triage step with a Skip button.

    Returns:
        ReplyKeyboardMarkup: Keyboard with Skip and Cancel buttons.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SKIP_BUTTON_TEXT)],
            [KeyboardButton(text=CANCEL_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Опишите задачу или нажмите 'Пропустить'...",
    )


def get_admin_crm_keyboard(lead_id: int) -> InlineKeyboardMarkup:
    """Construct inline micro-CRM keyboard for administrator status management.

    Args:
        lead_id: Primary key ID of the target lead record.

    Returns:
        InlineKeyboardMarkup: Interactive buttons for CONFIRMED, IN_PROGRESS, REJECTED.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"admin_status:{lead_id}:CONFIRMED",
                ),
                InlineKeyboardButton(
                    text="📞 В работе",
                    callback_data=f"admin_status:{lead_id}:IN_PROGRESS",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Спам/Отказ",
                    callback_data=f"admin_status:{lead_id}:REJECTED",
                ),
            ],
        ]
    )


def is_valid_phone(phone: str) -> bool:
    """Validate whether input string conforms to international phone number format.

    Args:
        phone: Raw phone string provided by user.

    Returns:
        bool: True if string contains a valid phone representation, False otherwise.
    """
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone)
    return bool(re.fullmatch(r"^\+?[0-9]{7,15}$", cleaned))


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_BUTTON_TEXT)
async def handle_cancellation(message: Message, state: FSMContext) -> None:
    """Cancel the active lead generation session or manage self-service booking cancellations.

    Args:
        message: Incoming Telegram message.
        state: Active FSM context.
    """
    current_state = await state.get_state()
    if current_state is not None:
        logger.info(
            "User %s (ID: %d) cancelled onboarding at state '%s'.",
            message.from_user.username if message.from_user else "unknown",
            message.from_user.id if message.from_user else 0,
            current_state,
        )
        await state.clear()
        await message.answer(
            "🚫 <b>Операция отменена.</b>\n\n"
            "Когда будете готовы записаться на консультацию, отправьте /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Check for active bookings if cancelled outside active onboarding
    user_id = message.from_user.id if message.from_user else 0
    active_lead = await get_active_lead_by_user(user_id)

    if not active_lead:
        await message.answer(
            "ℹ️ <b>У вас нет активных записей.</b>\n\n"
            "Чтобы оформить новую заявку, отправьте команду /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    lead_id = active_lead["id"]
    service = active_lead.get("service", "Консультация")
    await message.answer(
        f"📋 <b>Ваша текущая запись:</b>\n\n"
        f"<b>Номер:</b> #{lead_id}\n"
        f"<b>Услуга:</b> {html.escape(service)}\n"
        f"<b>Статус:</b> <code>{active_lead.get('status', 'NEW')}</code>\n\n"
        "Вы можете отменить её с помощью кнопки ниже:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить запись",
                        callback_data=f"user_cancel:{lead_id}",
                    )
                ]
            ]
        ),
    )


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    """Handle /start, enforce anti-duplicate self-service checks, or present services.

    Args:
        message: Incoming Telegram message.
        state: Active FSM context.
    """
    await state.clear()

    user_id = message.from_user.id if message.from_user else 0
    user_name = (
        message.from_user.first_name if message.from_user else "Уважаемый клиент"
    )

    logger.info(
        "User %s (ID: %d) initiated /start.",
        message.from_user.username if message.from_user else "unknown",
        user_id,
    )

    # 1. Anti-Duplicate Check: inspect whether an active booking already exists
    active_lead = await get_active_lead_by_user(user_id)
    if active_lead:
        lead_id = active_lead["id"]
        service = active_lead.get("service", "Не указана")
        client_name = active_lead.get("client_name", "Не указано")
        phone = active_lead.get("phone_number", "Не указан")
        comment = active_lead.get("comment") or "—"
        status = active_lead.get("status", "NEW")
        tag = active_lead.get("context_tag") or "STANDARD"

        existing_prompt = (
            f"📋 <b>У вас уже есть активная запись #{lead_id}!</b>\n\n"
            f"• <b>Услуга:</b> {html.escape(service)}\n"
            f"• <b>Имя клиента:</b> {html.escape(client_name)}\n"
            f"• <b>Телефон:</b> <code>{html.escape(phone)}</code>\n"
            f"• <b>Детали задачи:</b> {html.escape(comment)}\n"
            f"• <b>Статус заявки:</b> <code>{status}</code>\n"
            f"• <b>Категория:</b> <code>{tag}</code>\n\n"
            "Вы можете отменить текущую запись или изменить данные для новой:"
        )
        self_service_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить запись",
                        callback_data=f"user_cancel:{lead_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Изменить данные / Перезаписаться",
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

    # 2. Present dynamic services from business_profile.json
    profile = load_business_profile()
    biz_name = profile.get("business_name", "LeadGen & Booking Bot")

    welcome_text = (
        f"👋 Здравствуйте, <b>{html.escape(user_name)}</b>!\n\n"
        f"Добро пожаловать в сервис записи и консультаций <b>{html.escape(biz_name)}</b>.\n"
        "Пожалуйста, выберите интересующую услугу из списка ниже:"
    )

    await message.answer(
        text=welcome_text,
        reply_markup=get_services_keyboard(),
    )
    await state.set_state(LeadGenState.waiting_for_service)


@router.callback_query(F.data.startswith("user_cancel:"))
async def process_user_cancel_lead(callback: CallbackQuery) -> None:
    """Handle self-service cancellation of active lead by the user.

    Cancels the lead record in SQLite and updates Google Sheets in the background.

    Args:
        callback: Incoming callback query.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        raw_payload = callback.data.split(":", 1)[1] if callback.data else ""

        if not raw_payload.isdigit():
            await callback.answer("Некорректный номер записи.", show_alert=True)
            return

        lead_id = int(raw_payload)
        lead = await get_lead_by_id(lead_id)

        if not lead or lead.get("user_id") != user_id:
            await callback.answer(
                "Заявка не найдена или у вас нет прав на её изменение.",
                show_alert=True,
            )
            return

        # Update SQLite and Google Sheets
        await cancel_active_lead(lead_id)
        asyncio.create_task(
            update_sheet_lead_status(
                GOOGLE_CREDS_PATH,
                GOOGLE_SHEET_ID,
                lead_id,
                "CANCELLED",
            )
        )

        logger.info(
            "User %d cancelled active lead #%d via self-service inline button.",
            user_id,
            lead_id,
        )
        await callback.answer(f"Запись #{lead_id} успешно отменена.", show_alert=True)

        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                f"❌ <b>Запись #{lead_id} была успешно отменена.</b>\n\n"
                "Вы можете оформить новую заявку в любое удобное время, отправив /start.",
                reply_markup=None,
            )
    except Exception as exc:
        logger.exception("Error processing user cancel callback: %s", exc)
        await callback.answer(
            "Произошла ошибка при отмене записи. Попробуйте снова.",
            show_alert=True,
        )


@router.callback_query(F.data.startswith("user_rebook:"))
async def process_user_rebook_lead(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel old lead in SQLite and Google Sheets, then restart onboarding.

    Args:
        callback: Incoming callback query.
        state: Active FSM context.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        raw_payload = callback.data.split(":", 1)[1] if callback.data else ""

        if not raw_payload.isdigit():
            await callback.answer("Некорректный номер записи.", show_alert=True)
            return

        lead_id = int(raw_payload)
        lead = await get_lead_by_id(lead_id)

        if not lead or lead.get("user_id") != user_id:
            await callback.answer(
                "Заявка не найдена или у вас нет прав на её изменение.",
                show_alert=True,
            )
            return

        # Cancel previous lead before allowing new booking
        await cancel_active_lead(lead_id)
        asyncio.create_task(
            update_sheet_lead_status(
                GOOGLE_CREDS_PATH,
                GOOGLE_SHEET_ID,
                lead_id,
                "CANCELLED",
            )
        )

        logger.info(
            "User %d rebooking: cancelled previous lead #%d.",
            user_id,
            lead_id,
        )
        await callback.answer(
            f"Предыдущая запись #{lead_id} отменена. Оформляем новую заявку.",
            show_alert=False,
        )

        await state.clear()
        if callback.message and isinstance(callback.message, Message):
            await callback.message.delete()

        prompt_text = (
            "🔄 <b>Предыдущая запись отменена.</b>\n\n"
            "Пожалуйста, выберите интересующую услугу для новой записи:"
        )
        await callback.message.answer(
            text=prompt_text,
            reply_markup=get_services_keyboard(),
        )
        await state.set_state(LeadGenState.waiting_for_service)
    except Exception as exc:
        logger.exception("Error processing user rebook callback: %s", exc)
        await callback.answer(
            "Произошла ошибка при перезаписи. Попробуйте снова.",
            show_alert=True,
        )


@router.message(LeadGenState.waiting_for_service, F.text)
async def process_service_selection(message: Message, state: FSMContext) -> None:
    """Process selected service option and prompt for client's full name.

    Args:
        message: Incoming message with service choice.
        state: Active FSM context.
    """
    selected_service = message.text.strip() if message.text else ""

    if not selected_service:
        await message.answer(
            "Пожалуйста, выберите услугу из списка ниже:",
            reply_markup=get_services_keyboard(),
        )
        return

    await state.update_data(service=selected_service)
    await state.set_state(LeadGenState.waiting_for_name)

    logger.debug(
        "User %d selected service '%s'.",
        message.from_user.id if message.from_user else 0,
        selected_service,
    )

    prompt_name_text = (
        f"Выбрано: <b>{html.escape(selected_service)}</b>\n\n"
        "👤 Введите ваше <b>Имя и Фамилию</b>, чтобы специалист знал, как к вам обращаться:"
    )
    await message.answer(
        text=prompt_name_text,
        reply_markup=get_cancel_keyboard(),
    )


@router.message(LeadGenState.waiting_for_name, F.text)
async def process_name_input(message: Message, state: FSMContext) -> None:
    """Process client's full name and prompt for phone number.

    Args:
        message: Incoming message containing full name.
        state: Active FSM context.
    """
    client_name = message.text.strip() if message.text else ""

    if len(client_name) < 2 or len(client_name) > 100:
        await message.answer(
            "⚠️ Пожалуйста, введите корректное имя (от 2 до 100 символов):",
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(client_name=client_name)
    await state.set_state(LeadGenState.waiting_for_phone)

    logger.debug(
        "User %d provided name '%s'.",
        message.from_user.id if message.from_user else 0,
        client_name,
    )

    prompt_phone_text = (
        f"Приятно познакомиться, <b>{html.escape(client_name)}</b>!\n\n"
        "📞 Укажите ваш <b>номер телефона</b> для связи со специалистом.\n"
        "Вы можете отправить контакт кнопкой ниже или ввести номер вручную:"
    )
    await message.answer(
        text=prompt_phone_text,
        reply_markup=get_phone_keyboard(),
    )


@router.message(LeadGenState.waiting_for_phone, F.contact | F.text)
async def process_phone_input(message: Message, state: FSMContext) -> None:
    """Process phone input and advance to the context triage step.

    Args:
        message: Message carrying either a shared contact card or manual phone string.
        state: Active FSM context.
    """
    if message.contact:
        phone_number = message.contact.phone_number
    elif message.text:
        phone_number = message.text.strip()
    else:
        await message.answer(
            "⚠️ Пожалуйста, укажите корректный номер телефона с помощью кнопки или текста:",
            reply_markup=get_phone_keyboard(),
        )
        return

    if not is_valid_phone(phone_number):
        await message.answer(
            "⚠️ Некорректный формат телефона. Укажите номер в международном формате (например, +79991234567):",
            reply_markup=get_phone_keyboard(),
        )
        return

    await state.update_data(phone_number=phone_number)
    await state.set_state(LeadGenState.waiting_for_comment)

    logger.debug(
        "User %d provided phone number '%s'. Advancing to context triage.",
        message.from_user.id if message.from_user else 0,
        phone_number,
    )

    prompt_comment_text = (
        "📝 <b>Опишите вашу задачу или пожелания</b>\n\n"
        "Кратко расскажите о проекте, вопросе или желаемой срочности.\n"
        "Это поможет нам заранее подготовить точные расчеты и назначить профильного эксперта.\n\n"
        "<i>Если хотите пропустить этот шаг, нажмите кнопку «⏭ Пропустить» ниже.</i>"
    )
    await message.answer(
        text=prompt_comment_text,
        reply_markup=get_comment_keyboard(),
    )


@router.message(LeadGenState.waiting_for_comment, F.text)
async def process_comment_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Process context commentary, execute triage engine, persist lead, and notify admin.

    Args:
        message: Message containing task description or skip command.
        state: Active FSM context.
        bot: Bot instance used for administrator dispatch.
    """
    raw_text = message.text.strip() if message.text else ""

    # Check if client chose to skip commentary
    is_skipped = (
        raw_text == SKIP_BUTTON_TEXT
        or raw_text.lower() in ("пропустить", "skip", "/skip", "⏭ пропустить")
    )
    comment_text: Optional[str] = None if is_skipped else raw_text

    # Retrieve collected state data
    data = await state.get_data()
    service = str(data.get("service", "Консультация"))
    client_name = str(data.get("client_name", "Клиент"))
    phone_number = str(data.get("phone_number", ""))

    user_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None

    # Run Context Triage Engine
    triage_result = analyze_lead_context(comment_text=comment_text, service=service)
    context_tag = triage_result["context_tag"]
    custom_reply = triage_result["custom_user_reply"]
    alert_prefix = triage_result["admin_alert_prefix"]

    # 1. Persist lead into WAL-enabled SQLite database
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
        )
    except Exception as exc:
        logger.exception("Failed to persist lead for user %d: %s", user_id, exc)
        await message.answer(
            "⚠️ Произошла ошибка при сохранении заявки. "
            "Пожалуйста, повторите попытку, отправив команду /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    # 2. Asynchronous Google Sheets CRM Export via asyncio.to_thread
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    row_data = [
        lead_id,
        timestamp_str,
        user_id,
        username or "",
        client_name,
        phone_number,
        service,
        comment_text or "—",
        context_tag,
        "NEW",
    ]
    asyncio.create_task(
        export_lead_to_sheets(
            GOOGLE_CREDS_PATH,
            GOOGLE_SHEET_ID,
            row_data,
        )
    )

    # 3. Clear FSM state
    await state.clear()

    # 4. Tailored confirmation reply to the client
    client_confirmation = (
        f"{custom_reply}\n\n"
        "📋 <b>Детали вашей заявки:</b>\n"
        f"• <b>Номер заявки:</b> #{lead_id}\n"
        f"• <b>Услуга:</b> {html.escape(service)}\n"
        f"• <b>Имя:</b> {html.escape(client_name)}\n"
        f"• <b>Телефон:</b> <code>{html.escape(phone_number)}</code>\n"
        f"• <b>Детали задачи:</b> {html.escape(comment_text) if comment_text else '<i>Не указано</i>'}\n"
        f"• <b>Приоритет:</b> <code>{context_tag}</code>\n\n"
        "Мы свяжемся с вами в самое ближайшее время!"
    )
    await message.answer(
        text=client_confirmation,
        reply_markup=ReplyKeyboardRemove(),
    )

    # 5. Dispatch notification to Administrator with context badge and Micro-CRM keyboard
    username_display = f"@{username}" if username else "Не указан"
    admin_notification = (
        f"{alert_prefix} <b>Новая заявка на консультацию!</b>\n\n"
        f"<b>ID:</b> #{lead_id}\n"
        f"<b>Категория:</b> <code>{context_tag}</code>\n"
        f"<b>Статус:</b> 🟡 <code>NEW</code>\n"
        f"<b>Услуга:</b> {html.escape(service)}\n"
        f"<b>Клиент:</b> {html.escape(client_name)}\n"
        f"<b>Телефон:</b> <code>{html.escape(phone_number)}</code>\n"
        f"<b>Telegram:</b> {username_display} (ID: <code>{user_id}</code>)\n"
        f"<b>Комментарий:</b> {html.escape(comment_text) if comment_text else '<i>Без комментария</i>'}\n"
    )

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_notification,
            reply_markup=get_admin_crm_keyboard(lead_id),
            parse_mode=ParseMode.HTML,
        )
        logger.info(
            "Admin %d notified successfully for lead #%d with tag '%s'.",
            ADMIN_ID,
            lead_id,
            context_tag,
        )
    except TelegramAPIError as admin_err:
        logger.warning(
            "Could not dispatch notification to admin ID %d: %s. "
            "(Ensure the admin has started the bot at least once).",
            ADMIN_ID,
            admin_err,
        )


@router.callback_query(F.data.startswith("admin_status:"))
async def process_admin_status_action(callback: CallbackQuery, bot: Bot) -> None:
    """Handle administrative status changes from micro-CRM inline buttons.

    Updates SQLite, synchronizes status to Google Sheets without creating duplicate
    rows, updates the admin alert message in-place, and notifies the client if confirmed.

    Args:
        callback: Incoming callback query from admin.
        bot: Bot instance.
    """
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if user_id != ADMIN_ID:
            await callback.answer(
                "⛔️ Действие доступно только администратору бота.",
                show_alert=True,
            )
            return

        parts = callback.data.split(":") if callback.data else []
        if len(parts) != 3:
            await callback.answer("Некорректный формат данных.", show_alert=True)
            return

        lead_id = int(parts[1])
        new_status = parts[2].strip().upper()

        # 1. Update SQLite
        updated = await update_lead_status(lead_id, new_status)
        if not updated:
            await callback.answer("Заявка не найдена в базе данных.", show_alert=True)
            return

        # 2. Background Google Sheets status synchronization
        asyncio.create_task(
            update_sheet_lead_status(
                GOOGLE_CREDS_PATH,
                GOOGLE_SHEET_ID,
                lead_id,
                new_status,
            )
        )

        # 3. Retrieve lead record to access client info
        lead = await get_lead_by_id(lead_id)

        # 4. Notify client if CONFIRMED
        if new_status == "CONFIRMED" and lead and lead.get("user_id"):
            client_user_id = int(lead["user_id"])
            client_notice = (
                f"🎉 <b>Ваша запись #{lead_id} подтверждена!</b>\n\n"
                f"• <b>Услуга:</b> {html.escape(str(lead.get('service', '')))}\n"
                "Наш специалист зарезервировал время и свяжется с вами для согласования деталей встречи."
            )
            try:
                await bot.send_message(
                    chat_id=client_user_id,
                    text=client_notice,
                    parse_mode=ParseMode.HTML,
                )
                logger.info(
                    "Sent booking confirmation notification to client %d for lead #%d.",
                    client_user_id,
                    lead_id,
                )
            except TelegramAPIError as client_err:
                logger.warning(
                    "Failed to dispatch confirmation message to client %d: %s",
                    client_user_id,
                    client_err,
                )

        # 5. Refresh Admin Message with current status
        status_badges: Dict[str, str] = {
            "CONFIRMED": "✅ Подтверждена (CONFIRMED)",
            "IN_PROGRESS": "📞 В работе (IN_PROGRESS)",
            "REJECTED": "🗑 Отклонена/Спам (REJECTED)",
            "CANCELLED": "❌ Отменена (CANCELLED)",
            "NEW": "🟡 Новая (NEW)",
        }
        badge_text = status_badges.get(new_status, new_status)
        now_time = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

        if callback.message and isinstance(callback.message, Message) and lead:
            service = str(lead.get("service", "N/A"))
            client_name = str(lead.get("client_name", "N/A"))
            phone = str(lead.get("phone_number", "N/A"))
            comment = lead.get("comment")
            tag = str(lead.get("context_tag", "STANDARD"))
            lead_uid = lead.get("user_id", 0)
            lead_uname = lead.get("username")
            uname_disp = f"@{lead_uname}" if lead_uname else "Не указан"

            triage = analyze_lead_context(comment, service=service)
            alert_prefix = triage.get("admin_alert_prefix", "📋")

            updated_admin_text = (
                f"{alert_prefix} <b>Заявка #{lead_id} — {badge_text}</b>\n\n"
                f"<b>ID:</b> #{lead_id}\n"
                f"<b>Категория:</b> <code>{tag}</code>\n"
                f"<b>Статус:</b> <b>{badge_text}</b> <i>(в {now_time})</i>\n"
                f"<b>Услуга:</b> {html.escape(service)}\n"
                f"<b>Клиент:</b> {html.escape(client_name)}\n"
                f"<b>Телефон:</b> <code>{html.escape(phone)}</code>\n"
                f"<b>Telegram:</b> {uname_disp} (ID: <code>{lead_uid}</code>)\n"
                f"<b>Комментарий:</b> {html.escape(str(comment)) if comment else '<i>Без комментария</i>'}\n"
            )

            try:
                await callback.message.edit_text(
                    text=updated_admin_text,
                    reply_markup=get_admin_crm_keyboard(lead_id),
                    parse_mode=ParseMode.HTML,
                )
            except TelegramAPIError as edit_err:
                logger.debug("Admin message edit skipped: %s", edit_err)

        await callback.answer(f"Статус заявки #{lead_id}: {new_status}")
    except Exception as exc:
        logger.exception("Error during admin CRM status update: %s", exc)
        await callback.answer("Ошибка при обновлении статуса.", show_alert=True)


async def main() -> None:
    """Initialize resources, apply database migrations, and launch polling."""
    logger.info("Initializing LeadGen & Booking Bot...")

    # Initialize SQLite database with WAL mode and self-healing migrations
    await init_db()

    # Initialize Bot and Dispatcher with HTML parse mode and in-memory FSM storage
    bot = Bot(
        token=BOT_TOKEN,  # type: ignore[arg-type]
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Bot successfully initialized. Starting long-polling...")
    try:
        # Drop pending updates to avoid processing obsolete messages on startup
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
