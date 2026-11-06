"""Trilingual localization module for LeadGen & Booking Bot.

Provides comprehensive trilingual string dictionaries (English, Ukrainian, Russian),
safe fallback retrieval, dynamic inline keyboard generation with Telegram auto-detection,
button variant extractors for aiogram message filters, and Google Sheets UI localization.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES: Tuple[str, ...] = ("en", "uk", "ru")
DEFAULT_LOCALE: str = "en"

SHEET_HEADERS_MAP: Dict[str, List[str]] = {
    "en": [
        "Lead ID",
        "Date",
        "Name",
        "Phone",
        "Service",
        "Notes (RAW)",
        "Priority",
        "Status",
        "Username",
    ],
    "uk": [
        "ID заявки",
        "Дата",
        "Ім'я",
        "Телефон",
        "Послуга",
        "Деталі (RAW)",
        "Пріоритет",
        "Статус",
        "Username",
    ],
    "ru": [
        "ID заявки",
        "Дата",
        "Имя",
        "Телефон",
        "Услуга",
        "Детали (RAW)",
        "Приоритет",
        "Статус",
        "Username",
    ],
}

SHEET_STATUSES_MAP: Dict[str, Dict[str, str]] = {
    "en": {
        "NEW": "NEW",
        "CONFIRMED": "CONFIRMED",
        "IN_PROGRESS": "IN_PROGRESS",
        "REJECTED": "REJECTED",
        "CANCELLED": "CANCELLED",
    },
    "uk": {
        "NEW": "НОВА",
        "CONFIRMED": "ПІДТВЕРДЖЕНО",
        "IN_PROGRESS": "В ОБРОБЦІ",
        "REJECTED": "ВІДХИЛЕНО",
        "CANCELLED": "СКАСОВАНО",
    },
    "ru": {
        "NEW": "НОВАЯ",
        "CONFIRMED": "ПОДТВЕРЖДЕНО",
        "IN_PROGRESS": "В ОБРАБОТКЕ",
        "REJECTED": "ОТКЛОНЕНО",
        "CANCELLED": "ОТМЕНЕНО",
    },
}

SHEET_PRIORITIES_MAP: Dict[str, Dict[str, str]] = {
    "en": {
        "URGENT_VIP": "URGENT_VIP",
        "PRICE_INQUIRY": "PRICE_INQUIRY",
        "LOW_PRIORITY": "LOW_PRIORITY",
        "STANDARD": "STANDARD",
    },
    "uk": {
        "URGENT_VIP": "ТЕРМІНОВО (VIP)",
        "PRICE_INQUIRY": "ЗАПИТ ВАРТОСТІ",
        "LOW_PRIORITY": "НИЗЬКИЙ ПРІОРИТЕТ",
        "STANDARD": "СТАНДАРТНИЙ",
    },
    "ru": {
        "URGENT_VIP": "СРОЧНО (VIP)",
        "PRICE_INQUIRY": "ЗАПРОС СТОИМОСТИ",
        "LOW_PRIORITY": "НИЗКИЙ ПРИОРИТЕТ",
        "STANDARD": "СТАНДАРТНЫЙ",
    },
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # Onboarding & Navigation
        "onboarding_header": "🌐 Choose interface language / Оберіть мову інтерфейсу / Выберите язык интерфейса:",
        "welcome_menu": (
            "👋 Hello, <b>{name}</b>!\n\n"
            "Welcome to <b>{biz_name}</b> booking and consultation service.\n"
            "Please use the menu below to book a consultation, review your active bookings, or adjust language settings."
        ),
        "welcome_services": (
            "👋 Hello, <b>{name}</b>!\n\n"
            "Welcome to <b>{biz_name}</b> booking and consultation service.\n"
            "Please select a service from the list below to get started:"
        ),
        "select_service_prompt": "Please select a service from the list below:",

        # Menu & Action Buttons
        "btn_book": "📅 Book a Consultation",
        "btn_my_bookings": "📋 My Bookings",
        "btn_lang": "🌐 Change Language",
        "btn_cancel": "❌ Cancel",
        "btn_skip": "⏭ Skip",
        "btn_share_contact": "📱 Share Contact",
        "btn_cancel_booking": "❌ Cancel Booking",
        "btn_reschedule": "🔄 Reschedule / Update Info",

        # FSM Booking Prompts
        "prompt_name": (
            "Selected: <b>{service}</b>\n\n"
            "👤 Please enter your <b>Full Name</b> so our specialist knows how to address you:"
        ),
        "prompt_name_error": "⚠️ Please enter a valid name (between 2 and 100 characters):",
        "prompt_phone": (
            "Nice to meet you, <b>{name}</b>!\n\n"
            "📞 Please provide your <b>phone number</b> so our specialist can reach you.\n"
            "You can tap the button below to share your contact or type the number manually:"
        ),
        "prompt_phone_error": (
            "⚠️ Invalid phone number format. Please provide a valid international number (e.g., +1234567890):"
        ),
        "prompt_comment": (
            "📝 <b>Describe your project or task details</b>\n\n"
            "Briefly tell us about your objectives, timeline, or specific questions.\n"
            "This enables our team to prepare accurate estimates and assign the relevant expert.\n\n"
            "<i>If you prefer to skip this step, tap '⏭ Skip' below.</i>"
        ),

        # Placeholders
        "placeholder_service": "Select a service from the list below...",
        "placeholder_name": "Enter your full name...",
        "placeholder_phone": "Tap button or enter phone manually...",
        "placeholder_comment": "Describe your task or tap 'Skip'...",

        # Self-Service & Booking Status
        "operation_cancelled": (
            "🚫 <b>Operation cancelled.</b>\n\n"
            "Whenever you are ready to book a consultation, tap '📅 Book a Consultation' or send /start."
        ),
        "no_active_bookings": (
            "ℹ️ <b>You have no active bookings.</b>\n\n"
            "To submit a new request, tap '📅 Book a Consultation' or send /start."
        ),
        "active_booking_card": (
            "📋 <b>You already have an active booking #{lead_id}!</b>\n\n"
            "• <b>Service:</b> {service}\n"
            "• <b>Client Name:</b> {client_name}\n"
            "• <b>Phone:</b> <code>{phone}</code>\n"
            "• <b>Task Details:</b> {comment}\n"
            "• <b>Status:</b> <code>{status}</code>\n"
            "• <b>Priority:</b> <code>{tag}</code>\n\n"
            "You can cancel your existing booking or reschedule below:"
        ),
        "booking_confirmed_card": (
            "{custom_reply}\n\n"
            "📋 <b>Your Booking Summary:</b>\n"
            "• <b>Booking ID:</b> #{lead_id}\n"
            "• <b>Service:</b> {service}\n"
            "• <b>Name:</b> {client_name}\n"
            "• <b>Phone:</b> <code>{phone}</code>\n"
            "• <b>Task Details:</b> {comment}\n"
            "• <b>Priority:</b> <code>{tag}</code>\n\n"
            "Our team will contact you shortly!"
        ),
        "booking_cancelled_success": (
            "❌ <b>Booking #{lead_id} was successfully cancelled.</b>\n\n"
            "You can submit a new booking at any time via /start."
        ),
        "rebook_prompt": (
            "🔄 <b>Previous booking cancelled.</b>\n\n"
            "Please select a service for your new booking:"
        ),
        "cancel_alert": "Booking #{lead_id} has been cancelled.",
        "rebook_alert": "Previous booking cancelled. Starting new booking.",

        # Context Triage Auto-Replies
        "triage_URGENT_VIP": (
            "⚡️ <b>Priority: High (URGENT VIP)</b>\n"
            "Your request has been registered with the highest priority. An on-duty specialist "
            "has received an urgent notification and will contact you within 15 minutes!"
        ),
        "triage_PRICE_INQUIRY": (
            "💰 <b>Price Inquiry (PRICE INQUIRY)</b>\n"
            "Thank you for your interest in our pricing! We will prepare a preliminary estimate "
            "and commercial offer tailored to your project requirements before calling."
        ),
        "triage_LOW_PRIORITY": (
            "📝 <b>Scheduled Inquiry (LOW PRIORITY)</b>\n"
            "Thank you for reaching out! We have scheduled your request and will contact you "
            "in due course."
        ),
        "triage_STANDARD": (
            "✅ <b>Request Accepted (STANDARD)</b>\n"
            "Thank you for providing the details! Our specialist will reach out during business "
            "hours to discuss the next steps."
        ),

        # Client Push Notifications (CRM Status Updates)
        "client_status_confirmed": (
            "🎉 <b>Your booking #{lead_id} has been confirmed!</b>\n\n"
            "• <b>Service:</b> {service}\n"
            "Our specialist has reserved this slot and will contact you to coordinate meeting details."
        ),
        "client_status_in_progress": (
            "📞 <b>Your booking #{lead_id} is now in progress!</b>\n\n"
            "• <b>Service:</b> {service}\n"
            "An expert has started processing your request and will reach out to you shortly."
        ),
        "client_status_rejected": (
            "ℹ️ <b>Update on your booking #{lead_id}:</b>\n\n"
            "Unfortunately, your request could not be accepted at this time. "
            "Please contact our support team or submit a new inquiry via /start."
        ),
        "client_status_cancelled": (
            "❌ <b>Your booking #{lead_id} has been cancelled.</b>\n\n"
            "You can submit a new booking at any time via /start."
        ),

        # Manager CRM Notifications & Alerts
        "manager_crm_alert": (
            "{alert_prefix} <b>New Consultation Booking!</b>\n\n"
            "<b>ID:</b> #{lead_id}\n"
            "<b>Category:</b> <code>{context_tag}</code>\n"
            "<b>Status:</b> 🟡 <code>NEW</code>\n"
            "<b>Service:</b> {service}\n"
            "<b>Client:</b> {client_name}\n"
            "<b>Phone:</b> <code>{phone}</code>\n"
            "<b>Telegram:</b> {username_display} (ID: <code>{user_id}</code>)\n"
            "<b>Notes:</b> {comment}\n"
        ),
        "manager_crm_status_update": (
            "{alert_prefix} <b>Booking #{lead_id} — {badge_text}</b>\n\n"
            "<b>ID:</b> #{lead_id}\n"
            "<b>Category:</b> <code>{tag}</code>\n"
            "<b>Status:</b> <b>{badge_text}</b> <i>(at {now_time})</i>\n"
            "<b>Service:</b> {service}\n"
            "<b>Client:</b> {client_name}\n"
            "<b>Phone:</b> <code>{phone}</code>\n"
            "<b>Telegram:</b> {uname_disp} (ID: <code>{lead_uid}</code>)\n"
            "<b>Notes:</b> {comment}\n"
        ),
        "crm_btn_confirm": "✅ Confirm",
        "crm_btn_in_progress": "⏳ In Progress",
        "crm_btn_reject": "❌ Reject",
        "crm_btn_translate": "🌐 Translate Notes",
        "crm_btn_hide_translation": "↩️ Hide Translation",
        "crm_translation_header": "🌐 <b>Translation ({lang}):</b>\n<i>{translated_notes}</i>",
        "crm_translation_empty": "<i>No notes provided by client.</i>",

        # General & Errors
        "not_specified": "<i>Not specified</i>",
        "no_comment": "<i>No comment</i>",
        "save_error": "⚠️ An error occurred while saving your request. Please try again with /start.",
        "lang_updated": "Language preference saved.",
        "lang_changed_notice": "🌐 Interface language updated. Please select an option from the menu below:",
        "access_denied": "⛔️ This action is only permitted for the bot administrator.",
        "invalid_data": "Invalid request format.",
        "not_found": "Lead not found or permission denied.",
    },

    "uk": {
        # Onboarding & Navigation
        "onboarding_header": "🌐 Choose interface language / Оберіть мову інтерфейсу / Выберите язык интерфейса:",
        "welcome_menu": (
            "👋 Вітаємо, <b>{name}</b>!\n\n"
            "Ласкаво просимо до сервісу запису та консультацій <b>{biz_name}</b>.\n"
            "Скористайтеся меню нижче, щоб записатися на консультацію, переглянути свої записи або змінити налаштування мови."
        ),
        "welcome_services": (
            "👋 Вітаємо, <b>{name}</b>!\n\n"
            "Ласкаво просимо до сервісу запису та консультацій <b>{biz_name}</b>.\n"
            "Будь ласка, оберіть послугу зі списку нижче, щоб розпочати:"
        ),
        "select_service_prompt": "Будь ласка, оберіть послугу зі списку нижче:",

        # Menu & Action Buttons
        "btn_book": "📅 Записатися на консультацію",
        "btn_my_bookings": "📋 Мої записи",
        "btn_lang": "🌐 Змінити мову",
        "btn_cancel": "❌ Скасувати",
        "btn_skip": "⏭ Пропустити",
        "btn_share_contact": "📱 Поділитися контактом",
        "btn_cancel_booking": "❌ Скасувати запис",
        "btn_reschedule": "🔄 Змінити дані / Перезаписатися",

        # FSM Booking Prompts
        "prompt_name": (
            "Обрано: <b>{service}</b>\n\n"
            "👤 Будь ласка, введіть ваше <b>Ім'я та Прізвище</b>, щоб фахівець знав, як до вас звертатися:"
        ),
        "prompt_name_error": "⚠️ Будь ласка, введіть коректне ім'я (від 2 до 100 символів):",
        "prompt_phone": (
            "Приємно познайомитися, <b>{name}</b>!\n\n"
            "📞 Вкажіть ваш <b>номер телефону</b> для зв'язку з фахівцем.\n"
            "Ви можете надіслати контакт кнопкою нижче або ввести номер вручну:"
        ),
        "prompt_phone_error": (
            "⚠️ Некоректний формат телефону. Вкажіть номер у міжнародному форматі (наприклад, +380501234567):"
        ),
        "prompt_comment": (
            "📝 <b>Опишіть ваше завдання або побажання</b>\n\n"
            "Коротко розкажіть про проект, питання або бажану терміновість.\n"
            "Це допоможе нам підготувати точні розрахунки та призначити профільного експерта.\n\n"
            "<i>Якщо бажаєте пропустити цей крок, натисніть «⏭ Пропустити» нижче.</i>"
        ),

        # Placeholders
        "placeholder_service": "Оберіть послугу із запропонованих нижче...",
        "placeholder_name": "Введіть ваше ім'я...",
        "placeholder_phone": "Натисніть кнопку або введіть номер вручну...",
        "placeholder_comment": "Опишіть завдання або натисніть 'Пропустити'...",

        # Self-Service & Booking Status
        "operation_cancelled": (
            "🚫 <b>Операцію скасовано.</b>\n\n"
            "Коли будете готові записатися на консультацію, натисніть «📅 Записатися на консультацію» або надішліть /start."
        ),
        "no_active_bookings": (
            "ℹ️ <b>У вас немає активних записів.</b>\n\n"
            "Щоб створити нову заявку, натисніть «📅 Записатися на консультацію» або надішліть /start."
        ),
        "active_booking_card": (
            "📋 <b>У вас вже є активний запис #{lead_id}!</b>\n\n"
            "• <b>Послуга:</b> {service}\n"
            "• <b>Ім'я клієнта:</b> {client_name}\n"
            "• <b>Телефон:</b> <code>{phone}</code>\n"
            "• <b>Деталі завдання:</b> {comment}\n"
            "• <b>Статус заявки:</b> <code>{status}</code>\n"
            "• <b>Категорія:</b> <code>{tag}</code>\n\n"
            "Ви можете скасувати поточний запис або перезаписатися:"
        ),
        "booking_confirmed_card": (
            "{custom_reply}\n\n"
            "📋 <b>Деталі вашої заявки:</b>\n"
            "• <b>Номер заявки:</b> #{lead_id}\n"
            "• <b>Послуга:</b> {service}\n"
            "• <b>Ім'я:</b> {client_name}\n"
            "• <b>Телефон:</b> <code>{phone}</code>\n"
            "• <b>Деталі завдання:</b> {comment}\n"
            "• <b>Пріоритет:</b> <code>{tag}</code>\n\n"
            "Ми зв'яжемося з вами найближчим часом!"
        ),
        "booking_cancelled_success": (
            "❌ <b>Запис #{lead_id} було успішно скасовано.</b>\n\n"
            "Ви можете оформити нову заявку в будь-який зручний час через /start."
        ),
        "rebook_prompt": (
            "🔄 <b>Попередній запис скасовано.</b>\n\n"
            "Будь ласка, оберіть послугу для нового запису:"
        ),
        "cancel_alert": "Запис #{lead_id} скасовано.",
        "rebook_alert": "Попередній запис скасовано. Оформляємо нову заявку.",

        # Context Triage Auto-Replies
        "triage_URGENT_VIP": (
            "⚡️ <b>Пріоритет: Високий (URGENT VIP)</b>\n"
            "Вашу заявку зареєстровано з найвищим пріоритетом. Черговий спеціаліст "
            "вже отримав термінове сповіщення та зв'яжеться з вами протягом 15 хвилин!"
        ),
        "triage_PRICE_INQUIRY": (
            "💰 <b>Запит вартості (PRICE INQUIRY)</b>\n"
            "Дякуємо за інтерес до наших тарифів! Ми підготуємо попередній розрахунок "
            "та кошторис під ваші завдання перед дзвінком."
        ),
        "triage_LOW_PRIORITY": (
            "📝 <b>Плановий запит (LOW PRIORITY)</b>\n"
            "Дякуємо за звернення! Ми зберегли ваш запит у графіку та зв'яжемося "
            "з вами в плановому порядку."
        ),
        "triage_STANDARD": (
            "✅ <b>Заявку прийнято (STANDARD)</b>\n"
            "Дякуємо за надану інформацію! Наш спеціаліст зв'яжеться з вами "
            "у найближчий робочий час для уточнення деталей."
        ),

        # Client Push Notifications (CRM Status Updates)
        "client_status_confirmed": (
            "🎉 <b>Ваш запис #{lead_id} підтверджено!</b>\n\n"
            "• <b>Послуга:</b> {service}\n"
            "Наш фахівець зарезервував час і зв'яжеться з вами для узгодження деталей зустрічі."
        ),
        "client_status_in_progress": (
            "📞 <b>Ваш запис #{lead_id} взято в роботу!</b>\n\n"
            "• <b>Послуга:</b> {service}\n"
            "Спеціаліст розпочав обробку вашої заявки та зв'яжеться з вами найближчим часом."
        ),
        "client_status_rejected": (
            "ℹ️ <b>Оновлення щодо вашого запису #{lead_id}:</b>\n\n"
            "На жаль, вашу заявку наразі не може бути прийнято в роботу. "
            "Будь ласка, зверніться до служби підтримки або створіть новий запит через /start."
        ),
        "client_status_cancelled": (
            "❌ <b>Ваш запис #{lead_id} скасовано.</b>\n\n"
            "Ви можете оформити новий запис у будь-який час через /start."
        ),

        # Manager CRM Notifications & Alerts
        "manager_crm_alert": (
            "{alert_prefix} <b>Нова заявка на консультацію!</b>\n\n"
            "<b>ID:</b> #{lead_id}\n"
            "<b>Категорія:</b> <code>{context_tag}</code>\n"
            "<b>Статус:</b> 🟡 <code>НОВА</code>\n"
            "<b>Послуга:</b> {service}\n"
            "<b>Клієнт:</b> {client_name}\n"
            "<b>Телефон:</b> <code>{phone}</code>\n"
            "<b>Telegram:</b> {username_display} (ID: <code>{user_id}</code>)\n"
            "<b>Деталі:</b> {comment}\n"
        ),
        "manager_crm_status_update": (
            "{alert_prefix} <b>Заявка #{lead_id} — {badge_text}</b>\n\n"
            "<b>ID:</b> #{lead_id}\n"
            "<b>Категорія:</b> <code>{tag}</code>\n"
            "<b>Статус:</b> <b>{badge_text}</b> <i>(о {now_time})</i>\n"
            "<b>Послуга:</b> {service}\n"
            "<b>Клієнт:</b> {client_name}\n"
            "<b>Телефон:</b> <code>{phone}</code>\n"
            "<b>Telegram:</b> {uname_disp} (ID: <code>{lead_uid}</code>)\n"
            "<b>Деталі:</b> {comment}\n"
        ),
        "crm_btn_confirm": "✅ Підтвердити",
        "crm_btn_in_progress": "⏳ В обробці",
        "crm_btn_reject": "❌ Відхилити",
        "crm_btn_translate": "🌐 Перекласти деталі",
        "crm_btn_hide_translation": "↩️ Приховати переклад",
        "crm_translation_header": "🌐 <b>Переклад ({lang}):</b>\n<i>{translated_notes}</i>",
        "crm_translation_empty": "<i>Клієнт не надав деталей.</i>",

        # General & Errors
        "not_specified": "<i>Не вказано</i>",
        "no_comment": "<i>Без коментаря</i>",
        "save_error": "⚠️ Сталася помилка під час збереження заявки. Будь ласка, спробуйте ще раз через /start.",
        "lang_updated": "Мову інтерфейсу збережено.",
        "lang_changed_notice": "🌐 Мову інтерфейсу оновлено. Будь ласка, оберіть дію з меню нижче:",
        "access_denied": "⛔️ Дія доступна лише адміністратору бота.",
        "invalid_data": "Некоректний формат даних.",
        "not_found": "Заявку не знайдено або недостатньо прав.",
    },

    "ru": {
        # Onboarding & Navigation
        "onboarding_header": "🌐 Choose interface language / Оберіть мову інтерфейсу / Выберите язык интерфейса:",
        "welcome_menu": (
            "👋 Здравствуйте, <b>{name}</b>!\n\n"
            "Добро пожаловать в сервис записи и консультаций <b>{biz_name}</b>.\n"
            "Используйте меню ниже, чтобы записаться на консультацию, посмотреть активные записи или изменить настройки языка."
        ),
        "welcome_services": (
            "👋 Здравствуйте, <b>{name}</b>!\n\n"
            "Добро пожаловать в сервис записи и консультаций <b>{biz_name}</b>.\n"
            "Пожалуйста, выберите интересующую услугу из списка ниже, чтобы начать:"
        ),
        "select_service_prompt": "Пожалуйста, выберите услугу из списка ниже:",

        # Menu & Action Buttons
        "btn_book": "📅 Записаться на консультацию",
        "btn_my_bookings": "📋 Мои записи",
        "btn_lang": "🌐 Сменить язык",
        "btn_cancel": "❌ Отмена",
        "btn_skip": "⏭ Пропустить",
        "btn_share_contact": "📱 Поделиться контактом",
        "btn_cancel_booking": "❌ Отменить запись",
        "btn_reschedule": "🔄 Изменить данные / Перезаписаться",

        # FSM Booking Prompts
        "prompt_name": (
            "Выбрано: <b>{service}</b>\n\n"
            "👤 Введите ваше <b>Имя и Фамилию</b>, чтобы специалист знал, как к вам обращаться:"
        ),
        "prompt_name_error": "⚠️ Пожалуйста, введите корректное имя (от 2 до 100 символов):",
        "prompt_phone": (
            "Приятно познакомиться, <b>{name}</b>!\n\n"
            "📞 Укажите ваш <b>номер телефона</b> для связи со специалистом.\n"
            "Вы можете отправить контакт кнопкой ниже или ввести номер вручную:"
        ),
        "prompt_phone_error": (
            "⚠️ Некорректный формат телефона. Укажите номер в международном формате (например, +79991234567):"
        ),
        "prompt_comment": (
            "📝 <b>Опишите вашу задачу или пожелания</b>\n\n"
            "Кратко расскажите о проекте, вопросе или желаемой срочности.\n"
            "Это поможет нам заранее подготовить точные расчеты и назначить профильного эксперта.\n\n"
            "<i>Если хотите пропустить этот шаг, нажмите кнопку «⏭ Пропустить» ниже.</i>"
        ),

        # Placeholders
        "placeholder_service": "Выберите услугу из предложенных ниже...",
        "placeholder_name": "Введите ваше полное имя...",
        "placeholder_phone": "Нажмите кнопку или введите номер вручную...",
        "placeholder_comment": "Опишите задачу или нажмите 'Пропустить'...",

        # Self-Service & Booking Status
        "operation_cancelled": (
            "🚫 <b>Операция отменена.</b>\n\n"
            "Когда будете готовы записаться на консультацию, нажмите «📅 Записаться на консультацию» или отправьте /start."
        ),
        "no_active_bookings": (
            "ℹ️ <b>У вас нет активных записей.</b>\n\n"
            "Чтобы оформить новую заявку, нажмите «📅 Записаться на консультацию» или отправьте /start."
        ),
        "active_booking_card": (
            "📋 <b>У вас уже есть активная запись #{lead_id}!</b>\n\n"
            "• <b>Услуга:</b> {service}\n"
            "• <b>Имя клиента:</b> {client_name}\n"
            "• <b>Телефон:</b> <code>{phone}</code>\n"
            "• <b>Детали задачи:</b> {comment}\n"
            "• <b>Статус заявки:</b> <code>{status}</code>\n"
            "• <b>Категория:</b> <code>{tag}</code>\n\n"
            "Вы можете отменить текущую запись или изменить данные для новой:"
        ),
        "booking_confirmed_card": (
            "{custom_reply}\n\n"
            "📋 <b>Детали вашей заявки:</b>\n"
            "• <b>Номер заявки:</b> #{lead_id}\n"
            "• <b>Услуга:</b> {service}\n"
            "• <b>Имя:</b> {client_name}\n"
            "• <b>Телефон:</b> <code>{phone}</code>\n"
            "• <b>Детали задачи:</b> {comment}\n"
            "• <b>Приоритет:</b> <code>{tag}</code>\n\n"
            "Мы свяжемся с вами в самое ближайшее время!"
        ),
        "booking_cancelled_success": (
            "❌ <b>Запись #{lead_id} была успешно отменена.</b>\n\n"
            "Вы можете оформить новую заявку в любое удобное время, отправив /start."
        ),
        "rebook_prompt": (
            "🔄 <b>Предыдущая запись отменена.</b>\n\n"
            "Пожалуйста, выберите интересующую услугу для новой записи:"
        ),
        "cancel_alert": "Запись #{lead_id} успешно отменена.",
        "rebook_alert": "Предыдущая запись отменена. Оформляем новую заявку.",

        # Context Triage Auto-Replies
        "triage_URGENT_VIP": (
            "⚡️ <b>Приоритет: Высокий (URGENT VIP)</b>\n"
            "Ваша заявка зарегистрирована с наивысшим приоритетом. Дежурный специалист "
            "уже получил срочное уведомление и свяжется с вами в течение 15 минут!"
        ),
        "triage_PRICE_INQUIRY": (
            "💰 <b>Запрос стоимости (PRICE INQUIRY)</b>\n"
            "Спасибо за интерес к нашим расценкам! Мы подготовим предварительный расчет "
            "и смету под ваши задачи перед звонком."
        ),
        "triage_LOW_PRIORITY": (
            "📝 <b>Плановый запрос (LOW PRIORITY)</b>\n"
            "Спасибо за обращение! Мы сохранили ваш запрос в графике и свяжемся "
            "с вами в плановом порядке."
        ),
        "triage_STANDARD": (
            "✅ <b>Заявка принята (STANDARD)</b>\n"
            "Спасибо за предоставленную информацию! Наш специалист свяжется "
            "с вами в ближайшее рабочее время для уточнения деталей."
        ),

        # Client Push Notifications (CRM Status Updates)
        "client_status_confirmed": (
            "🎉 <b>Ваша запись #{lead_id} подтверждена!</b>\n\n"
            "• <b>Услуга:</b> {service}\n"
            "Наш специалист зарезервировал время и свяжется с вами для согласования деталей встречи."
        ),
        "client_status_in_progress": (
            "📞 <b>Ваша запись #{lead_id} взята в работу!</b>\n\n"
            "• <b>Услуга:</b> {service}\n"
            "Специалист начал обработку вашей заявки и свяжется с вами в ближайшее время."
        ),
        "client_status_rejected": (
            "ℹ️ <b>Обновление по вашей записи #{lead_id}:</b>\n\n"
            "К сожалению, ваша заявка не может быть принята в работу в данный момент. "
            "Пожалуйста, обратитесь в поддержку или оформите новый запрос через /start."
        ),
        "client_status_cancelled": (
            "❌ <b>Ваша запись #{lead_id} была отменена.</b>\n\n"
            "Вы можете оформить новую заявку в любое время через /start."
        ),

        # Manager CRM Notifications & Alerts
        "manager_crm_alert": (
            "{alert_prefix} <b>Новая заявка на консультацию!</b>\n\n"
            "<b>ID:</b> #{lead_id}\n"
            "<b>Категория:</b> <code>{context_tag}</code>\n"
            "<b>Статус:</b> 🟡 <code>НОВАЯ</code>\n"
            "<b>Услуга:</b> {service}\n"
            "<b>Клиент:</b> {client_name}\n"
            "<b>Телефон:</b> <code>{phone}</code>\n"
            "<b>Telegram:</b> {username_display} (ID: <code>{user_id}</code>)\n"
            "<b>Детали:</b> {comment}\n"
        ),
        "manager_crm_status_update": (
            "{alert_prefix} <b>Заявка #{lead_id} — {badge_text}</b>\n\n"
            "<b>ID:</b> #{lead_id}\n"
            "<b>Категория:</b> <code>{tag}</code>\n"
            "<b>Статус:</b> <b>{badge_text}</b> <i>(в {now_time})</i>\n"
            "<b>Услуга:</b> {service}\n"
            "<b>Клиент:</b> {client_name}\n"
            "<b>Телефон:</b> <code>{phone}</code>\n"
            "<b>Telegram:</b> {uname_disp} (ID: <code>{lead_uid}</code>)\n"
            "<b>Детали:</b> {comment}\n"
        ),
        "crm_btn_confirm": "✅ Подтвердить",
        "crm_btn_in_progress": "⏳ В обработке",
        "crm_btn_reject": "❌ Отклонить",
        "crm_btn_translate": "🌐 Перевести детали",
        "crm_btn_hide_translation": "↩️ Скрыть перевод",
        "crm_translation_header": "🌐 <b>Перевод ({lang}):</b>\n<i>{translated_notes}</i>",
        "crm_translation_empty": "<i>Клиент не указал деталей.</i>",

        # General & Errors
        "not_specified": "<i>Не указано</i>",
        "no_comment": "<i>Без комментария</i>",
        "save_error": "⚠️ Произошла ошибка при сохранении заявки. Пожалуйста, повторите попытку, отправив команду /start.",
        "lang_updated": "Язык интерфейса сохранен.",
        "lang_changed_notice": "🌐 Язык интерфейса обновлен. Пожалуйста, выберите действие из меню ниже:",
        "access_denied": "⛔️ Действие доступно только администратору бота.",
        "invalid_data": "Некорректный формат данных.",
        "not_found": "Заявка не найдена или у вас нет прав на её изменение.",
    },
}


def get_text(key: str, lang: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Retrieve a localized string by key with fallback to English and safe keyword formatting.

    Args:
        key: Translation dictionary key.
        lang: Target ISO language code ('en', 'uk', 'ru'). Defaults to 'en'.
        **kwargs: Substitution variables for string interpolation.

    Returns:
        str: Fully formatted localized string, or key if not found.
    """
    lang_code = lang if lang in TRANSLATIONS else DEFAULT_LOCALE
    lang_dict = TRANSLATIONS.get(lang_code, {})
    template = lang_dict.get(key)

    if template is None:
        template = TRANSLATIONS.get(DEFAULT_LOCALE, {}).get(key, key)

    if not kwargs:
        return template

    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning(
            "Safe formatting fallback triggered for key '%s' (lang=%s): %s",
            key,
            lang,
            exc,
        )
        return template


