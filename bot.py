import os
import json
import time
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from google import genai
from knowledge import SALON_KNOWLEDGE


# ============================================================
# НАСТРОЙКИ ДЛЯ RENDER
# ============================================================
# Обязательные переменные окружения:
# TELEGRAM_BOT_TOKEN — токен AI-бота от BotFather
# PUBLIC_URL — публичный URL Render-сервиса, например https://your-service.onrender.com
# GEMINI_API_KEY — ключ Gemini API
#
# Необязательные переменные окружения:
# GEMINI_MODEL — модель Gemini, например gemini-3.5-flash
# OWNER_TELEGRAM_ID — ваш Telegram user_id, чтобы только вы могли смотреть /usage
#
# PORT Render обычно задаёт сам.
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

# Если хотите закрыть /usage от всех, кроме себя:
# 1. Узнайте свой Telegram user_id через @userinfobot
# 2. Добавьте в Render переменную OWNER_TELEGRAM_ID=ваш_id
OWNER_TELEGRAM_ID = os.environ.get("OWNER_TELEGRAM_ID")

# Идентификатор демо-проекта для учёта лимита
CLIENT_ID = "beauty_ai_demo_bot"
DEFAULT_MONTHLY_LIMIT = int(os.environ.get("DEFAULT_MONTHLY_LIMIT", "500"))
USAGE_FILE = "usage_data.json"

gemini_client = None


SYSTEM_PROMPT = """
Ты — вежливый AI-помощник демо-салона красоты в Telegram-боте.

Это демонстрационный бот, а не бот реального салона.
Твоя задача — показать, как AI-бот может отвечать клиентам по базе знаний бизнеса.

Правила:
1. Отвечай только на основе предоставленной базы знаний.
2. Не придумывай цены, услуги, адрес, акции, график, мастеров, контакты и свободные окна.
3. Если информации недостаточно, честно скажи, что данных нет в демо-базе.
4. Не делай вид, что запись реально подключена.
5. Если клиент спрашивает про свободное время, точную запись, индивидуальный подбор или противопоказания — направь к администратору.
6. Не отвечай на темы, не связанные с услугами салона, ценами, записью, подготовкой, графиком и контактами.
7. Не давай медицинских рекомендаций и не заменяй консультацию специалиста.
8. Не выдавай предположения за факты.
9. Пиши коротко, дружелюбно и понятно.
10. Если вопрос касается реального проекта, объясни, что в рабочей версии данные заменяются на информацию конкретного салона.

Формат ответа:
- короткий ответ по сути;
- если данных не хватает, скажи об этом прямо;
- если нужен человек, предложи обратиться к администратору салона;
- не используй фейковые контакты.
"""


# ============================================================
# ХРАНЕНИЕ ЛИМИТОВ
# ============================================================

def get_current_period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def load_usage_data() -> dict:
    if not os.path.exists(USAGE_FILE):
        return {}

    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_usage_data(data: dict) -> None:
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_client_plan(client_id: str, default_limit: int = DEFAULT_MONTHLY_LIMIT) -> dict:
    data = load_usage_data()
    current_period = get_current_period()

    if client_id not in data:
        data[client_id] = {
            "plan_name": f"AI_{default_limit}",
            "monthly_ai_limit": default_limit,
            "ai_requests_used": 0,
            "period": current_period,
        }
        save_usage_data(data)
        return data[client_id]

    client = data[client_id]

    if client.get("period") != current_period:
        client["ai_requests_used"] = 0
        client["period"] = current_period
        save_usage_data(data)

    return client


def ai_limit_reached(client_id: str, default_limit: int = DEFAULT_MONTHLY_LIMIT) -> bool:
    client = ensure_client_plan(client_id, default_limit)
    return client["ai_requests_used"] >= client["monthly_ai_limit"]


def increase_ai_usage(client_id: str, default_limit: int = DEFAULT_MONTHLY_LIMIT) -> None:
    data = load_usage_data()
    current_period = get_current_period()

    if client_id not in data:
        data[client_id] = {
            "plan_name": f"AI_{default_limit}",
            "monthly_ai_limit": default_limit,
            "ai_requests_used": 0,
            "period": current_period,
        }

    client = data[client_id]

    if client.get("period") != current_period:
        client["ai_requests_used"] = 0
        client["period"] = current_period

    client["ai_requests_used"] += 1
    save_usage_data(data)


