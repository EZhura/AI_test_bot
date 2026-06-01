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
        "Добро пожаловать!\n\n"
        "Я помогу вам быстро узнать основную информацию:\n"
        "— услуги\n"
        "— цены\n"
        "— как записаться\n"
        "— частые вопросы\n"
        "— контакты\n"
        "— AI-ответы на свободные вопросы\n\n"
        "Выберите нужный раздел ниже."
    ),
    "services_screen": "Выберите интересующий вас раздел услуг.",
    "prices_screen": "Здесь вы можете посмотреть цены и акции.",
    "booking_screen": "Здесь собрана информация о записи.",
    "faq_screen": "Частые вопросы клиентов.",
    "contacts_screen": "Контакты и информация о нас.",
    "admin_screen": (
        "Связаться с администратором:\n\n"
        "Telegram: @your_admin_username\n"
        "Телефон: +7 900 000-00-00\n\n"
        "Можете написать администратору прямо сейчас."
    ),
    "ask_ai_screen": (
        "Напишите ваш вопрос одним сообщением.\n\n"
        "Я постараюсь помочь по информации о салоне.\n"
        "Если вопрос требует уточнения, я предложу связаться с администратором."
    ),

    # УСЛУГИ
    "service_manicure": (
        "Маникюр\n\n"
        "Мы предлагаем:\n"
        "— классический маникюр\n"
        "— аппаратный маникюр\n"
        "— маникюр с покрытием\n\n"
        "Если хотите, дальше можете посмотреть цены или перейти к записи."
    ),
    "service_pedicure": (
        "Педикюр\n\n"
        "Мы предлагаем:\n"
        "— классический педикюр\n"
        "— аппаратный педикюр\n"
        "— педикюр с покрытием\n\n"
        "Если хотите, дальше можете посмотреть цены или перейти к записи."
    ),
    "service_brows": (
        "Брови\n\n"
        "Мы предлагаем:\n"
        "— коррекцию бровей\n"
        "— окрашивание\n"
        "— комплекс коррекция + окрашивание\n\n"
        "Если хотите, дальше можете посмотреть цены или перейти к записи."
    ),

    # ЦЕНЫ
    "price_list": (
        "Прайс\n\n"
        "Маникюр — от 1500 ₽\n"
        "Педикюр — от 2000 ₽\n"
        "Брови — от 900 ₽\n\n"
        "Точная стоимость зависит от выбранной услуги и объёма работы."
    ),
    "price_promos": (
        "Акции\n\n"
        "Сейчас действуют:\n"
        "— скидка 10% на первое посещение\n"
        "— комплексная скидка при записи на 2 услуги\n\n"
        "Актуальные предложения лучше уточнять у администратора."
    ),

    # ЗАПИСЬ
    "booking_how": (
        "Как проходит запись\n\n"
        "1. Вы выбираете интересующую услугу\n"
        "2. Пишете администратору\n"
        "3. Уточняете удобную дату и время\n"
        "4. Получаете подтверждение записи"
    ),
    "booking_what_write": (
        "Что написать администратору\n\n"
        "Пример сообщения:\n\n"
        "Здравствуйте. Хочу записаться на маникюр.\n"
        "Удобно на этой неделе во второй половине дня.\n"
        "Подскажите, пожалуйста, какие есть свободные окна?"
    ),

    # FAQ
    "faq_duration": (
        "Сколько длится процедура\n\n"
        "Обычно:\n"
        "— маникюр: 1–2 часа\n"
        "— педикюр: 1.5–2.5 часа\n"
        "— брови: 30–60 минут\n\n"
        "Точное время зависит от конкретной услуги."
    ),
    "faq_prepare": (
        "Как подготовиться\n\n"
        "Обычно специальная подготовка не нужна.\n"
        "Если есть особенности или ограничения, лучше заранее написать администратору."
    ),
    "faq_reschedule": (
        "Можно ли перенести запись\n\n"
        "Да, перенос возможен.\n"
        "Желательно предупредить администратора заранее, чтобы подобрать новое удобное время."
    ),

    # КОНТАКТЫ
    "contacts_address": (
        "Адрес\n\n"
        "г. Москва\n"
        "ул. Примерная, д. 10\n\n"
        "Точный адрес и схему прохода можно уточнить у администратора."
    ),
    "contacts_schedule": (
        "График работы\n\n"
        "Ежедневно\n"
        "с 10:00 до 21:00"
    ),
    "contacts_all": (
        "Контакты\n\n"
        "Telegram: @your_admin_username\n"
        "Телефон: +7 900 000-00-00\n"
        "WhatsApp: +7 900 000-00-00"
    ),
}

