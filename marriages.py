"""Модуль системы браков."""
import secrets
import time
from typing import Dict, Any, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from storage import load_marriage, save_marriage
from utils import display_name_from_user, safe_html, mention_html, format_timestamp
from config import MARRY_DEEPLINK_PREFIX


def is_user_married_in_chat(store: Dict[str, Any], chat_id: int, user_id: int) -> bool:
    for m in store.get("marriages", []):
        if m["chat_id"] == chat_id and (m["a_id"] == user_id or m["b_id"] == user_id):
            return True
    return False


def find_user_partner_in_chat(store: Dict[str, Any], chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    for m in store.get("marriages", []):
        if m["chat_id"] == chat_id and (m["a_id"] == user_id or m["b_id"] == user_id):
            return m
    return None


def find_marriage_of_user(store: Dict[str, Any], chat_id: int, user_id: int) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    for idx, m in enumerate(store.get("marriages", [])):
        if m["chat_id"] == chat_id and (m["a_id"] == user_id or m["b_id"] == user_id):
            return idx, m
    return None, None


def remove_marriage(store: Dict[str, Any], idx: int) -> None:
    if 0 <= idx < len(store["marriages"]):
        del store["marriages"][idx]
        save_marriage(store)


async def cmd_marry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not update.effective_chat:
        return

    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("💒 Команда /брак используется только в группах!")
        return

    proposer = update.effective_user
    if not proposer:
        return

    target_user = None
    target_username = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        if message.entities:
            for ent in message.entities:
                if ent.type == "text_mention" and ent.user:
                    target_user = ent.user
                    break
                if ent.type == "mention":
                    text = message.text or ""
                    mention_text = text[ent.offset: ent.offset + ent.length]
                    target_username = mention_text.lstrip("@")

    if not target_user and not target_username:
        await message.reply_text(
            "💕 <b>Кого звать в брак?</b>\n\n"
            "📝 <i>Подсказка:</i> ответьте на сообщение человека командой /брак или упомяните его как «текстовое упоминание» (с выбором из списка).\n"
            "⚠️ Обычный @username может не дать боту узнать ID для отправки в ЛС.",
            parse_mode=ParseMode.HTML
        )
        return

    if target_user and target_user.id == proposer.id:
        await message.reply_text("🚫 <b>Еблан?</b>\n\n💡 Найди себе достойного партнера в чате!", parse_mode=ParseMode.HTML)
        return

    store = load_marriage()
    chat_id = chat.id

    if is_user_married_in_chat(store, chat_id, proposer.id):
        partner = find_user_partner_in_chat(store, chat_id, proposer.id)
        partner_name = partner["b_name"] if partner["a_id"] == proposer.id else partner["a_name"]
        await message.reply_text(
            f"💍 <b>Вы уже состоите в браке!</b>\n\n"
            f"❤️ Ваш партнер: {safe_html(partner_name)}\n"
            f"💔 Для развода наберите /развод",
            parse_mode=ParseMode.HTML,
        )
        return

    if target_user and is_user_married_in_chat(store, chat_id, target_user.id):
        await message.reply_text(
            f"💔 <b>Этот пользователь уже состоит в браке!</b>\n\n"
            f"💔 {safe_html(display_name_from_user(target_user))} уже занят(а) в этом чате.",
            parse_mode=ParseMode.HTML
        )
        return

    pid = secrets.token_urlsafe(8).replace("_", "-")
    proposer_name = display_name_from_user(proposer)
    proposal: Dict[str, Any] = {
        "id": pid,
        "chat_id": chat_id,
        "proposer_id": proposer.id,
        "proposer_name": proposer_name,
        "target_id": target_user.id if target_user else None,
        "target_username": target_user.username if target_user and target_user.username else (target_username or None),
        "target_name": display_name_from_user(target_user) if target_user else (f"@{target_username}" if target_username else "пользователь"),
        "created_at": int(time.time()),
        "status": "pending",
    }
    store["proposals"][pid] = proposal
    save_marriage(store)

    me = await context.bot.get_me()
    bot_username = me.username
    deep_link = f"https://t.me/{bot_username}?start={MARRY_DEEPLINK_PREFIX}{pid}"

    dm_ok = False
    if target_user:
        try:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💍 Принять предложение", callback_data=f"accept:{pid}"),
                    InlineKeyboardButton("💔 Отказаться", callback_data=f"decline:{pid}"),
                ]
            ])
            await context.bot.send_message(
                chat_id=target_user.id,
                text=(
                    f"💕 <b>Предложение брака!</b>\n\n"
                    f"👤 От: {safe_html(proposer_name)}\n"
                    f"💬 В чате: «{safe_html(chat.title or str(chat.id))}»\n\n"
                    f"💖 <i>Хотите принять предложение?</i>"
                ),
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
            dm_ok = True
        except Exception:
            pass

    if dm_ok:
        await message.reply_text(
            f"💌 <b>Предложение отправлено!</b>\n\n"
            f"👤 Получатель: {safe_html(proposal['target_name'])}\n"
            f"📨 Сообщение доставлено в личные сообщения\n"
            f"⏰ Ожидайте ответа...",
            parse_mode=ParseMode.HTML,
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💍 Перейти к предложению", url=deep_link)]
        ])
        await message.reply_text(
            f"⚠️ <b>Не удалось отправить в ЛС</b>\n\n"
            f"👤 Получатель: {safe_html(proposal['target_name'])}\n"
            f"💡 Нажмите кнопку ниже, чтобы принять предложение:",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )


