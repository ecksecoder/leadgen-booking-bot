# LeadGen and Booking Telegram Bot (Коммерческая Micro-CRM)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/wal.html)
[![Google Sheets API](https://img.shields.io/badge/Google%20Sheets-API%20v4-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)](https://developers.google.com/sheets/api)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License MIT](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)](LICENSE)

[Read in English](README.md) | [Русский]

---

## Архитектурный обзор

LeadGen and Booking Bot представляет собой асинхронный сервис на платформе Telegram, предназначенный для структурированного сбора лидов, квалификации приоритетов и ведения коммерческих сделок непосредственно внутри мессенджера с точечной двусторонней синхронизацией в Google Таблицы.

```
       КЛИЕНТ В TELEGRAM
              |
              v
     [aiogram 3.x FSM Intake]
     (Последовательный сбор: Услуга -> Имя -> Телефон -> Детали)
              |
              v
   [Context Triage Engine]
   Скоринг и разметка приоритетов по ключевым словам:
   - URGENT_VIP     (Баллы: 100, Приоритет 1: Аварийный SLA 15 минут)
   - PRICE_INQUIRY  (Баллы: 70,  Приоритет 2: Запрос расчета сметы и стоимости)
   - LOW_PRIORITY   (Баллы: 30,  Приоритет 3: Плановое обращение без срочности)
   - STANDARD       (Баллы: 10,  Приоритет 4: Стандартный рабочий регламент)
              |
      +-------+-------------------------------+
      |                                       |
      v                                       v
[Хранилище SQLite WAL]          [Синхронизация Google Sheets]
- Потокобезопасность to_thread()- 9-колоночный структурированный экспорт
- Режим WAL и NORMAL sync       - Точечное in-place обновление строк по Lead ID
- Автоматические миграции       - Привязка языка заголовков и статусов к Admin
      |                                       |
      +-------+-------------------------------+
              |
              v
   [Micro-CRM администратора в Telegram]
   - Уведомления менеджеру на текущем языке клиента Telegram администратора
   - Динамическое отслеживание локали Telegram администратора (en, uk, ru)
   - Управление статусами в один клик (CONFIRMED / IN_PROGRESS / REJECTED)
   - AI-перевод исходных комментариев клиента по запросу в карточках CRM
   - Push-уведомления клиенту строго на сохраненном языке client_lang
```

---

## Функциональные возможности

### 1. Многоязычное бронирование для клиентов (en / uk / ru)
- Трехъязычный клиентский интерфейс с полной поддержкой английского (en / GB), украинского (uk / UA) и русского (ru / RU) языков.
- Строгий онбординг-гейт: При первом выполнении команды `/start` новым пользователем без сохраненного профиля бот отображает интерактивный выбор языка до вывода каталога услуг.
- Автоматическое определение локали: Распознает язык клиента в Telegram с возможностью ручного переключения в любой момент через `/lang` или кнопки меню.
- Маркировка кнопки автоопределения с латинским написанием: Кнопка отображает `Auto (Telegram)`, `Автоматично (Telegram)` или `Авто (Telegram)` со словом `(Telegram)` строго на латинице.

### 2. Независимые CRM-уведомления на языке администратора Telegram
- Изолированный движок локализации: Языковые предпочтения клиентов и менеджеров функционируют полностью независимо.
- Динамическое отслеживание языка администратора: При каждом входящем событии от `ADMIN_ID` (сообщение или callback) система считывает `event.from_user.language_code`. Код `uk` преобразуется в украинский, `ru`/`be` - в русский, а все остальные - в английский.
- При смене языка интерфейса Telegram администратором состояние в памяти и базе данных обновляется мгновенно, а входящие карточки CRM и обновления статусов формируются на актуальном языке администратора.

### 3. Динамическая синхронизация заголовков и статусов Google Таблиц с локалью администратора
- Синхронизация заголовков столбцов A-I в реальном времени: При изменении языка администратора фоновая задача (`sync_sheet_headers`) проверяет строку 1 через `asyncio.to_thread`. Если заголовки строки 1 отличаются от `get_sheet_headers(admin_lang)`, строка 1 обновляется без изменения существующих строк данных.
- Локализованные заголовки для поддерживаемых языков:
  - Английский: `Lead ID`, `Date`, `Name`, `Phone`, `Service`, `Notes (RAW)`, `Priority`, `Status`, `Username`
  - Украинский: `ID заявки`, `Дата`, `Ім'я`, `Телефон`, `Послуга`, `Деталі (RAW)`, `Пріоритет`, `Статус`, `Username`
  - Русский: `ID заявки`, `Дата`, `Имя`, `Телефон`, `Услуга`, `Детали (RAW)`, `Приоритет`, `Статус`, `Username`
- Синхронизация статусов и приоритетов: Значения статусов (`NEW`, `CONFIRMED`, `IN_PROGRESS`, `REJECTED`, `CANCELLED`) и теги приоритета (`URGENT_VIP`, `PRICE_INQUIRY`, `LOW_PRIORITY`, `STANDARD`) локализуются на актуальный язык администратора при добавлении и обновлении.

### 4. AI-перевод исходных заметок клиента по запросу прямо в карточках Telegram CRM
- Сохранение исходного текста по умолчанию: Карточка администратора отображает оригинальный текст комментария клиента для исключения искажений.
- Интерактивная кнопка перевода: В карточку лида встроена кнопка `Translate Notes` (`Перекласти деталі` / `Перевести детали`).
- По нажатию система извлекает исходный комментарий, запрашивает перевод на текущий язык администратора, добавляет блок перевода в сообщение и заменяет кнопку на `Hide Translation` (`Приховати переклад` / `Скрыть перевод`).
- Нажатие `Hide Translation` убирает блок перевода и возвращает исходный вид кнопки.

### 5. Строгое сохранение исходных данных клиента без искажений транслитерацией
- Имя клиента, номер телефона и текст комментария сохраняются строго в исходном (RAW) виде.
- Запрещены любые деструктивные трансформации, принудительная транслитерация или фильтрация символов.
- При смене статуса заявки администратором push-уведомление клиенту отправляется строго на сохраненном языке клиента (`client_lang`).

### 6. Движок контекстной приоритизации и квалификация лидов
- Детерминированный скоринг текста задачи по ключевым словам и регулярным выражениям согласно правилам конфигурации.
- Классификация по четырем эксплуатационным категориям:
  - `URGENT_VIP` (Приоритет 1, Баллы 100): Критические сбои, аварии, жесткие дедлайны. Клиенту отправляется регламент связи за 15 минут.
  - `PRICE_INQUIRY` (Приоритет 2, Баллы 70): Расчет стоимости, тарифов, коммерческих предложений и смет.
  - `LOW_PRIORITY` (Приоритет 3, Баллы 30): Перспективные вопросы, перенос на будущее, отсутствие срочности.
  - `STANDARD` (Приоритет 4, Баллы 10): Стандартные заявки, обрабатываемые в общем рабочем порядке.
- Персонализированные автоответы: Локализованные ответы формируются на языке клиента.

### 7. Точечное in-place обновление строк в Google Таблицах по Lead ID
- Все сетевые вызовы библиотеки `gspread` выполняются в пуле потоков через `asyncio.to_thread()`, исключая блокировку главного цикла событий.
- При изменении статуса в Telegram бот находит строку по `Lead ID` в столбце A и точечно перезаписывает статус в столбце H (столбец 8).
- Исключается дублирование строк и гарантируется целостность таблицы.

### 8. Защита от дублей и функции самообслуживания клиента
- Проверка активных бронирований: При вызове `/start` или кнопки записи бот проверяет наличие активных заявок в статусах `NEW`, `IN_PROGRESS` или `CONFIRMED`.
- Меню управления текущей записью:
  - Отменить запись: Переводит статус лида в `CANCELLED` в SQLite и обновляет столбец H в Google Таблицах.
  - Перезаписаться: Отменяет предыдущую запись и перезапускает сценарий бронирования заново.

---

## Изолированная конфигурация (business_profile.json)

Логика бизнес-профиля отделена от исполняемого кода. Изменение списка услуг, тарифов или ключевых слов приоритизации выполняется через файл `business_profile.json` без необходимости пересборки контейнеров или изменения исходного кода.

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
        "keywords": ["urgent", "asap", "critical", "emergency", "sos", "deadline", "срочно", "терміново"],
        "admin_alert_prefix": "[URGENT_VIP]"
      },
      {
        "tag": "PRICE_INQUIRY",
        "priority": 2,
        "keywords": ["price", "cost", "how much", "quote", "rate", "budget", "цена", "ціна"],
        "admin_alert_prefix": "[PRICE_INQUIRY]"
      },
      {
        "tag": "LOW_PRIORITY",
        "priority": 3,
        "keywords": ["later", "someday", "low priority", "just asking", "не к спеху", "пізніше"],
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

## Стек технологий

| Слой | Технология | Назначение / Роль |
| :--- | :--- | :--- |
| Среда выполнения | Python 3.11+ | Стандартный интерпретатор CPython с циклом событий asyncio |
| Каркас бота | aiogram 3.17+ | Асинхронный фреймворк Telegram Bot API с поддержкой FSM |
| База данных | SQLite 3 | Журналирование WAL, синхронизация NORMAL, busy timeout 5000ms |
| Синхронизация таблиц | gspread 6.2+ | Google Sheets API v4 с авторизацией через Service Account |
| Изоляция данных | Собственный движок | Строгое RAW-хранение данных клиента, независимая локаль админа |
| Контейнеризация | Docker Engine | Многоэтапная сборка от непривилегированного пользователя (UID 10001) |
| Оркестрация | Docker Compose v2 | Управление сервисом, монтирование томов, ротация логов |

---

## Руководство по развертыванию

### Вариант A: Развертывание в Docker Compose

1. Клонировать репозиторий и перейти в корень проекта:
```bash
git clone https://github.com/your-username/leadgen-booking-bot.git
cd leadgen-booking-bot
```

2. Подготовить файл переменных окружения:
```bash
cp .env.example .env
```
Отредактировать `.env`, указав `BOT_TOKEN`, `ADMIN_ID` и параметры таблицы Google Sheets.

3. Разместить файл ключей сервисного аккаунта Google (при использовании таблиц):
Сохранить JSON-файл как `credentials.json` в корневой директории проекта. Предоставить доступ к таблице для почты `client_email`, указанной внутри JSON-ключа.

4. Собрать и запустить контейнер:
```bash
docker compose up -d --build
```

5. Просмотр логов:
```bash
docker compose logs -f
```

6. Остановка сервиса:
```bash
docker compose down
```

### Вариант B: Локальный запуск без контейнеров

1. Создать и активировать виртуальное окружение:
```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Установить зависимости:
```bash
pip install -r requirements.txt
```

3. Настроить параметры в файле `.env`:
```ini
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_01234567
ADMIN_ID=123456789
DB_PATH=leads.db
LOG_LEVEL=INFO
GOOGLE_CREDS_PATH=credentials.json
GOOGLE_SHEET_ID=your_spreadsheet_id_here
```

4. Запустить сервис:
```bash
python bot.py
```

---

## Переменные окружения

| Переменная | Обязательна | По умолчанию | Описание |
| :--- | :--- | :--- | :--- |
| `BOT_TOKEN` | Да | Отсутствует | Токен Telegram Bot API, полученный у @BotFather |
| `ADMIN_ID` | Да | Отсутствует | Числовой Telegram ID администратора для получения уведомлений |
| `DB_PATH` | Нет | `leads.db` | Путь к файлу базы данных SQLite |
| `LOG_LEVEL` | Нет | `INFO` | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `GOOGLE_CREDS_PATH` | Нет | `credentials.json` | Путь к JSON-файлу сервисного аккаунта Google |
| `GOOGLE_SHEET_ID` | Нет | Отсутствует | Идентификатор таблицы из URL Google Sheets |

---

## Тестирование и верификация

Проверка статической компиляции модулей проекта:

```bash
python -m py_compile bot.py context_triage.py database.py sheets_sync.py locales.py
```

Проверка логики приоритизации, базы данных и локализации в среде выполнения:

```bash
python -c "from locales import get_sheet_headers, get_text; from context_triage import analyze_lead_context; print('Headers:', get_sheet_headers('ru')); print('Triage:', analyze_lead_context('Срочный проект', lang='ru'))"
```

---

## Лицензия

Проект распространяется под открытой лицензией [MIT License](LICENSE). Разрешено коммерческое использование, брендирование и доработка.