def get_client_usage_text(client_id: str, default_limit: int = DEFAULT_MONTHLY_LIMIT) -> str:
    client = ensure_client_plan(client_id, default_limit)
    remaining = max(client["monthly_ai_limit"] - client["ai_requests_used"], 0)

    return (
        f"Тариф: {client['plan_name']}\n"
        f"Лимит AI-ответов: {client['monthly_ai_limit']}\n"
        f"Использовано: {client['ai_requests_used']}\n"
        f"Осталось: {remaining}\n"
        f"Период: {client['period']}\n\n"
        "Важно: в демо-боте учёт хранится в локальном файле Render. "
        "Для рабочего клиентского проекта лучше использовать внешнее хранение."
    )


# ============================================================
# GEMINI
# ============================================================

def get_gemini_client():
    global gemini_client

    if gemini_client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("Не задана переменная окружения GEMINI_API_KEY")
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    return gemini_client


def ask_ai(user_question: str) -> str:
    prompt = f"""
{SYSTEM_PROMPT}

База знаний демо-салона:
{SALON_KNOWLEDGE}

Вопрос пользователя:
{user_question}
"""

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    answer = getattr(response, "text", "") or ""
    answer = answer.strip()

    if not answer:
        return (
            "Сейчас не удалось получить корректный AI-ответ. "
            "В рабочем боте в такой ситуации клиенту можно предложить перейти к администратору."
        )

    return answer


def ask_ai_with_retry(user_question: str, max_attempts: int = 3) -> str:
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return ask_ai(user_question)
        except Exception as e:
            last_error = e
            error_text = repr(e)
            print(f"GEMINI ERROR attempt {attempt}: {error_text}")

            temporary_error = (
                "503" in error_text
                or "UNAVAILABLE" in error_text
                or "high demand" in error_text.lower()
                or "timeout" in error_text.lower()
            )

            if temporary_error and attempt < max_attempts:
                time.sleep(2 * attempt)
                continue

            break

    raise last_error


# ============================================================
# ТЕКСТЫ И КНОПКИ
# ============================================================

SCREEN_TEXTS = {
    "start_screen": (
        "Здравствуйте 👋\n\n"
        "Это демо-пример AI-бота для салона красоты.\n\n"
        "Он показывает, как бот может отвечать на вопросы клиента по базе знаний салона: "
        "услуги, цены, подготовка, запись, акции и ограничения.\n\n"
        "Важно: это не реальный салон. В рабочем проекте база знаний, контакты, адрес, цены "
        "и правила записи заменяются на данные конкретного бизнеса.\n\n"
        "Вы можете выбрать раздел ниже или нажать «Задать вопрос» и написать вопрос своими словами."
    ),

    "ask_ai_screen": (
        "Задайте вопрос AI-боту\n\n"
        "Напишите вопрос одним сообщением.\n\n"
        "Примеры:\n"
        "— Сколько стоит маникюр?\n"
        "— Какие есть услуги?\n"
        "— Как подготовиться к процедуре?\n"
        "— Можно ли перенести запись?\n"
        "— Есть ли скидка на первое посещение?\n\n"
        "AI отвечает только по демо-базе знаний и не придумывает данные, которых в ней нет."
    ),

    "prices_screen": (
        "Цены в демо-примере\n\n"
        "Маникюр без покрытия — от 1500 ₽\n"
        "Маникюр с покрытием — от 2200 ₽\n"
        "Педикюр — от 2500 ₽\n"
        "Коррекция бровей — от 900 ₽\n"
        "Окрашивание бровей — от 1200 ₽\n\n"
        "В рабочем проекте сюда добавляется реальный прайс салона.\n\n"
        "Если нужна точная стоимость под конкретную ситуацию, бот должен направить клиента к администратору."
    ),

    "booking_screen": (
        "Запись\n\n"
        "В этом демо-боте запись не подключена.\n\n"
        "В рабочем проекте бот может:\n"
        "— переводить клиента к администратору;\n"
        "— вести в WhatsApp или Telegram;\n"
        "— давать ссылку на YCLIENTS, DIKIDI, Altegio, Taplink или другую систему записи;\n"
        "— помогать клиенту сформулировать запрос перед записью.\n\n"
        "Бот не должен обещать свободные окна, если система записи не подключена."
    ),

    "promos_screen": (
        "Акции в демо-примере\n\n"
        "— скидка 10% на первое посещение;\n"
        "— комплексная скидка при записи на 2 услуги.\n\n"
        "В рабочем проекте акции заменяются на реальные предложения салона.\n\n"
        "AI-бот не должен придумывать скидки или акции, которых нет в базе знаний."
    ),

    "contacts_screen": (
        "Контакты\n\n"
        "Это демо-экран.\n\n"
        "В рабочем проекте здесь будут реальные контакты салона:\n"
        "— адрес;\n"
        "— график;\n"
        "— WhatsApp;\n"
        "— Telegram;\n"
        "— телефон;\n"
        "— ссылка на онлайн-запись;\n"
        "— ссылка на карту или схема прохода.\n\n"
        "В демо-версии реальные контакты не указаны."
    ),

    "admin_screen": (
        "Администратор\n\n"
        "Это демо-экран перехода к администратору.\n\n"
        "В рабочем боте здесь будет реальная ссылка на администратора салона: "
        "WhatsApp, Telegram, телефон, онлайн-запись или CRM.\n\n"
        "К администратору лучше переводить вопросы про:\n"
        "— свободные окна;\n"
        "— точную стоимость;\n"
        "— индивидуальный подбор услуги;\n"
        "— противопоказания;\n"
        "— перенос или отмену записи;\n"
        "— ситуации, которых нет в базе знаний."
    ),

    "limitations_screen": (
        "Ограничения AI-бота\n\n"
        "AI-бот не должен:\n"
        "— придумывать услуги, цены, скидки или контакты;\n"
        "— обещать свободные окна без подключения записи;\n"
        "— заменять администратора полностью;\n"
        "— давать медицинские рекомендации;\n"
        "— отвечать уверенно, если данных нет в базе.\n\n"
        "Правильная логика: AI отвечает на типовые вопросы, а сложные и индивидуальные ситуации передаёт человеку."
    ),
}


