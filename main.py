"""Основной файл бота."""
import logging
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    TypeHandler,
    ApplicationHandlerStop,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, HELP_TEXT, MARRY_DEEPLINK_PREFIX
from storage import load_store, save_store
from settings import ChatSettings, get_chat_settings, stop, set_morning, set_evening, set_timezone, settings_cmd
from greetings import schedule_for_chat, preview_greeting
from admin import admin_claim, admins_list, admin_add, admin_remove, ensure_admin
from custom_commands import cc_cmd_set, cc_cmd_set_photo, cc_cmd_remove, cc_cmd_list, custom_command_router
from marriages import cmd_marry, cmd_marriages, cmd_divorce, cb_marry, cmd_expand, cmd_close_marriage
from kisses import cmd_kiss
from drinking import cmd_drink, cb_drink
from selfcare import cmd_selfcare, cb_ribs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("tg-g4f-greetings")

BLOCKED_CHAT_ID = -1002403119663  


def is_blocked_chat(update: Update) -> bool:
    if update.effective_chat and update.effective_chat.id == BLOCKED_CHAT_ID:
        return True
    cq = getattr(update, "callback_query", None)
    if cq and cq.message and cq.message.chat and cq.message.chat.id == BLOCKED_CHAT_ID:
        return True
    return False


async def block_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_blocked_chat(update):
        raise ApplicationHandlerStop()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    chat = update.effective_chat
    text = (message.text or "").strip()
    args = text.split(" ", 1)
    start_param = ""
    if len(args) > 1 and args[0].startswith("/start"):
        start_param = args[1].strip()

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await ensure_admin(update):
            return
        chat_id = chat.id
        store = load_store()
        settings = get_chat_settings(store, chat_id)
        store[str(chat_id)] = settings.to_dict()
        save_store(store)
        schedule_for_chat(context.application, chat_id, settings)
        await message.reply_text(
            "Подписка оформлена! Я буду присылать утренние и вечерние пожелания с котиками.\n"
            "Настроить: /set_morning HH:MM, /set_evening HH:MM, /set_timezone Area/City\n\n"
            "Система браков:\n"
            "• Воспользуйтесь /брак в ответ на сообщение пользователя (или текстовым упоминанием)\n"
            "• Принятие/отказ — в личных сообщениях с ботом\n"
            "• Посмотреть пары: /браки\n"
            "• Кого-нибудь трахнуть: /трахнуть\n"
            "• Выпить алкоголь: /выпить\n"
            "• Самоотсос для одиноких: /самоотсос"
        )
        return

    if start_param.startswith(MARRY_DEEPLINK_PREFIX):
        from marriages import load_marriage
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from utils import safe_html

        pid = start_param[len(MARRY_DEEPLINK_PREFIX):]
        data = load_marriage()
        prop = data["proposals"].get(pid)
        if not prop or prop.get("status") != "pending":
            await message.reply_text("Ссылка недействительна или предложение уже обработано.")
            return

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept:{pid}"),
                InlineKeyboardButton("❌ Отказаться", callback_data=f"decline:{pid}"),
            ]
        ])
        chat_title = f"«{prop['chat_id']}»"
        await message.reply_text(
            f"Предложение брака от {safe_html(prop['proposer_name'])} в чате {chat_title}.\n"
            "Хотите принять?",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return

    await message.reply_text(
        "Привет! Я бот с котиками, пожеланиями и «системой браков».\n"
        "Если вы владелец бота и ещё не назначены: отправьте /admin_claim."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


def bootstrap_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_error_handler(error_handler)

    app.add_handler(TypeHandler(Update, block_chat_handler), group=-100)

    # база 
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("set_morning", set_morning))
    app.add_handler(CommandHandler("set_evening", set_evening))
    app.add_handler(CommandHandler("set_timezone", set_timezone))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("preview", preview_greeting))
    app.add_handler(CommandHandler("help", help_cmd))

    # админ
    app.add_handler(CommandHandler("admin_claim", admin_claim))
    app.add_handler(CommandHandler("admins", admins_list))
    app.add_handler(CommandHandler("admin_add", admin_add))
    app.add_handler(CommandHandler("admin_remove", admin_remove))

    # кастом
    app.add_handler(CommandHandler("cc_set", cc_cmd_set))
    app.add_handler(CommandHandler("cc_set_photo", cc_cmd_set_photo))
    app.add_handler(CommandHandler("cc_remove", cc_cmd_remove))
    app.add_handler(CommandHandler("cc_list", cc_cmd_list))

    # браки
    app.add_handler(CommandHandler(["marry"], cmd_marry, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler(["marriages"], cmd_marriages, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler(["divorce"], cmd_divorce, filters=filters.ChatType.GROUPS))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/брак(?:@\w+)?(?:\s|$)"), cmd_marry))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/браки(?:@\w+)?(?:\s|$)"), cmd_marriages))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/развод(?:@\w+)?(?:\s|$)"), cmd_divorce))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/расширить(?:@\w+)?(?:\s|$)"), cmd_expand))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/закрыть_брак(?:@\w+)?(?:\s|$)"), cmd_close_marriage))
    app.add_handler(CallbackQueryHandler(cb_marry, pattern=r"^(accept|decline):"))

    # развлечения
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/трахнуть(?:@\w+)?(?:\s|$)"), cmd_kiss))
    app.add_handler(MessageHandler(filters.Regex(r"^/выпить(?:@\w+)?(?:\s|$)"), cmd_drink))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/самоотсос(?:@\w+)?(?:\s|$)"), cmd_selfcare))
    app.add_handler(CallbackQueryHandler(cb_drink, pattern=r"^drink:"))
    app.add_handler(CallbackQueryHandler(cb_ribs, pattern=r"^ribs:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_command_router))
    app.add_handler(MessageHandler(filters.Regex(r"^/"), custom_command_router))

    store = load_store()
    for chat_id_str, cfg in store.items():
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            continue
        if chat_id == BLOCKED_CHAT_ID:
            logger.info("Skipping scheduling for blocked chat %s", chat_id)
            continue
        schedule_for_chat(app, chat_id, ChatSettings.from_dict(cfg))

    return app


def main() -> None:
    try:
        app = bootstrap_application()
        logger.info("Starting bot...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Bot crashed: %s", e)
        raise


if __name__ == "__main__":
    main()
