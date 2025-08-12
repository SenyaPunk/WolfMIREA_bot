import time
import random
import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes

from storage import load_cooldowns, save_cooldowns
from marriages import is_user_married_in_chat
from utils import safe_html

logger = logging.getLogger(__name__)

# Кулдауны в секундах
SELFCARE_COOLDOWN = 7200  # 2 часа
REDUCED_COOLDOWN = 5400   # 1.5 часа
RIBS_REQUIRED = 3         # Количество нажатий для слома ребер

# Сообщения о самоотсосе
SELFCARE_MESSAGES = [
    "🍆 {user} мастерски выполнил самоотсос! Гибкость на высоте! 🤸‍♂️",
    "🔥 {user} показал невероятную растяжку и сделал себе приятно! 😏",
    "💪 {user} порадовал себя минетиков и доказал, что йога - это не только про медитацию! 🧘‍♂️",
    "🎯 {user} достиг новых высот в самообслуживании! Браво! 👏",
    "🌟 {user} порадовался минетиком и продемонстрировал акробатические навыки высшего класса! 🤹‍♂️",
    "🏆 {user} отсосал сам себе и получает золотую медаль по самодостаточности! 🥇",
    "🎪 {user} пососал себе. Да ты бы мог выступать в цирке с такой гибкостью! 🎭"
]

# Сообщения об ошибке для женатых
MARRIED_ERROR_MESSAGES = [
    "💍 Эй, у тебя же есть партнер! Зачем самоотсос, когда можно попросить любимого? 😏",
    "💕 Ты в браке! Твоя вторая половинка справится лучше любого самоотсоса! 😘",
    "👫 Семейные люди должны решать такие вопросы вместе! 💑",
    "💒 В браке есть свои привилегии - используй их! 😉",
    "💖 Зачем самоотсос, когда рядом любящий человек? 🥰",
    "👰‍♂️ Женатым/замужним такие вольности не положены! "
]

# Сообщения о сломанных ребрах
RIBS_MESSAGES = [
    "💀 *ХРУСТ* Ребро треснуло! Но гибкость увеличилась! ({remaining} осталось)",
    "🦴 *КРАК* Еще одно ребро пожертвовано ради искусства! ({remaining} осталось)",
    "💥 *ЩЕЛК* Боль - это временно, а самоотсос - навсегда! ({remaining} осталось)",
    "⚡ *ХРЯСЬ* Ребра ломаются, но дух не сломлен! ({remaining} осталось)",
    "🔨 *ТРЕЩ* Жертвы ради великой цели! ({remaining} осталось)"
]

RIBS_COMPLETE_MESSAGE = "🎉 Все ребра сломаны! Кулдаун уменьшен до 1.5 часов! Теперь ты настоящий мастер! 🏆"


def get_selfcare_cooldown_key(user_id: int, chat_id: int) -> str:
    return f"selfcare_{user_id}_{chat_id}"


def get_ribs_key(user_id: int, chat_id: int) -> str:
    return f"ribs_{user_id}_{chat_id}"


def check_selfcare_cooldown(user_id: int, chat_id: int) -> Optional[float]:
    cooldowns = load_cooldowns()
    key = get_selfcare_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        return None
    
    last_selfcare = cooldowns[key].get("last_selfcare", 0)
    is_reduced = cooldowns[key].get("reduced", False)
    
    current_time = time.time()
    time_passed = current_time - last_selfcare
    
    cooldown_time = REDUCED_COOLDOWN if is_reduced else SELFCARE_COOLDOWN
    
    if time_passed >= cooldown_time:
        return None
    
    return cooldown_time - time_passed


def set_selfcare_cooldown(user_id: int, chat_id: int) -> None:
    cooldowns = load_cooldowns()
    key = get_selfcare_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    cooldowns[key]["last_selfcare"] = time.time()
    cooldowns[key]["reduced"] = False
    save_cooldowns(cooldowns)


def get_ribs_broken(user_id: int, chat_id: int) -> int:
    cooldowns = load_cooldowns()
    key = get_ribs_key(user_id, chat_id)
    
    if key not in cooldowns:
        return 0
    
    return cooldowns[key].get("broken", 0)