SCREEN_BUTTONS = {
    "start_screen": [
        [("Задать вопрос", "ask_ai_screen"), ("Цены", "prices_screen")],
        [("Запись", "booking_screen"), ("Акции", "promos_screen")],
        [("Контакты", "contacts_screen"), ("Администратор", "admin_screen")],
        [("Ограничения AI", "limitations_screen")],
    ],

    "ask_ai_screen": [
        [("Администратор", "admin_screen"), ("В меню", "start_screen")],
    ],

    "prices_screen": [
        [("Задать вопрос", "ask_ai_screen"), ("Запись", "booking_screen")],
        [("Администратор", "admin_screen"), ("В меню", "start_screen")],
    ],

    "booking_screen": [
        [("Администратор", "admin_screen"), ("Задать вопрос", "ask_ai_screen")],
        [("В меню", "start_screen")],
    ],

    "promos_screen": [
        [("Запись", "booking_screen"), ("Администратор", "admin_screen")],
        [("Задать вопрос", "ask_ai_screen"), ("В меню", "start_screen")],
    ],

    "contacts_screen": [
        [("Администратор", "admin_screen"), ("Задать вопрос", "ask_ai_screen")],
        [("В меню", "start_screen")],
    ],

    "admin_screen": [
        [("Задать вопрос", "ask_ai_screen")],
        [("В меню", "start_screen")],
    ],

    "limitations_screen": [
        [("Задать вопрос", "ask_ai_screen")],
        [("В меню", "start_screen")],
    ],
}


BUTTON_TO_SCREEN = {}

for screen_id, rows in SCREEN_BUTTONS.items():
    for row in rows:
        for button_text, target_screen in row:
            BUTTON_TO_SCREEN[button_text] = target_screen


# ============================================================
# КЛАВИАТУРА
# ============================================================

def build_keyboard(screen_id: str) -> ReplyKeyboardMarkup:
    rows = SCREEN_BUTTONS.get(screen_id, SCREEN_BUTTONS["start_screen"])
    keyboard = []

    for row in rows:
        keyboard.append([KeyboardButton(button_text) for button_text, _ in row])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел"
    )


def needs_admin_fallback(text: str) -> bool:
    fallback_markers = [
        "обратиться к администратору",
        "связаться с администратором",
        "написать администратору",
        "уточнить у администратора",
        "лучше уточнить",
        "данных нет",
        "данных недостаточно",
        "нет в демо-базе",
        "нет в базе знаний",
    ]

    lowered = text.lower()
    return any(marker in lowered for marker in fallback_markers)