SCREEN_BUTTONS = {
    "start_screen": [
        [("Услуги", "services_screen"), ("Цены", "prices_screen")],
        [("Как записаться", "booking_screen"), ("FAQ", "faq_screen")],
        [("Контакты", "contacts_screen"), ("Задать вопрос", "ask_ai_screen")],
        [("Администратор", "admin_screen")],
    ],

    "services_screen": [
        [("Маникюр", "service_manicure"), ("Педикюр", "service_pedicure")],
        [("Брови", "service_brows")],
        [("В меню", "start_screen")],
    ],

    "prices_screen": [
        [("Прайс", "price_list"), ("Акции", "price_promos")],
        [("В меню", "start_screen")],
    ],

    "booking_screen": [
        [("Как проходит запись", "booking_how")],
        [("Что написать администратору", "booking_what_write")],
        [("В меню", "start_screen")],
    ],

    "faq_screen": [
        [("Сколько длится процедура", "faq_duration")],
        [("Как подготовиться", "faq_prepare")],
        [("Можно ли перенести запись", "faq_reschedule")],
        [("В меню", "start_screen")],
    ],

    "contacts_screen": [
        [("Адрес", "contacts_address"), ("График", "contacts_schedule")],
        [("Все контакты", "contacts_all")],
        [("В меню", "start_screen")],
    ],

    "admin_screen": [
        [("В меню", "start_screen")],
    ],

    "ask_ai_screen": [
        [("Администратор", "admin_screen"), ("В меню", "start_screen")],
    ],

    "service_manicure": [
        [("Цены", "prices_screen"), ("Как записаться", "booking_screen")],
        [("Назад к услугам", "services_screen"), ("В меню", "start_screen")],
    ],
    "service_pedicure": [
        [("Цены", "prices_screen"), ("Как записаться", "booking_screen")],
        [("Назад к услугам", "services_screen"), ("В меню", "start_screen")],
    ],
    "service_brows": [
        [("Цены", "prices_screen"), ("Как записаться", "booking_screen")],
        [("Назад к услугам", "services_screen"), ("В меню", "start_screen")],
    ],

    "price_list": [
        [("Как записаться", "booking_screen")],
        [("Назад к ценам", "prices_screen"), ("В меню", "start_screen")],
    ],
    "price_promos": [
        [("Как записаться", "booking_screen")],
        [("Назад к ценам", "prices_screen"), ("В меню", "start_screen")],
    ],

    "booking_how": [
        [("Написать администратору", "admin_screen")],
        [("Назад к записи", "booking_screen"), ("В меню", "start_screen")],
    ],
    "booking_what_write": [
        [("Написать администратору", "admin_screen")],
        [("Назад к записи", "booking_screen"), ("В меню", "start_screen")],
    ],

    "faq_duration": [
        [("Назад к FAQ", "faq_screen"), ("В меню", "start_screen")],
    ],
    "faq_prepare": [
        [("Назад к FAQ", "faq_screen"), ("В меню", "start_screen")],
    ],
    "faq_reschedule": [
        [("Назад к FAQ", "faq_screen"), ("В меню", "start_screen")],
    ],

    "contacts_address": [
        [("Назад к контактам", "contacts_screen"), ("В меню", "start_screen")],
    ],
    "contacts_schedule": [
        [("Назад к контактам", "contacts_screen"), ("В меню", "start_screen")],
    ],
    "contacts_all": [
        [("Назад к контактам", "contacts_screen"), ("В меню", "start_screen")],
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


async def show_screen(update: Update, screen_id: str, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
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
        await update.message.reply_text(ai_answer, reply_markup=build_keyboard("admin_screen"))
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

    print("Beauty AI Gemini Bot is running on Render...")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{PUBLIC_URL}/{TOKEN}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()