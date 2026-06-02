import os
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

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
Ты — вежливый AI-помощник салона красоты в Telegram-боте.

Твои правила:
1. Отвечай только на основе предоставленной информации о салоне.
2. Не придумывай цены, услуги, адрес, акции, график, мастеров и свободные окна.
3. Если информации недостаточно, честно скажи об этом и предложи обратиться к администратору.
4. Пиши коротко, дружелюбно и понятно.
5. Не отвечай на темы, не связанные с услугами салона, ценами, записью, подготовкой, графиком, адресом и контактами.
6. Если вопрос требует индивидуальной консультации, диагностики, подтверждения цены или свободного времени, направь клиента к администратору.
7. Не выдавай предположения за факты.
8. Если вопрос медицинский, спорный или явно вне базы знаний — не делай выводов и направляй к администратору.

Формат ответа:
- короткий ответ по сути;
- если нужно, 1 короткое уточнение;
- если данных недостаточно, предложи связаться с администратором.
"""


def ask_ai(user_question: str) -> str:
    prompt = f"""
{SYSTEM_PROMPT}

Информация о салоне:
{SALON_KNOWLEDGE}

Вопрос клиента:
{user_question}
"""

    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )

    answer = getattr(response, "text", "") or ""
    answer = answer.strip()

    if not answer:
        return (
            "Сейчас мне не удалось корректно ответить на вопрос. "
            "Пожалуйста, свяжитесь с администратором: @your_admin_username"
        )

    return answer


SCREEN_TEXTS = {
    "start_screen": (
        "Здравствуйте 👋\n"
        "Добро пожаловать в Beauty AI Bot.\n\n"
        "Я могу:\n"
        "— ответить на ваш вопрос по услугам салона\n"
        "— показать цены\n"
        "— подсказать, как записаться\n"
        "— показать акции и контакты\n\n"
        "Выберите действие ниже или задайте вопрос через AI."
    ),
    "ask_ai_screen": (
        "Напишите ваш вопрос одним сообщением.\n\n"
        "Например:\n"
        "— Сколько стоит маникюр?\n"
        "— Какой у вас график?\n"
        "— Как подготовиться к процедуре?\n"
        "— Можно ли перенести запись?"
    ),
    "prices_screen": (
        "Цены\n\n"
        "Маникюр — от 1500 ₽\n"
        "Маникюр с покрытием — от 2200 ₽\n"
        "Педикюр — от 2500 ₽\n"
        "Брови — от 900 ₽\n\n"
        "Если нужен точный подбор услуги, можно задать вопрос через AI или написать администратору."
    ),
    "booking_screen": (
        "Как записаться\n\n"
        "1. Вы можете задать вопрос через AI\n"
        "2. Или сразу написать администратору\n"
        "3. Если нужен перенос / отмена / подбор времени — лучше писать администратору напрямую"
    ),
    "promos_screen": (
        "Акции\n\n"
        "— скидка 10% на первое посещение\n"
        "— комплексная скидка при записи на 2 услуги\n\n"
        "Актуальные условия лучше уточнить у администратора."
    ),
    "contacts_screen": (
        "Контакты\n\n"
        "Адрес: г. Москва, ул. Примерная, д. 10\n"
        "График: ежедневно с 10:00 до 21:00\n"
        "Telegram: @your_admin_username\n"
        "Телефон: +7 900 000-00-00"
    ),
    "admin_screen": (
        "Связаться с администратором:\n\n"
        "Telegram: @your_admin_username\n"
        "Телефон: +7 900 000-00-00\n\n"
        "Если вопрос индивидуальный или нужен подбор времени, лучше написать администратору."
    ),
}

SCREEN_BUTTONS = {
    "start_screen": [
        [("Задать вопрос", "ask_ai_screen"), ("Цены", "prices_screen")],
        [("Записаться", "booking_screen"), ("Акции", "promos_screen")],
        [("Контакты", "contacts_screen"), ("Администратор", "admin_screen")],
    ],

    "ask_ai_screen": [
        [("Администратор", "admin_screen"), ("В меню", "start_screen")],
    ],

    "prices_screen": [
        [("Задать вопрос", "ask_ai_screen"), ("Записаться", "booking_screen")],
        [("Администратор", "admin_screen"), ("В меню", "start_screen")],
    ],

    "booking_screen": [
        [("Администратор", "admin_screen"), ("Задать вопрос", "ask_ai_screen")],
        [("В меню", "start_screen")],
    ],

    "promos_screen": [
        [("Записаться", "booking_screen"), ("Администратор", "admin_screen")],
        [("В меню", "start_screen")],
    ],

    "contacts_screen": [
        [("Администратор", "admin_screen"), ("Задать вопрос", "ask_ai_screen")],
        [("В меню", "start_screen")],
    ],

    "admin_screen": [
        [("В меню", "start_screen")],
    ],
}

BUTTON_TO_SCREEN = {}
for screen_id, rows in SCREEN_BUTTONS.items():
    for row in rows:
        for button_text, target_screen in row:
            BUTTON_TO_SCREEN[button_text] = target_screen


def build_keyboard(screen_id: str) -> ReplyKeyboardMarkup:
    rows = SCREEN_BUTTONS.get(screen_id, [])
    keyboard = []
    for row in rows:
        keyboard.append([KeyboardButton(button_text) for button_text, _ in row])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def needs_admin_fallback(text: str) -> bool:
    fallback_markers = [
        "обратиться к администратору",
        "связаться с администратором",
        "уточнить у администратора",
        "лучше уточнить",
        "недостаточно информации",
    ]
    lowered = text.lower()
    return any(marker in lowered for marker in fallback_markers)


async def show_screen(
    update: Update,
    screen_id: str,
    context: ContextTypes.DEFAULT_TYPE | None = None,
) -> None:
    text = SCREEN_TEXTS.get(screen_id, "Экран пока не найден.")
    keyboard = build_keyboard(screen_id)

    if context is not None:
        context.user_data["awaiting_ai_question"] = (screen_id == "ask_ai_screen")

    await update.message.reply_text(text, reply_markup=keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_ai_question"] = False
    await show_screen(update, "start_screen", context)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_ai_question"] = False
    await show_screen(update, "start_screen", context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Команды:\n"
        "/start — открыть главное меню\n"
        "/menu — открыть главное меню\n"
        "/help — помощь",
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

    await update.message.reply_text("Секунду, думаю над ответом...")

    try:
        ai_answer = ask_ai(user_question)
    except Exception as e:
        context.user_data["awaiting_ai_question"] = False
        print("GEMINI ERROR:", repr(e))
        await update.message.reply_text(
            "Сейчас не удалось обработать вопрос через AI.\n"
            "Пожалуйста, свяжитесь с администратором: @your_admin_username",
            reply_markup=build_keyboard("admin_screen"),
        )
        return

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
        ),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    if context.user_data.get("awaiting_ai_question") and text not in BUTTON_TO_SCREEN:
        await handle_ai_question(update, context)
        return

    if text in BUTTON_TO_SCREEN:
        await show_screen(update, BUTTON_TO_SCREEN[text], context)
        return

    await update.message.reply_text(
        "Пожалуйста, используйте кнопки меню ниже.",
        reply_markup=build_keyboard("start_screen"),
    )


def main() -> None:
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Minimal AI-first Beauty Bot is running on Render...")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{PUBLIC_URL}/{TOKEN}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()