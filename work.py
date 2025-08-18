import time
import random
import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes

from storage import load_cooldowns, save_cooldowns
from economy import add_user_balance, get_slave_owner
from utils import safe_html

logger = logging.getLogger(__name__)

# Кулдаун между использованиями команды (в секундах)
WORK_COOLDOWN = 14400  # 4 часа
WORK_TIME_LIMIT = 30   # 30 секунд на выполнение работы
REQUIRED_CLICKS = 10   # Нужно нажать ровно 10 раз
MIN_REWARD = 5        # Минимальная награда
MAX_REWARD = 80       # Максимальная награда
REWARD_DELAY = 3600    # Час до выплаты награды
SLAVE_TAX_PERCENT = 10  # процент налога с рабов для хозяина

def get_work_cooldown_key(user_id: int, chat_id: int) -> str:
    return f"work_{user_id}_{chat_id}"

def get_work_session_key(user_id: int, chat_id: int) -> str:
    return f"work_session_{user_id}_{chat_id}"

def check_work_cooldown(user_id: int, chat_id: int) -> Optional[float]:
    cooldowns = load_cooldowns()
    key = get_work_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        return None
    
    last_work = cooldowns[key].get("last_work", 0)
    current_time = time.time()
    time_passed = current_time - last_work
    
    if time_passed >= WORK_COOLDOWN:
        return None
    
    return WORK_COOLDOWN - time_passed

def set_work_cooldown(user_id: int, chat_id: int) -> None:
    cooldowns = load_cooldowns()
    key = get_work_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    cooldowns[key]["last_work"] = time.time()
    save_cooldowns(cooldowns)

def start_work_session(user_id: int, chat_id: int) -> None:
    """Начать рабочую сессию"""
    cooldowns = load_cooldowns()
    key = get_work_session_key(user_id, chat_id)
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    cooldowns[key]["start_time"] = time.time()
    cooldowns[key]["clicks"] = 0
    cooldowns[key]["active"] = True
    save_cooldowns(cooldowns)

def get_work_session(user_id: int, chat_id: int) -> dict:
    """Получить данные рабочей сессии"""
    cooldowns = load_cooldowns()
    key = get_work_session_key(user_id, chat_id)
    
    if key not in cooldowns:
        return {"active": False, "clicks": 0, "start_time": 0}
    
    return cooldowns[key]

def add_work_click(user_id: int, chat_id: int) -> dict:
    """Добавить клик в рабочую сессию"""
    cooldowns = load_cooldowns()
    key = get_work_session_key(user_id, chat_id)
    
    if key not in cooldowns:
        return {"active": False, "clicks": 0, "start_time": 0}
    
    session = cooldowns[key]
    if not session.get("active", False):
        return session
    
    # Проверяем не истекло ли время
    current_time = time.time()
    if current_time - session.get("start_time", 0) > WORK_TIME_LIMIT:
        session["active"] = False
        save_cooldowns(cooldowns)
        return session
    
    session["clicks"] = session.get("clicks", 0) + 1
    save_cooldowns(cooldowns)
    return session

def end_work_session(user_id: int, chat_id: int) -> None:
    """Завершить рабочую сессию"""
    cooldowns = load_cooldowns()
    key = get_work_session_key(user_id, chat_id)
    
    if key in cooldowns:
        cooldowns[key]["active"] = False
        save_cooldowns(cooldowns)

