# 🚀 LeadGen & Booking Telegram Bot (Commercial Micro-CRM)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/wal.html)
[![Google Sheets](https://img.shields.io/badge/Google%20Sheets-Two--Way%20Sync-34A853?style=for-the-badge&logo=googlesheets&logoColor=white)](https://developers.google.com/sheets/api)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)](LICENSE)

> **Автономный Telegram-бот для захвата, квалификации и бронирования лидов с функционалом Micro-CRM прямо в мессенджере, двусторонней синхронизацией с Google Таблицами и адаптивным движком контекстной сортировки.**

---

## 💼 Бизнес-ценность и возможности

LeadGen & Booking Bot — это готовое Enterprise-решение для сервисного бизнеса, консалтинга, IT-студий, клиник и агентств, закрывающее 100% задач по первичному приему, фильтрации и ведению клиентских заявок без необходимости внедрения тяжелых и дорогостоящих внешних CRM.

```
       КЛИЕНТ В TELEGRAM
             │
             ▼
   [Интерактивный FSM]
   • Выбор услуги из каталога
   • Валидация контактов
   • Ввод деталей / комментариев
             │
             ▼
  [Context Triage Engine]
  ⚡ Авто-скоринг по ключевым словам:
    🔥 URGENT_VIP (высокий приоритет)
    💰 PRICE_INQUIRY (расчет сметы)
    ⏳ LOW_PRIORITY (плановый интерес)
    📋 STANDARD
             │
      ┌──────┴───────────────────────────┐
      ▼                                  ▼
[SQLite WAL Storage]           [Two-Way Google Sheets Sync]
 • Self-Healing миграции        • Запись 10 параметров лида
 • 0% блокировки Event Loop     • In-place обновление статусов
      │                                  │
      └──────┬───────────────────────────┘
             ▼
   [Micro-CRM Администратора]
    • Мгновенный алерт с бейджем приоритета
    • Кнопки смены статуса (CONFIRMED / IN_PROGRESS / REJECTED)
    • Авто-уведомление клиента при подтверждении
```

### Ключевые преимущества для бизнеса:

1. **⚡ Micro-CRM прямо в Telegram для владельца и менеджеров**:
   - При поступлении заявки администратор получает мгновенное структурированное сообщение с кликабельными ссылками на контакт, телефоном и тегом срочности.
   - Управление сделкой в один клик: интерактивные inline-кнопки перевода статуса (`✅ Подтвердить`, `⏳ В работе`, `🚫 Отклонить`).
   - Автоматическая отправка уведомления клиенту в Telegram при подтверждении записи менеджером.

2. **📊 Двусторонняя синхронизация с Google Sheets (Two-Way Sync)**:
   - Лиды мгновенно попадают в Google Таблицу (`Lead ID`, дата, клиент, телефон, услуга, комментарий, тег приоритета, статус).
   - При смене статуса в Telegram бот находит строку по `Lead ID` (колонка A) и выполняет **in-place обновление ячейки** без повторного дублирования строк.

3. **🧠 Context Triage Engine (Интеллектуальная приоритизация)**:
   - Анализ текста обращения на лету по базе бизнес-правил (`business_profile.json`).
   - Автоматическое присвоение меток срочности: `🔥 URGENT_VIP` (аварии, сжатые сроки), `💰 PRICE_INQUIRY` (запросы сметы и цен), `⏳ LOW_PRIORITY` (отложенный интерес) и `📋 STANDARD`.
   - Персонализированный ответ клиенту в зависимости от категории (например, обещание перезвонить за 15 минут для VIP).
   - Расширяемый хук `register_llm_classifier()` для подключения языковых моделей (Gemini, Claude, GPT).

4. **🛡 Защита от дублей и Self-Service бронирование**:
   - Проверка наличия активных броней у пользователя (`NEW`, `IN_PROGRESS`, `CONFIRMED`).
   - Вместо создания бесполезных дубликатов бот показывает текущий статус заявки и предлагает удобные кнопки самообслуживания: `❌ Отменить запись` или `🔄 Перезаписаться`.

5. **🎨 Рескиннинг за 5 минут без изменения кода (`10x Scalability`)**:
   - Все прайс-листы, названия услуг, категории, триггеры скоринга и контакты вынесены в `business_profile.json`.
   - Запуск под новую нишу (стоматология, барбершоп, автосервис, юристы) требует лишь правки одного JSON-файла.

6. **🚀 Максимальная надежность и производительность**:
   - **Zero Event-Loop Blocking**: Все операции с диском (SQLite) и сетью (Google Sheets API) вынесены в фоновые потоки через `asyncio.to_thread()`.
   - **Self-Healing SQLite WAL Storage**: Автоматическая проверка структуры таблицы при старте через `PRAGMA table_info` и бесшовная накатка недостающих колонок без остановки сервиса.
   - Настройка журнала `WAL` (Write-Ahead Logging) с таймаутом ожидания блокировок `busy_timeout=10000ms`.

---

## 🏗 Архитектура проекта

```
LeadGen & Booking Bot/
├── bot.py                    # Главный цикл Aiogram 3.x, FSM, обработчики Micro-CRM
├── context_triage.py         # Движок контекстной классификации и скоринга лидов
├── database.py               # SQLite WAL хранилище, пулы, self-healing миграции
├── sheets_sync.py            # Потокобезопасная интеграция с Google Sheets API
├── business_profile.json     # Бизнес-конфигурация (услуги, прайс, правила триажа)
├── requirements.txt          # Зависимости проекта
├── Dockerfile                # Production multi-stage Docker образ (non-root botuser)
├── docker-compose.yml        # Оркестрация контейнера, volumes и log-rotation
├── .env.example              # Шаблон переменных окружения
└── .gitignore                # Жесткая изоляция секретов, БД и кэша
```

### Стек технологий:
- **Core**: Python 3.11+, Aiogram 3.17 (Asyncio FSM Framework).
- **База данных**: SQLite 3 в режиме `PRAGMA journal_mode=WAL` и `synchronous=NORMAL`.
- **Интеграция**: `gspread` (Google Sheets API v4 OAuth2/Service Account).
- **Контейнеризация**: Docker Engine, Docker Compose v2.
- **Безопасность**: Запуск от непривилегированного пользователя `botuser` (UID: 10001), изоляция секретов через read-only volumes.

---

## 🚀 Быстрый старт через Docker (Рекомендуемый)

Развертывание в production занимает менее 2 минут благодаря подготовленному образу.

### 1. Клонирование и переход в директорию
```bash
git clone https://github.com/your-username/leadgen-booking-bot.git
cd leadgen-booking-bot
```

### 2. Подготовка конфигурации окружения
Создайте файл `.env` на основе шаблона:
```bash
cp .env.example .env
```
Заполните обязательные параметры в `.env`:
```ini
# Токен бота из @BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_01234567

# Telegram ID администратора для получения алертов и управления CRM
ADMIN_ID=123456789

# Путь к SQLite БД внутри контейнера (рекомендуется оставить по умолчанию)
DB_PATH=/app/leads.db

# Уровень логирования: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# (Опционально) Google Sheets интеграция
GOOGLE_CREDS_PATH=credentials.json
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
```

### 3. Настройка Google Sheets (Опционально)
Если вам нужна синхронизация с Google Таблицами:
1. Создайте сервисный аккаунт в [Google Cloud Console](https://console.cloud.google.com/) и включите **Google Sheets API**.
2. Скачайте JSON-ключ и сохраните его в корне проекта под именем `credentials.json`.
3. Откройте доступ к вашей целевой Google Таблице на редактирование для email-адреса сервисного аккаунта (указан в `client_email` в `credentials.json`).
4. Вставьте ID таблицы в переменную `GOOGLE_SHEET_ID` в `.env`.

> [!NOTE]
> Если Google Sheets пока не требуются, бот запустится в штатном автономном режиме, сохраняя все лиды в SQLite.

### 4. Запуск контейнера
```bash
docker compose up -d --build
```

Просмотр логов:
```bash
docker compose logs -f
```

Остановка сервиса:
```bash
docker compose down
```

---

## 💻 Локальный запуск (без Docker)

Если вы разрабатываете или тестируете бота локально:

```bash
# 1. Создание и активация виртуального окружения
python -m venv .venv

# Для Linux/macOS:
source .venv/bin/activate
# Для Windows:
.venv\Scripts\activate

# 2. Установка зависимостей
pip install -r requirements.txt

# 3. Запуск бота
python bot.py
```

---

## ⚙️ Кастомизация под ваш бизнес (`business_profile.json`)

Чтобы изменить сферу деятельности бота, просто отредактируйте `business_profile.json`. Изменения подхватываются на лету без пересборки Docker-образа благодаря монтированию volume.

```json
{
  "business_name": "TechPro Solutions",
  "currency": "USD",
  "support_contact": "@techpro_support",
  "services": [
    {
      "id": "business_automation",
      "name": "💼 Автоматизация бизнес-процессов",
      "price_hint": "От $500",
      "description": "Сквозная автоматизация CRM, воронок и аналитики."
    },
    {
      "id": "telegram_bot",
      "name": "🤖 Разработка Telegram-ботов",
      "price_hint": "От $350",
      "description": "High-load AI и LeadGen боты с платежами и CRM."
    }
  ],
  "context_triage": {
    "rules": [
      {
        "tag": "URGENT_VIP",
        "priority": 1,
        "keywords": ["срочно", "urgent", "asap", "горит", "авария", "vip", "не работает"],
        "admin_alert_prefix": "🔥 URGENT_VIP",
        "custom_user_reply": "⚡️ <b>Приоритет: Высокий (URGENT VIP)</b>\nДежурный специалист свяжется с вами в течение 15 минут!"
      }
    ],
    "default": {
      "tag": "STANDARD",
      "admin_alert_prefix": "📋 STANDARD",
      "custom_user_reply": "✅ <b>Заявка принята</b>\nМы свяжемся с вами в рабочее время."
    }
  }
}
```

---

## 🔒 Безопасность и Production Best Practices

- **Защита секретов**: `.env`, приватные ключи `credentials.json` и файлы БД `*.db` строго изолированы в `.gitignore`.
- **Read-Only Credentials**: Сервисный ключ Google монтируется в Docker с флагом `:ro` (read-only), исключая риск перезаписи или модификации из контейнера.
- **Unprivileged Non-Root Execution**: Контейнер работает под пользователем `botuser` (UID: 10001) без прав root.
- **Защита дискового пространства**: Настроена автоматическая ротация Docker-логов `json-file` (максимум 3 файла по 10 МБ).
- **WAL Concurrency**: SQLite защищен от состояния гонки и блокировок `database is locked` при одновременных запросах клиентов.

---

## 📄 Лицензия

Проект распространяется под лицензией [MIT](LICENSE). Подходит для коммерческого использования и кастомизации под клиентские проекты.