async def cb_marry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cq = update.callback_query
    if not cq or not update.effective_user:
        return

    user = update.effective_user
    data = cq.data or ""
    if not (data.startswith("accept:") or data.startswith("decline:")):
        await cq.answer()
        return

    action, pid = data.split(":", 1)
    store = load_marriage()
    prop = store["proposals"].get(pid)
    if not prop or prop.get("status") != "pending":
        await cq.answer("❌ Ссылка недействительна или предложение уже обработано.", show_alert=True)
        return

    if prop.get("proposer_id") == user.id:
        await cq.answer("🚫 Нельзя принять предложение от самого себя!", show_alert=True)
        return

    if prop.get("target_id") and prop["target_id"] != user.id:
        await cq.answer("❌ Это предложение не для вас.", show_alert=True)
        return

    if is_user_married_in_chat(store, prop["chat_id"], user.id):
        await cq.answer("💍 Вы уже состоите в браке в этом чате!", show_alert=True)
        return

    if action == "accept":
        # Создаем брак
        marriage = {
            "chat_id": prop["chat_id"],
            "a_id": prop["proposer_id"],
            "a_name": prop["proposer_name"],
            "b_id": user.id,
            "b_name": display_name_from_user(user),
            "since": int(time.time()),
        }
        store["marriages"].append(marriage)
        prop["status"] = "accepted"
        save_marriage(store)

        await cq.edit_message_text(
            f"💍 <b>Поздравляем!</b>\n\n"
            f"✅ Вы приняли предложение брака от {safe_html(prop['proposer_name'])}!\n"
            f"❤️ Теперь вы официально в браке!\n"
            f"🎉 Желаем счастья!",
            parse_mode=ParseMode.HTML,
        )

        # Уведомляем в чат
        try:
            await context.bot.send_message(
                chat_id=prop["chat_id"],
                text=(
                    f"🎊 <b>СВАДЬБА!</b> 🎊\n\n"
                    f"💑 {mention_html(prop['proposer_id'], prop['proposer_name'])} "
                    f"и {mention_html(user.id, display_name_from_user(user))} теперь в браке!\n\n"
                    f"💍❤️ <i>Поздравляем молодоженов!</i> ❤️💍"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    else:
        prop["status"] = "declined"
        save_marriage(store)
        await cq.edit_message_text(
            f"💔 <b>Предложение отклонено</b>\n\n"
            f"❌ Вы отказались от предложения брака от {safe_html(prop['proposer_name'])}.\n"
            f"😢 Возможно, в следующий раз повезет больше...",
            parse_mode=ParseMode.HTML,
        )


async def cmd_marriages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("💒 Команда /браки работает только в группах!")
        return

    data = load_marriage()
    pairs = [m for m in data["marriages"] if m["chat_id"] == chat.id]
    if not pairs:
        await message.reply_text(
            "💔 <b>В этом чате пока нет пар</b>\n\n"
            "💡 Используйте /брак чтобы предложить кому-то руку и сердце!",
            parse_mode=ParseMode.HTML
        )
        return

    lines = []
    for i, m in enumerate(pairs, 1):
        a = mention_html(m["a_id"], m["a_name"])
        b = mention_html(m["b_id"], m["b_name"])
        lines.append(f"{i}. {a} 💕 {b}\n   <i>В браке с {format_timestamp(m['since'])}</i>")

    await message.reply_text(
        f"💍 <b>Счастливые пары этого чата:</b>\n\n" + "\n\n".join(lines),
        parse_mode=ParseMode.HTML
    )


async def cmd_divorce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("💔 Команда /развод работает только в группах!")
        return

    user = update.effective_user
    if not user:
        return

    data = load_marriage()
    idx, marriage = find_marriage_of_user(data, chat.id, user.id)
    if marriage is None:
        await message.reply_text(
            "💔 <b>Вы не состоите в браке</b>\n\n"
            "💡 Сначала найдите себе партнера с помощью /брак!",
            parse_mode=ParseMode.HTML
        )
        return

    mentioned_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        mentioned_id = message.reply_to_message.from_user.id
    else:
        if message.entities:
            for ent in message.entities:
                if ent.type == "text_mention" and ent.user:
                    mentioned_id = ent.user.id
                    break

    a_id, a_name = marriage["a_id"], marriage["a_name"]
    b_id, b_name = marriage["b_id"], marriage["b_name"]
    partner_id = b_id if a_id == user.id else a_id
    partner_name = b_name if a_id == user.id else a_name

    if mentioned_id is not None and mentioned_id != partner_id:
        await message.reply_text(
            f"⚠️ <b>Ошибка развода</b>\n\n"
            f"💍 Вы состоите в браке с {mention_html(partner_id, partner_name)}\n\n"
            f"💡 Для развода используйте /развод без упоминания или ответьте на сообщение вашего партнера.",
            parse_mode=ParseMode.HTML,
        )
        return

    remove_marriage(data, idx)
    await message.reply_text(
        f"💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\n"
        f"😢 {mention_html(user.id, display_name_from_user(user))} и "
        f"{mention_html(partner_id, partner_name)} больше не в браке.\n\n"
        f"🕊️ <i>Желаем обоим найти новое счастье...</i>",
        parse_mode=ParseMode.HTML,
    )