# ============================================================
# ОБРАБОТЧИКИ
# ============================================================

async def show_screen(
    update: Update,
    screen_id: str,
    context: ContextTypes.DEFAULT_TYPE | None = None,
) -> None:
    if not update.message:
        return

    text = SCREEN_TEXTS.get(screen_id, "Экран пока не найден.")
    keyboard = build_keyboard(screen_id)

    if context is not None:
        context.user_data["awaiting_ai_question"] = (screen_id == "ask_ai_screen")

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_ai_question"] = False
    await show_screen(update, "start_screen", context)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_ai_question"] = False
    await show_screen(update, "start_screen", context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    await update.message.reply_text(
        "Команды:\n"
        "/start — открыть главное меню\n"
        "/menu — открыть главное меню\n"
        "/help — помощь\n"
        "/usage — показать лимит AI-ответов, доступно только владельцу при настройке OWNER_TELEGRAM_ID\n\n"
        "Выберите раздел кнопками ниже или нажмите «Задать вопрос».",
        reply_markup=build_keyboard("start_screen"),
    )


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if OWNER_TELEGRAM_ID:
        current_user_id = str(update.effective_user.id) if update.effective_user else ""

        if current_user_id != OWNER_TELEGRAM_ID:
            await update.message.reply_text(
                "Эта команда доступна только владельцу бота.",
                reply_markup=build_keyboard("start_screen"),
            )
            return

    usage_text = get_client_usage_text(CLIENT_ID, DEFAULT_MONTHLY_LIMIT)
    await update.message.reply_text(
        usage_text,
        reply_markup=build_keyboard("start_screen"),
    )


async def handle_ai_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_question = (update.message.text or "").strip()

    if not user_question:
        await update.message.reply_text(
            "Пожалуйста, напишите вопрос текстом.",
            reply_markup=build_keyboard("ask_ai_screen"),
        )
        return

    if ai_limit_reached(CLIENT_ID, DEFAULT_MONTHLY_LIMIT):
        context.user_data["awaiting_ai_question"] = False
        await update.message.reply_text(
            "Лимит AI-ответов на этот период временно исчерпан.\n\n"
            "В рабочем проекте в такой ситуации можно подключить дополнительный AI-пакет "
            "или оставить клиенту кнопки и переход к администратору.",
            reply_markup=build_keyboard("admin_screen"),
        )
        return

    await update.message.reply_text("Секунду, проверяю информацию...")

    try:
        ai_answer = ask_ai_with_retry(user_question)
    except Exception as e:
        context.user_data["awaiting_ai_question"] = False
        print("FINAL GEMINI ERROR:", repr(e))

        await update.message.reply_text(
            "Сейчас AI-ответ временно недоступен.\n\n"
            "В рабочем боте в такой ситуации клиенту можно предложить перейти к администратору "
            "или попробовать позже.",
            reply_markup=build_keyboard("admin_screen"),
        )
        return

    increase_ai_usage(CLIENT_ID, DEFAULT_MONTHLY_LIMIT)
    context.user_data["awaiting_ai_question"] = False

    if needs_admin_fallback(ai_answer):
        await update.message.reply_text(
            ai_answer,
            reply_markup=build_keyboard("admin_screen"),
        )
        return

    await update.message.reply_text(
        ai_answer,
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("Задать вопрос"), KeyboardButton("Администратор")],
                [KeyboardButton("В меню")],
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие"
        ),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if context.user_data.get("awaiting_ai_question") and text not in BUTTON_TO_SCREEN:
        await handle_ai_question(update, context)
        return

    if text in BUTTON_TO_SCREEN:
        await show_screen(update, BUTTON_TO_SCREEN[text], context)
        return

    await update.message.reply_text(
        "Пожалуйста, используйте кнопки меню ниже или нажмите «Задать вопрос».",
        reply_markup=build_keyboard("start_screen"),
    )


# ============================================================
# ПРОВЕРКА НАСТРОЕК И ЗАПУСК
# ============================================================

def validate_settings() -> None:
    missing = []

    if not TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not PUBLIC_URL:
        missing.append("PUBLIC_URL")

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        raise RuntimeError(
            "Не заданы обязательные переменные окружения: " + ", ".join(missing)
        )


def main() -> None:
    validate_settings()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"Beauty AI Demo Bot is running on Render with model: {GEMINI_MODEL}")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{PUBLIC_URL}/{TOKEN}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()