def schedule_reward(user_id: int, chat_id: int, reward: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запланировать выплату награды через час"""
    async def pay_reward(context):
        try:
            owner_id = get_slave_owner(user_id)
            
            if owner_id:
                # Работник является рабом - отдаем 10% хозяину
                slave_tax = int(reward * SLAVE_TAX_PERCENT / 100)
                slave_reward = reward - slave_tax
                
                # Выплачиваем рабу
                add_user_balance(user_id, slave_reward)
                
                # Выплачиваем налог хозяину
                add_user_balance(owner_id, slave_tax)
                
                # Уведомляем раба
                await context.bot.send_message(
                    chat_id,
                    f"💰 <b>Зарплата получена!</b>\n\n"
                    f"👤 <b>Работник:</b> <a href='tg://user?id={user_id}'>пользователь</a>\n"
                    f"💵 <b>Заработано:</b> {reward} монет\n"
                    f"💰 <b>Вам:</b> {slave_reward} монет\n"
                    f"👑 <b>Хозяину:</b> {slave_tax} монет ({SLAVE_TAX_PERCENT}%)\n"
                    f"⏰ <b>За работу час назад</b>",
                    parse_mode=ParseMode.HTML
                )
                
                # Уведомляем хозяина о доходе с раба
                try:
                    await context.bot.send_message(
                        owner_id,
                        f"💎 <b>Доход с раба!</b>\n\n"
                        f"👤 <b>Ваш раб:</b> <a href='tg://user?id={user_id}'>пользователь</a>\n"
                        f"💰 <b>Заработал:</b> {reward} монет\n"
                        f"💵 <b>Ваша доля:</b> {slave_tax} монет ({SLAVE_TAX_PERCENT}%)\n"
                        f"⏰ <b>За работу час назад</b>",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify slave owner {owner_id}: {e}")
                
                logger.info(f"Work reward paid: {slave_reward} coins to slave {user_id}, {slave_tax} coins to owner {owner_id} in chat {chat_id}")
            else:
                # Обычный свободный работник
                add_user_balance(user_id, reward)
                await context.bot.send_message(
                    chat_id,
                    f"💰 <b>Зарплата получена!</b>\n\n"
                    f"👤 <b>Работник:</b> <a href='tg://user?id={user_id}'>пользователь</a>\n"
                    f"💵 <b>Сумма:</b> {reward} монет\n"
                    f"⏰ <b>За работу час назад</b>",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Work reward paid: {reward} coins to user {user_id} in chat {chat_id}")
                
        except Exception as e:
            logger.error(f"Failed to pay work reward: {e}")
    
    context.job_queue.run_once(pay_reward, REWARD_DELAY)

def format_time_remaining(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    else:
        return f"{minutes} мин."

def create_work_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру для работы"""
    button = InlineKeyboardButton(
        "🔨 Работать", 
        callback_data=f"work_click:{user_id}"
    )
    return InlineKeyboardMarkup([[button]])

async def cmd_work(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /work"""
    message = update.message
    if not message or not update.effective_user:
        return
    
    user = update.effective_user
    chat_id = message.chat.id
    
    # Проверяем, что команда используется в группе
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("🚫 Эта команда работает только в группах!")
        return
    
    # Проверяем кулдаун
    remaining_time = check_work_cooldown(user.id, chat_id)
    if remaining_time is not None:
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except Exception as e:
            logger.warning("Failed to delete user message: %s", e)
        
        # Отправляем предупреждение
        warning_msg = await context.bot.send_message(
            chat_id,
            f"🚫 <b>Вы уже работали недавно!</b>\n\n"
            f"⏰ Следующая смена через {format_time_remaining(remaining_time)}\n"
            f"💡 <i>Нужно отдохнуть между сменами...</i>",
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
    
    # Устанавливаем кулдаун и начинаем рабочую сессию
    set_work_cooldown(user.id, chat_id)
    start_work_session(user.id, chat_id)
    
    # Создаем сообщение с кнопкой работы
    keyboard = create_work_keyboard(user.id)
    
    work_msg = await message.reply_text(
        f"🏭 <b>Рабочая смена началась!</b>\n\n"
        f"👤 <b>Работник:</b> {safe_html(user.first_name)}\n"
        f"🎯 <b>Задача:</b> Нажать кнопку ровно {REQUIRED_CLICKS} раз\n"
        f"⏰ <b>Время:</b> {WORK_TIME_LIMIT} секунд\n"
        f"💰 <b>Зарплата:</b> {MIN_REWARD}-{MAX_REWARD} монет (через час)\n\n"
        f"🔥 <b>Начинайте работать!</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    
    # Запланировать удаление сообщения через 35 секунд (если работа не завершена)
    async def cleanup_work_message(context):
        try:
            session = get_work_session(user.id, chat_id)
            if session.get("active", False):
                end_work_session(user.id, chat_id)
                await context.bot.edit_message_text(
                    f"⏰ <b>Время вышло!</b>\n\n"
                    f"❌ {safe_html(user.first_name)} не успел(а) выполнить работу\n"
                    f"📊 Нажато: {session.get('clicks', 0)}/{REQUIRED_CLICKS}\n"
                    f"💸 <b>Зарплата не выплачена</b>",
                    chat_id=chat_id,
                    message_id=work_msg.message_id,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.warning("Failed to cleanup work message: %s", e)
    
    context.job_queue.run_once(cleanup_work_message, WORK_TIME_LIMIT + 5)
    
    logger.info(
        "Work command used by %s (%d) in chat %d",
        user.first_name, user.id, chat_id
    )

async def cb_work_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопки работы"""
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
        await query.answer("🚫 Это не ваша работа!", show_alert=True)
        return
    
    chat_id = query.message.chat.id
    user = query.from_user
    
    # Добавляем клик
    session = add_work_click(user_id, chat_id)
    
    if not session.get("active", False):
        await query.answer("⏰ Рабочая смена уже завершена!", show_alert=True)
        return
    
    clicks = session.get("clicks", 0)
    start_time = session.get("start_time", 0)
    current_time = time.time()
    elapsed = current_time - start_time
    remaining_time = max(0, WORK_TIME_LIMIT - elapsed)
    
    # Проверяем не истекло ли время
    if remaining_time <= 0:
        end_work_session(user_id, chat_id)
        await query.edit_message_text(
            f"⏰ <b>Время вышло!</b>\n\n"
            f"❌ {safe_html(user.first_name)} не успел(а) выполнить работу\n"
            f"📊 Нажато: {clicks}/{REQUIRED_CLICKS}\n"
            f"💸 <b>Зарплата не выплачена</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверяем выполнение задачи
    if clicks == REQUIRED_CLICKS:
        # Работа выполнена успешно!
        end_work_session(user_id, chat_id)
        reward = random.randint(MIN_REWARD, MAX_REWARD)
        
        owner_id = get_slave_owner(user_id)
        reward_info = ""
        
        if owner_id:
            slave_tax = int(reward * SLAVE_TAX_PERCENT / 100)
            slave_reward = reward - slave_tax
            reward_info = f"💰 <b>Зарплата:</b> {slave_reward} монет (из {reward}, {SLAVE_TAX_PERCENT}% хозяину)\n"
        else:
            reward_info = f"💰 <b>Зарплата:</b> {reward} монет\n"
        
        # Запланировать выплату через час
        schedule_reward(user_id, chat_id, reward, context)
        
        await query.edit_message_text(
            f"✅ <b>Работа выполнена!</b>\n\n"
            f"👤 <b>Работник:</b> {safe_html(user.first_name)}\n"
            f"📊 <b>Результат:</b> {clicks}/{REQUIRED_CLICKS} ✅\n"
            f"⏱️ <b>Время:</b> {int(elapsed)} сек.\n"
            f"{reward_info}"
            f"⏰ <b>Выплата через:</b> 1 час",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(
            "Work completed by %s (%d) in chat %d, reward: %d, owner: %s",
            user.first_name, user_id, chat_id, reward, owner_id or "none"
        )
        
    elif clicks > REQUIRED_CLICKS:
        # Слишком много нажатий - работа провалена
        end_work_session(user_id, chat_id)
        await query.edit_message_text(
            f"❌ <b>Работа провалена!</b>\n\n"
            f"👤 {safe_html(user.first_name)} нажал(а) слишком много раз\n"
            f"📊 Нажато: {clicks}/{REQUIRED_CLICKS} ❌\n"
            f"💸 <b>Зарплата не выплачена</b>\n\n"
            f"💡 <i>Нужно было нажать ровно {REQUIRED_CLICKS} раз!</i>",
            parse_mode=ParseMode.HTML
        )
        
    else:
        # Продолжаем работу
        keyboard = create_work_keyboard(user_id)
        await query.edit_message_text(
            f"🔨 <b>Работа в процессе...</b>\n\n"
            f"👤 <b>Работник:</b> {safe_html(user.first_name)}\n"
            f"📊 <b>Прогресс:</b> {clicks}/{REQUIRED_CLICKS}\n"
            f"⏰ <b>Осталось времени:</b> {int(remaining_time)} сек.\n\n"
            f"🎯 <b>Продолжайте нажимать!</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
