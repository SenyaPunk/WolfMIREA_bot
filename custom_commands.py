"""Модуль системы кастомных команд."""
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from storage import load_admins, save_admins
from admin import ensure_admin
from utils import normalize_cmd_name
from config import RESERVED_COMMANDS

logger = logging.getLogger(__name__)


def cc_set(cmd: str, entry: dict) -> None:
    data = load_admins()
    data["custom_commands"][cmd] = entry
    save_admins(data)


def cc_remove(cmd: str) -> bool:
    data = load_admins()
    if cmd in data.get("custom_commands", {}):
        del data["custom_commands"][cmd]
        save_admins(data)
        return True
    return False


def cc_list() -> dict:
    data = load_admins()
    return data.get("custom_commands", {})


async def cc_cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    parts = (update.message.text or "").split(" ", 2)
    if len(parts) < 3:
        await update.message.reply_text("Использование: /cc_set <command> <text>")
        return
    cmd = normalize_cmd_name(parts[1])
    if not cmd or cmd in RESERVED_COMMANDS:
        await update.message.reply_text("Нельзя использовать это имя команды (зарезервировано).")
        return
    text = parts[2].strip()
    cc_set(cmd, {"type": "text", "text": text})
    await update.message.reply_text(f"Кастомная команда '/{cmd}' сохранена (текст).")


async def cc_cmd_set_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    parts = (update.message.text or "").split(" ", 3)
    if len(parts) < 3:
        await update.message.reply_text("Использование: /cc_set_photo <command> <image_url> [| caption]")
        return
    cmd = normalize_cmd_name(parts[1])
    if not cmd or cmd in RESERVED_COMMANDS:
        await update.message.reply_text("Нельзя использовать это имя команды (зарезервировано).")
        return
    rest = (parts[2] if len(parts) >= 3 else "")
    trailing = (parts[3] if len(parts) >= 4 else "")
    raw = (rest + (" " + trailing if trailing else "")).strip()
    if " | " in raw:
        image_url, caption = raw.split(" | ", 1)
    elif "|" in raw:
        image_url, caption = raw.split("|", 1)
    else:
        image_url, caption = raw, ""
    image_url = image_url.strip()
    caption = caption.strip()
    if not image_url:
        await update.message.reply_text("Укажите image_url.")
        return
    cc_set(cmd, {"type": "photo", "image_url": image_url, "caption": caption})
    await update.message.reply_text(f"Кастомная команда '/{cmd}' сохранена (фото).")


async def cc_cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    parts = (update.message.text or "").split(" ", 1)
    if len(parts) < 2:
        await update.message.reply_text("Использование: /cc_remove <command>")
        return
    cmd = normalize_cmd_name(parts[1])
    if cc_remove(cmd):
        await update.message.reply_text(f"Кастомная команда '/{cmd}' удалена.")
    else:
        await update.message.reply_text("Такой команды нет.")


async def cc_cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cmds = cc_list()
    if not cmds:
        await update.message.reply_text("Кастомных команд пока нет.")
        return
    names = sorted(cmds.keys())
    await update.message.reply_text("Доступные кастомные команды:\n" + ", ".join(f"/{n}" for n in names))


async def custom_command_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()
    if not text.startswith("/"):
        return
    token = text.split()[0]  
    cmd = normalize_cmd_name(token)
    if not cmd or cmd in RESERVED_COMMANDS:
        return  
    cmds = cc_list()
    entry = cmds.get(cmd)
    if not entry:
        return
    try:
        if entry.get("type") == "photo" and entry.get("image_url"):
            await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=entry["image_url"],
                caption=entry.get("caption") or None,
                parse_mode=ParseMode.HTML if entry.get("caption") else None,
            )
        else:
            await message.reply_text(entry.get("text", ""))
    except Exception as e:
        logger.error("Failed to execute custom command '/%s': %s", cmd, e)
        await message.reply_text("Не удалось выполнить команду, попробуйте позже.")
