import secrets
import time
from typing import Dict, Any, Optional, Tuple, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from storage import load_marriage, save_marriage
from utils import display_name_from_user, safe_html, mention_html, format_timestamp, profile_link_html
from config import MARRY_DEEPLINK_PREFIX

MAX_FAMILY_SIZE = 5


def get_user_marriage(store: Dict[str, Any], chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Найти брак пользователя в чате"""
    for m in store.get("marriages", []):
        if m["chat_id"] == chat_id:
            members = m.get("members", [])
            for member in members:
                if member["id"] == user_id:
                    return m
    return None


def is_user_married_in_chat(store: Dict[str, Any], chat_id: int, user_id: int) -> bool:
    """Проверить, состоит ли пользователь в браке в чате"""
    return get_user_marriage(store, chat_id, user_id) is not None


def find_marriage_index(store: Dict[str, Any], chat_id: int, user_id: int) -> Optional[int]:
    """Найти индекс брака пользователя"""
    for idx, m in enumerate(store.get("marriages", [])):
        if m["chat_id"] == chat_id:
            members = m.get("members", [])
            for member in members:
                if member["id"] == user_id:
                    return idx
    return None


def remove_user_from_marriage(store: Dict[str, Any], chat_id: int, user_id: int) -> bool:
    """Удалить пользователя из брака"""
    marriage_idx = find_marriage_index(store, chat_id, user_id)
    if marriage_idx is None:
        return False
    
    marriage = store["marriages"][marriage_idx]
    members = marriage.get("members", [])
    
    # Удаляем пользователя из списка участников
    marriage["members"] = [m for m in members if m["id"] != user_id]
    
    # Если остался только один человек, удаляем весь брак
    if len(marriage["members"]) <= 1:
        del store["marriages"][marriage_idx]
    
    save_marriage(store)
    return True


def can_join_marriage(marriage: Dict[str, Any]) -> bool:
    """Проверить, можно ли присоединиться к браку"""
    if not marriage.get("expanded", False):
        return False
    members_count = len(marriage.get("members", []))
    return members_count < MAX_FAMILY_SIZE


def get_marriage_members_text(marriage: Dict[str, Any]) -> str:
    """Получить текст со списком участников брака"""
    members = marriage.get("members", [])
    if len(members) <= 2:
        # Обычный брак
        if len(members) == 2:
            a = profile_link_html(members[0]["id"], members[0]["name"], members[0].get("username"))
            b = profile_link_html(members[1]["id"], members[1]["name"], members[1].get("username"))
            return f"{a} 💕 {b}"
    else:
        # Полигамный брак
        member_links = []
        for member in members:
            link = profile_link_html(member["id"], member["name"], member.get("username"))
            member_links.append(link)
        return " 💕 ".join(member_links)
    
    return "Неизвестный брак"


def find_target_user_marriage(store: Dict[str, Any], chat_id: int, target_user, target_username: Optional[str]) -> Optional[Dict[str, Any]]:
    """Найти брак целевого пользователя (по ID или username)"""
    if target_user:
        return get_user_marriage(store, chat_id, target_user.id)
    
    # Если только username, ищем по всем бракам
    if target_username:
        for marriage in store.get("marriages", []):
            if marriage["chat_id"] == chat_id:
                for member in marriage.get("members", []):
                    if member.get("username") and member["username"].lower() == target_username.lower():
                        return marriage
    
    return None


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

    # Определяем цель предложения
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

    # Проверяем статус предлагающего
    proposer_marriage = get_user_marriage(store, chat_id, proposer.id)
    
    # Проверяем статус цели (учитываем как ID, так и username)
    target_marriage = find_target_user_marriage(store, chat_id, target_user, target_username)

    # Логика предложений
    if proposer_marriage and target_marriage:
        # Проверяем, не один ли это брак
        proposer_idx = find_marriage_index(store, chat_id, proposer.id)
        target_idx = None
        
        if target_user:
            target_idx = find_marriage_index(store, chat_id, target_user.id)
        else:
            # Ищем индекс брака по username
            for idx, marriage in enumerate(store.get("marriages", [])):
                if marriage["chat_id"] == chat_id:
                    for member in marriage.get("members", []):
                        if member.get("username") and member["username"].lower() == target_username.lower():
                            target_idx = idx
                            break
                    if target_idx is not None:
                        break
        
        if proposer_idx == target_idx:
            await message.reply_text(
                "💕 <b>Вы уже в одной семье!</b>\n\n"
                "👨‍👩‍👧‍👦 Вы состоите в браке с этим человеком.",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text(
                "💔 <b>Оба уже в разных браках!</b>\n\n"
                "💡 Нельзя объединить два разных брака.",
                parse_mode=ParseMode.HTML
            )
        return
    
    if proposer_marriage:
        # Предлагающий в браке - приглашает в свою семью
        if not can_join_marriage(proposer_marriage):
            if not proposer_marriage.get("expanded", False):
                await message.reply_text(
                    "💔 <b>Ваш брак закрыт для новых участников!</b>\n\n"
                    "💡 Используйте /расширить чтобы разрешить присоединение.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    f"💔 <b>Семья переполнена!</b>\n\n"
                    f"👥 Максимум участников: {MAX_FAMILY_SIZE}\n"
                    f"👥 Текущее количество: {len(proposer_marriage.get('members', []))}",
                    parse_mode=ParseMode.HTML
                )
            return
        
        if target_marriage:
            await message.reply_text(
                "💔 <b>Этот пользователь уже состоит в браке!</b>",
                parse_mode=ParseMode.HTML
            )
            return
            
        proposal_type = "invite_to_family"
        
    elif target_marriage:
        # Цель в браке - просим принять в их семью
        if not can_join_marriage(target_marriage):
            if not target_marriage.get("expanded", False):
                await message.reply_text(
                    "💔 <b>Их брак закрыт для новых участников!</b>\n\n"
                    "💡 Они должны использовать /расширить чтобы разрешить присоединение.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    f"💔 <b>Их семья переполнена!</b>\n\n"
                    f"👥 Максимум участников: {MAX_FAMILY_SIZE}",
                    parse_mode=ParseMode.HTML
                )
            return
            
        proposal_type = "join_family"
        
    else:
        # Оба свободны - обычный брак
        proposal_type = "regular"

    # Создаем предложение
    pid = secrets.token_urlsafe(8).replace("_", "-")
    proposer_name = display_name_from_user(proposer)
    proposal: Dict[str, Any] = {
        "id": pid,
        "chat_id": chat_id,
        "proposer_id": proposer.id,
        "proposer_name": proposer_name,
        "proposer_username": proposer.username if proposer.username else None,
        "target_id": target_user.id if target_user else None,
        "target_username": target_user.username if target_user and target_user.username else (target_username or None),
        "target_name": display_name_from_user(target_user) if target_user else (f"@{target_username}" if target_username else "пользователь"),
        "type": proposal_type,
        "created_at": int(time.time()),
        "status": "pending",
    }
    
    if proposal_type == "join_family" and target_marriage:
        # Сохраняем индекс целевого брака для точного определения
        target_marriage_idx = find_marriage_index(store, chat_id, target_user.id if target_user else None)
        if target_marriage_idx is not None:
            proposal["target_marriage_idx"] = target_marriage_idx
            # Также сохраняем ID всех участников целевого брака для дополнительной проверки
            proposal["target_marriage_members"] = [m["id"] for m in target_marriage.get("members", [])]
    
    store["proposals"][pid] = proposal
    save_marriage(store)

    # Отправляем предложение
    me = await context.bot.get_me()
    bot_username = me.username
    deep_link = f"https://t.me/{bot_username}?start={MARRY_DEEPLINK_PREFIX}{pid}"

    dm_ok = False
    if target_user:
        try:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💍 Принять", callback_data=f"accept:{pid}"),
                    InlineKeyboardButton("💔 Отказаться", callback_data=f"decline:{pid}"),
                ]
            ])
            
            if proposal_type == "regular":
                text = (
                    f"💕 <b>Предложение брака!</b>\n\n"
                    f"👤 От: {safe_html(proposer_name)}\n"
                    f"💬 В чате: «{safe_html(chat.title or str(chat.id))}»\n\n"
                    f"💖 <i>Хотите принять предложение?</i>"
                )
            elif proposal_type == "invite_to_family":
                family_size = len(proposer_marriage.get("members", []))
                text = (
                    f"👨‍👩‍👧‍👦 <b>Приглашение в семью!</b>\n\n"
                    f"👤 От: {safe_html(proposer_name)}\n"
                    f"💬 В чате: «{safe_html(chat.title or str(chat.id))}»\n"
                    f"👥 Размер семьи: {family_size} человек\n\n"
                    f"💖 <i>Хотите присоединиться к их семье?</i>"
                )
            else:  # join_family
                family_size = len(target_marriage.get("members", []))
                text = (
                    f"🙏 <b>Просьба о присоединении!</b>\n\n"
                    f"👤 {safe_html(proposer_name)} хочет присоединиться к вашей семье\n"
                    f"💬 В чате: «{safe_html(chat.title or str(chat.id))}»\n"
                    f"👥 Текущий размер семьи: {family_size} человек\n\n"
                    f"💖 <i>Принять в семью?</i>"
                )
            
            await context.bot.send_message(
                chat_id=target_user.id,
                text=text,
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

    # Дополнительная проверка на момент принятия
    if is_user_married_in_chat(store, prop["chat_id"], user.id) and prop.get("type") != "join_family":
        await cq.answer("💍 Вы уже состоите в браке в этом чате!", show_alert=True)
        return

    if action == "accept":
        proposal_type = prop.get("type", "regular")
        
        if proposal_type == "regular":
            # Обычный брак между двумя людьми
            marriage = {
                "chat_id": prop["chat_id"],
                "members": [
                    {
                        "id": prop["proposer_id"],
                        "name": prop["proposer_name"],
                        "username": prop.get("proposer_username")
                    },
                    {
                        "id": user.id,
                        "name": display_name_from_user(user),
                        "username": user.username if user.username else None
                    }
                ],
                "since": int(time.time()),
                "expanded": False
            }
            store["marriages"].append(marriage)
            
            success_text = (
                f"💍 <b>Поздравляем!</b>\n\n"
                f"✅ Вы приняли предложение брака от {safe_html(prop['proposer_name'])}!\n"
                f"❤️ Теперь вы официально в браке!\n"
                f"🎉 Желаем счастья!"
            )
            
            chat_text = (
                f"🎊 <b>СВАДЬБА!</b> 🎊\n\n"
                f"💑 {mention_html(prop['proposer_id'], prop['proposer_name'])} "
                f"и {mention_html(user.id, display_name_from_user(user))} теперь в браке!\n\n"
                f"💍❤️ <i>Поздравляем молодоженов!</i> ❤️💍"
            )
            
        elif proposal_type == "invite_to_family":
            # Приглашение в существующую семью
            proposer_marriage = get_user_marriage(store, prop["chat_id"], prop["proposer_id"])
            if not proposer_marriage or not can_join_marriage(proposer_marriage):
                await cq.answer("❌ Семья больше не принимает новых участников.", show_alert=True)
                return
                
            # Добавляем пользователя в семью
            marriage_idx = find_marriage_index(store, prop["chat_id"], prop["proposer_id"])
            store["marriages"][marriage_idx]["members"].append({
                "id": user.id,
                "name": display_name_from_user(user),
                "username": user.username if user.username else None
            })
            
            family_size = len(store["marriages"][marriage_idx]["members"])
            success_text = (
                f"👨‍👩‍👧‍👦 <b>Добро пожаловать в семью!</b>\n\n"
                f"✅ Вы присоединились к семье {safe_html(prop['proposer_name'])}!\n"
                f"👥 Размер семьи: {family_size} человек\n"
                f"🎉 Желаем счастья!"
            )
            
            chat_text = (
                f"🎊 <b>ПОПОЛНЕНИЕ В СЕМЬЕ!</b> 🎊\n\n"
                f"👨‍👩‍👧‍👦 {mention_html(user.id, display_name_from_user(user))} "
                f"присоединился к семье!\n\n"
                f"💍❤️ <i>Поздравляем с расширением семьи!</i> ❤️💍"
            )
            
        else:  # join_family
            # Проверяем, есть ли сохраненная информация о целевом браке
            if "target_marriage_idx" in prop and "target_marriage_members" in prop:
                target_marriage_idx = prop["target_marriage_idx"]
                target_marriage_members = prop["target_marriage_members"]
                
                # Проверяем, что брак все еще существует и пользователь в нем
                if (target_marriage_idx < len(store["marriages"]) and 
                    store["marriages"][target_marriage_idx]["chat_id"] == prop["chat_id"] and
                    user.id in target_marriage_members):
                    
                    target_marriage = store["marriages"][target_marriage_idx]
                    if not can_join_marriage(target_marriage):
                        await cq.answer("❌ Семья больше не принимает новых участников.", show_alert=True)
                        return
                    
                    # Добавляем предлагающего в правильный брак
                    store["marriages"][target_marriage_idx]["members"].append({
                        "id": prop["proposer_id"],
                        "name": prop["proposer_name"],
                        "username": prop.get("proposer_username")
                    })
                    
                    family_size = len(store["marriages"][target_marriage_idx]["members"])
                else:
                    await cq.answer("❌ Целевая семья больше не существует или изменилась.", show_alert=True)
                    return
            else:
                # Fallback к старой логике (если предложение создано до обновления)
                user_marriage = get_user_marriage(store, prop["chat_id"], user.id)
                if not user_marriage or not can_join_marriage(user_marriage):
                    await cq.answer("❌ Ваша семья больше не принимает новых участников.", show_alert=True)
                    return
                    
                # Добавляем предлагающего в семью пользователя
                marriage_idx = find_marriage_index(store, prop["chat_id"], user.id)
                store["marriages"][marriage_idx]["members"].append({
                    "id": prop["proposer_id"],
                    "name": prop["proposer_name"],
                    "username": prop.get("proposer_username")
                })
                
                family_size = len(store["marriages"][marriage_idx]["members"])
            
            success_text = (
                f"👨‍👩‍👧‍👦 <b>Новый член семьи!</b>\n\n"
                f"✅ Вы приняли {safe_html(prop['proposer_name'])} в свою семью!\n"
                f"👥 Размер семьи: {family_size} человек\n"
                f"🎉 Поздравляем!"
            )
            
            chat_text = (
                f"🎊 <b>ПОПОЛНЕНИЕ В СЕМЬЕ!</b> 🎊\n\n"
                f"👨‍👩‍👧‍👦 {mention_html(prop['proposer_id'], prop['proposer_name'])} "
                f"присоединился к семье!\n\n"
                f"💍❤️ <i>Поздравляем с расширением семьи!</i> ❤️💍"
            )


        prop["status"] = "accepted"
        save_marriage(store)

        await cq.edit_message_text(success_text, parse_mode=ParseMode.HTML)

        # Уведомляем в чат
        try:
            await context.bot.send_message(
                chat_id=prop["chat_id"],
                text=chat_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    else:
        prop["status"] = "declined"
        save_marriage(store)
        await cq.edit_message_text(
            f"💔 <b>Предложение отклонено</b>\n\n"
            f"❌ Вы отказались от предложения от {safe_html(prop['proposer_name'])}.\n"
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
    marriages = [m for m in data["marriages"] if m["chat_id"] == chat.id]
    if not marriages:
        await message.reply_text(
            "💔 <b>В этом чате пока нет пар</b>\n\n"
            "💡 Используйте /брак чтобы предложить кому-то руку и сердце!",
            parse_mode=ParseMode.HTML
        )
        return

    lines = []
    for i, marriage in enumerate(marriages, 1):
        members_text = get_marriage_members_text(marriage)
        members_count = len(marriage.get("members", []))
        
        status_emoji = "🔓" if marriage.get("expanded", False) else "🔒"
        family_info = f"({members_count} чел.)" if members_count > 2 else ""
        
        lines.append(
            f"{i}. {members_text} {status_emoji} {family_info}\n"
            f"   <i>В браке с {format_timestamp(marriage['since'])}</i>"
        )

    footer = (
        "\n\n<i>🔓 - семья открыта для новых участников\n"
        "🔒 - семья закрыта</i>"
    )

    await message.reply_text(
        f"💍 <b>Счастливые пары этого чата:</b>\n\n" + "\n\n".join(lines) + footer,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
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

    store = load_marriage()
    marriage = get_user_marriage(store, chat.id, user.id)
    if not marriage:
        await message.reply_text(
            "💔 <b>Вы не состоите в браке</b>\n\n"
            "💡 Сначала найдите себе партнера с помощью /брак!",
            parse_mode=ParseMode.HTML
        )
        return

    members = marriage.get("members", [])
    members_count = len(members)
    
    if members_count <= 2:
        # Обычный развод - удаляем весь брак
        remove_user_from_marriage(store, chat.id, user.id)
        
        partner = None
        for member in members:
            if member["id"] != user.id:
                partner = member
                break
        
        if partner:
            await message.reply_text(
                f"💔 <b>РАЗВОД ОФОРМЛЕН</b>\n\n"
                f"😢 {mention_html(user.id, display_name_from_user(user))} и "
                f"{mention_html(partner['id'], partner['name'])} больше не в браке.\n\n"
                f"🕊️ <i>Желаем обоим найти новое счастье...</i>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                "💔 <b>Вы покинули брак</b>",
                parse_mode=ParseMode.HTML,
            )
    else:
        # Выход из полигамной семьи
        remove_user_from_marriage(store, chat.id, user.id)
        
        await message.reply_text(
            f"💔 <b>ВЫХОД ИЗ СЕМЬИ</b>\n\n"
            f"😢 {mention_html(user.id, display_name_from_user(user))} покинул семью.\n"
            f"👥 В семье осталось {members_count - 1} человек.\n\n"
            f"🕊️ <i>Желаем найти новое счастье...</i>",
            parse_mode=ParseMode.HTML
        )


async def cmd_expand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для расширения брака"""
    message = update.message
    if not message or not update.effective_chat:
        return
    
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("💒 Команда /расширить работает только в группах!")
        return

    user = update.effective_user
    if not user:
        return

    store = load_marriage()
    marriage = get_user_marriage(store, chat.id, user.id)
    
    if not marriage:
        await message.reply_text(
            "💔 <b>Вы не состоите в браке</b>\n\n"
            "💡 Сначала найдите себе партнера с помощью /брак!",
            parse_mode=ParseMode.HTML
        )
        return
    
    if marriage.get("expanded", False):
        await message.reply_text(
            "✅ <b>Ваша семья уже открыта!</b>\n\n"
            "👥 Другие пользователи могут присоединиться к вашей семье.\n"
            "🔒 Используйте /закрыть_брак чтобы запретить новых участников.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Расширяем брак
    marriage_idx = find_marriage_index(store, chat.id, user.id)
    if marriage_idx is not None:
        store["marriages"][marriage_idx]["expanded"] = True
        save_marriage(store)
        
        members_count = len(marriage.get("members", []))
        await message.reply_text(
            f"🔓 <b>Семья открыта для новых участников!</b>\n\n"
            f"👥 Текущий размер: {members_count}/{MAX_FAMILY_SIZE}\n"
            f"💡 Теперь другие пользователи могут:\n"
            f"• Написать /брак @ваш_ник - попросить присоединиться\n"
            f"• Вы можете написать /брак @ник - пригласить кого-то\n\n"
            f"🔒 Используйте /закрыть_брак чтобы запретить новых участников.",
            parse_mode=ParseMode.HTML
        )


async def cmd_close_marriage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для закрытия брака"""
    message = update.message
    if not message or not update.effective_chat:
        return
    
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("💒 Команда /закрыть_брак работает только в группах!")
        return

    user = update.effective_user
    if not user:
        return

    store = load_marriage()
    marriage = get_user_marriage(store, chat.id, user.id)
    
    if not marriage:
        await message.reply_text(
            "💔 <b>Вы не состоите в браке</b>\n\n"
            "💡 Сначала найдите себе партнера с помощью /брак!",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not marriage.get("expanded", False):
        await message.reply_text(
            "🔒 <b>Ваша семья уже закрыта!</b>\n\n"
            "👥 Новые участники не могут присоединиться.\n"
            "🔓 Используйте /расширить чтобы снова разрешить новых участников.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Закрываем брак
    marriage_idx = find_marriage_index(store, chat.id, user.id)
    if marriage_idx is not None:
        store["marriages"][marriage_idx]["expanded"] = False
        save_marriage(store)
        
        members_count = len(marriage.get("members", []))
        await message.reply_text(
            f"🔒 <b>Семья закрыта для новых участников!</b>\n\n"
            f"👥 Текущий размер: {members_count} человек\n"
            f"💡 Новые участники больше не могут присоединиться.\n\n"
            f"🔓 Используйте /расширить чтобы снова разрешить новых участников.",
            parse_mode=ParseMode.HTML
        )