def get_button_variants(key: str) -> Tuple[str, ...]:
    """Retrieve all localized textual variations of a button label across supported languages.

    Used directly in aiogram message filters (e.g., F.text.in_(get_button_variants('btn_lang'))).

    Args:
        key: Button translation key in TRANSLATIONS dictionary.

    Returns:
        Tuple[str, ...]: Unique collection of button labels across 'en', 'uk', and 'ru'.
    """
    variants: List[str] = []
    for lang in ("en", "uk", "ru"):
        val = TRANSLATIONS.get(lang, {}).get(key)
        if val and val not in variants:
            variants.append(val)
    return tuple(variants)


def detect_locale(telegram_lang: Optional[str]) -> str:
    """Map Telegram client language code to one of the supported locales ('en', 'uk', 'ru').

    Maps 'uk' -> 'uk', 'ru'/'be' -> 'ru', and all others -> 'en'.

    Args:
        telegram_lang: Raw language_code from Telegram User object.

    Returns:
        str: 'uk' for Ukrainian, 'ru' for Russian/Belarusian, else 'en'.
    """
    if not telegram_lang:
        return DEFAULT_LOCALE
    code = telegram_lang.lower().strip()
    if code.startswith("uk"):
        return "uk"
    if code.startswith("ru") or code.startswith("be"):
        return "ru"
    return DEFAULT_LOCALE


