import time
import logging
from typing import Optional
from telegram import Update, User
from telegram.ext import ContextTypes
from telegram.constants import ChatType

from storage import load_cooldowns, save_cooldowns
from utils import safe_html, get_target_user

logger = logging.getLogger(__name__)

KISS_COOLDOWN = 5400

KISS_MESSAGES = [
    "{kisser} нежно трахнул(а) {target} 💋",
    "{kisser} страстно трахнул(а) {target} 😘",
    "{kisser} сладко трахает в попку {target} 💕",
    "{kisser} трахает {target} прям в анал 😊",
    "{kisser} жестко ебет {target} 😗💨",
    "{kisser} трахает {target} в узкую дырочку 🥰",
    "{kisser} разрывает жопу {target} своим членом 💖",
]


def get_kiss_cooldown_key(user_id: int, chat_id: int) -> str:
    return f"kiss_{user_id}_{chat_id}"


def check_kiss_cooldown(user_id: int, chat_id: int) -> Optional[float]:
    cooldowns = load_cooldowns()
    key = get_kiss_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        return None
    
    last_kiss = cooldowns[key].get("last_kiss", 0)
    current_time = time.time()
    time_passed = current_time - last_kiss
    
    if time_passed >= KISS_COOLDOWN:
        return None
    
    return KISS_COOLDOWN - time_passed


def set_kiss_cooldown(user_id: int, chat_id: int) -> None:
    cooldowns = load_cooldowns()
    key = get_kiss_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    cooldowns[key]["last_kiss"] = time.time()
    save_cooldowns(cooldowns)


def format_time_remaining(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    else:
        return f"{minutes} мин."


async def cmd_kiss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.from_user:
        return
    
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("Эта команда работает только в группах!")
        return
    
    kisser = message.from_user
    chat_id = message.chat.id
    
    target_user = get_target_user(message, context.args)
    
    if not target_user:
        await message.reply_text(
            "Укажите пользователя, которого хотите трахнуть!\n"
            "Используйте: /трахнуть @username или в ответ на сообщение"
        )
        return
    
    is_self_kiss = False
    if hasattr(target_user, 'id') and target_user.id:
        is_self_kiss = target_user.id == kisser.id
    elif hasattr(target_user, 'username') and target_user.username:
        is_self_kiss = (kisser.username and 
                       target_user.username.lower() == kisser.username.lower())
    
    if is_self_kiss:
        bot_msg = await message.reply_text("Лучше трахните кого-нибудь другого!")
        
        async def delete_messages(context):
            try:
                await context.bot.delete_message(chat_id, message.message_id)
            except Exception as e:
                logger.warning("Failed to delete user message: %s", e)
            try:
                await context.bot.delete_message(chat_id, bot_msg.message_id)
            except Exception as e:
                logger.warning("Failed to delete bot message: %s", e)
        
        context.job_queue.run_once(delete_messages, 3)
        return
    
    remaining_time = check_kiss_cooldown(kisser.id, chat_id)
    if remaining_time is not None:
        try:
            await message.delete()
        except Exception as e:
            logger.warning("Failed to delete command message: %s", e)
        
        warning_msg = await context.bot.send_message(
            chat_id,
            f"⏰ {safe_html(kisser.first_name)}, вы сможете снова трахнуть кого-то через "
            f"{format_time_remaining(remaining_time)}",
            parse_mode="HTML"
        )
        
        async def delete_warning(context):
            try:
                await context.bot.delete_message(chat_id, warning_msg.message_id)
            except Exception as e:
                logger.warning("Failed to delete warning message: %s", e)
        
        context.job_queue.run_once(delete_warning, 3)
        return
    
    set_kiss_cooldown(kisser.id, chat_id)
    
    import random
    kiss_message = random.choice(KISS_MESSAGES)
    
    target_name = target_user.first_name
    if hasattr(target_user, 'username') and target_user.username and not hasattr(target_user, 'id'):
        target_name = f"@{target_user.username}"
    
    formatted_message = kiss_message.format(
        kisser=safe_html(kisser.first_name),
        target=safe_html(target_name)
    )
    
    await message.reply_text(formatted_message, parse_mode="HTML")
    
    logger.info(
        "Kiss command used by %s (%d) targeting %s in chat %d",
        kisser.first_name, kisser.id,
        target_name, chat_id
    )