def break_rib(user_id: int, chat_id: int) -> int:
    cooldowns = load_cooldowns()
    ribs_key = get_ribs_key(user_id, chat_id)
    
    if ribs_key not in cooldowns:
        cooldowns[ribs_key] = {}
    
    current_broken = cooldowns[ribs_key].get("broken", 0)
    new_broken = min(current_broken + 1, RIBS_REQUIRED)
    cooldowns[ribs_key]["broken"] = new_broken
    
    # Если все ребра сломаны, уменьшаем кулдаун
    if new_broken >= RIBS_REQUIRED:
        selfcare_key = get_selfcare_cooldown_key(user_id, chat_id)
        if selfcare_key in cooldowns:
            cooldowns[selfcare_key]["reduced"] = True
        # Сбрасываем счетчик ребер
        cooldowns[ribs_key]["broken"] = 0
    
    save_cooldowns(cooldowns)
    return new_broken


def format_time_remaining(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    else:
        return f"{minutes} мин."


def create_ribs_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру для слома ребер"""
    button = InlineKeyboardButton(
        "🦴 Сломать ребра", 
        callback_data=f"ribs:{user_id}"
    )
    return InlineKeyboardMarkup([[button]])


async def cmd_selfcare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /самоотсос"""
    message = update.message
    if not message or not update.effective_user:
        return
    
    user = update.effective_user
    chat_id = message.chat.id
    
    # Проверяем, что команда используется в группе
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("🚫 Эта команда работает только в группах!")
        return
    
    # Проверяем, состоит ли пользователь в браке
    from storage import load_marriage
    store = load_marriage()
    if is_user_married_in_chat(store, chat_id, user.id):
        error_message = random.choice(MARRIED_ERROR_MESSAGES)
        await message.reply_text(error_message, parse_mode=ParseMode.HTML)
        return
    
    # Проверяем кулдаун
    remaining_time = check_selfcare_cooldown(user.id, chat_id)
    if remaining_time is not None:
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except Exception as e:
            logger.warning("Failed to delete user message: %s", e)
        
        # Отправляем предупреждение
        warning_msg = await context.bot.send_message(
            chat_id,
            f"🚫 <b>Рано еще!</b>\n\n"
            f"⏰ Попробуйте снова через {format_time_remaining(remaining_time)}\n"
            f"💡 <i>Организму нужно восстановиться...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Удаляем предупреждение через 3 секунды
        async def delete_warning(context):
            try:
                await context.bot.delete_message(chat_id, warning_msg.message_id)
            except Exception as e:
                logger.warning("Failed to delete warning message: %s", e)
        
        context.job_queue.run_once(delete_warning, 3)
        return
    
    # Устанавливаем кулдаун
    set_selfcare_cooldown(user.id, chat_id)
    
    # Выбираем случайное сообщение
    selfcare_message = random.choice(SELFCARE_MESSAGES)
    formatted_message = selfcare_message.format(user=safe_html(user.first_name))
    
    # Создаем клавиатуру с кнопкой слома ребер
    keyboard = create_ribs_keyboard(user.id)
    
    await message.reply_text(
        formatted_message,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    
    logger.info(
        "Selfcare command used by %s (%d) in chat %d",
        user.first_name, user.id, chat_id
    )


async def cb_ribs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопки слома ребер"""
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, user_id_str = query.data.split(":")
        user_id = int(user_id_str)
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка обработки команды.")
        return
    
    # Проверяем, что кнопку нажал тот же пользователь
    if query.from_user.id != user_id:
        await query.answer("🚫 Это не ваши ребра!", show_alert=True)
        return
    
    chat_id = query.message.chat.id
    
    # Ломаем ребро
    broken_ribs = break_rib(user_id, chat_id)
    remaining = RIBS_REQUIRED - broken_ribs
    
    if remaining > 0:
        # Еще нужно ломать ребра
        rib_message = random.choice(RIBS_MESSAGES).format(remaining=remaining)
        keyboard = create_ribs_keyboard(user_id)
        
        try:
            await query.edit_message_text(
                rib_message,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning("Failed to edit ribs message: %s", e)
    else:
        # Все ребра сломаны
        try:
            await query.edit_message_text(
                RIBS_COMPLETE_MESSAGE,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning("Failed to edit completion message: %s", e)
    
    logger.info(
        "Ribs broken by %s (%d) in chat %d, total: %d",
        query.from_user.first_name, user_id, chat_id, broken_ribs
    )
