"""Модуль системы администрирования."""
from typing import Optional
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes
from storage import load_admins, save_admins


def is_owner(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    data = load_admins()
    return data.get("owner_id") == user_id


def is_admin(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    data = load_admins()
    return data.get("owner_id") == user_id or user_id in set(data.get("admins", []))


async def ensure_admin(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    if not is_admin(uid):
        if update.effective_chat and update.message:
            await update.message.reply_text("Эта команда доступна только админам.")
        return False
    return True


def extract_target_user_id_from_message(message) -> Optional[int]:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention" and ent.user:
                return ent.user.id
    parts = (message.text or "").strip().split()
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return None


async def admin_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Эту команду можно использовать только в личных сообщениях с ботом.")
        return
    uid = update.effective_user.id if update.effective_user else None
    data = load_admins()
    if data.get("owner_id"):
        await update.message.reply_text(f"Владелец уже назначен: {data['owner_id']}.")
        return
    if not uid:
        await update.message.reply_text("Не удалось определить ваш ID.")
        return
    data["owner_id"] = uid
    save_admins(data)
    await update.message.reply_text(f"Вы назначены владельцем бота (owner_id={uid}).")


async def admins_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    data = load_admins()
    owner_id = data.get("owner_id")
    admins = data.get("admins", [])
    lines = [f"Owner ID: {owner_id}"]
    if admins:
        lines.append("Admins: " + ", ".join(map(str, admins)))
    else:
        lines.append("Admins: (пусто)")
    await update.message.reply_text("\n".join(lines))


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if not is_owner(uid):
        await update.message.reply_text("Добавлять админов может только Арсений.")
        return
    target_id = extract_target_user_id_from_message(update.message)
    if not target_id:
        await update.message.reply_text("Укажите пользователя (реплаем, text_mention или ID): /admin_add <id>")
        return
    data = load_admins()
    if target_id == data.get("owner_id"):
        await update.message.reply_text("Этот пользователь уже владелец.")
        return
    admins = set(data.get("admins", []))
    admins.add(target_id)
    data["admins"] = list(sorted(admins))
    save_admins(data)
    await update.message.reply_text(f"Пользователь {target_id} добавлен в админы.")


async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if not is_owner(uid):
        await update.message.reply_text("Удалять админов может только владелец бота.")
        return
    target_id = extract_target_user_id_from_message(update.message)
    if not target_id:
        await update.message.reply_text("Укажите пользователя (реплаем, text_mention или ID): /admin_remove <id>")
        return
    data = load_admins()
    if target_id == data.get("owner_id"):
        await update.message.reply_text("Нельзя удалить владельца.")
        return
    admins = set(data.get("admins", []))
    if target_id in admins:
        admins.remove(target_id)
        data["admins"] = list(sorted(admins))
        save_admins(data)
        await update.message.reply_text(f"Пользователь {target_id} удалён из админов.")
    else:
        await update.message.reply_text("Этот пользователь не админ.")