def get_language_inline_kb(
    active_lang: str = "en",
    is_auto: bool = False,
    prefix: str = "lang_set",
) -> InlineKeyboardMarkup:
    """Construct the trilingual inline selection keyboard with strict Latin '(Telegram)' auto-labeling.

    Language buttons are '🇬🇧 English', '🇺🇦 Українська', '🇷🇺 Русский' with trailing ' ✅'
    on the active choice when not is_auto. Auto button label is derived strictly from
    active_lang with (Telegram) strictly in Latin:
      - '🔄 Auto (Telegram)' for en
      - '🔄 Автоматично (Telegram)' for uk
      - '🔄 Авто (Telegram)' for ru
    If is_auto is True, prepends '✅ '.

    Args:
        active_lang: Currently active or detected language code ('en', 'uk', 'ru').
        is_auto: Whether the active language is derived from automatic Telegram detection.
        prefix: Callback data prefix ('lang_set' for settings, 'lang_init' for onboarding).

    Returns:
        InlineKeyboardMarkup: Interactive 4-button inline keyboard.
    """
    lang_labels = {
        "en": "🇬🇧 English",
        "uk": "🇺🇦 Українська",
        "ru": "🇷🇺 Русский",
    }
    buttons: List[List[InlineKeyboardButton]] = []

    for code, label in lang_labels.items():
        button_text = f"{label} ✅" if (not is_auto and active_lang == code) else label
        buttons.append(
            [InlineKeyboardButton(text=button_text, callback_data=f"{prefix}:{code}")]
        )

    auto_base_labels = {
        "en": "🔄 Auto (Telegram)",
        "uk": "🔄 Автоматично (Telegram)",
        "ru": "🔄 Авто (Telegram)",
    }
    base_auto = auto_base_labels.get(active_lang, "🔄 Auto (Telegram)")
    auto_text = f"✅ {base_auto}" if is_auto else base_auto

    buttons.append(
        [InlineKeyboardButton(text=auto_text, callback_data=f"{prefix}:auto")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_sheet_headers(lang: str = "en") -> List[str]:
    """Retrieve localized Google Sheets Column A-I headers for Row 1.

    Headers returned: Lead ID, Date, Name, Phone, Service, Notes (RAW), Priority, Status, Username.

    Args:
        lang: Target locale ('en', 'uk', 'ru'). Defaults to 'en'.

    Returns:
        List[str]: 9-element list of localized column header names.
    """
    lang_code = lang if lang in SHEET_HEADERS_MAP else DEFAULT_LOCALE
    return list(SHEET_HEADERS_MAP.get(lang_code, SHEET_HEADERS_MAP[DEFAULT_LOCALE]))


def get_sheet_status(status_key: str, lang: str = "en") -> str:
    """Retrieve localized status string for Google Sheets updates.

    Args:
        status_key: Lifecycle status identifier ('NEW', 'CONFIRMED', 'IN_PROGRESS', 'REJECTED', 'CANCELLED').
        lang: Target administrator locale ('en', 'uk', 'ru').

    Returns:
        str: Localized status text.
    """
    lang_code = lang if lang in SHEET_STATUSES_MAP else DEFAULT_LOCALE
    normalized = status_key.strip().upper()
    return SHEET_STATUSES_MAP.get(lang_code, SHEET_STATUSES_MAP[DEFAULT_LOCALE]).get(
        normalized, normalized
    )


def get_sheet_priority(priority_key: str, lang: str = "en") -> str:
    """Retrieve localized priority tag string for Google Sheets export.

    Args:
        priority_key: Triage tag ('URGENT_VIP', 'PRICE_INQUIRY', 'LOW_PRIORITY', 'STANDARD').
        lang: Target administrator locale ('en', 'uk', 'ru').

    Returns:
        str: Localized priority text.
    """
    lang_code = lang if lang in SHEET_PRIORITIES_MAP else DEFAULT_LOCALE
    normalized = priority_key.strip().upper()
    return SHEET_PRIORITIES_MAP.get(lang_code, SHEET_PRIORITIES_MAP[DEFAULT_LOCALE]).get(
        normalized, normalized
    )
