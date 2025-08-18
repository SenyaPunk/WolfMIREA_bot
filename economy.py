"""Система экономики бота."""
import json
import logging
from typing import Dict, Any, Optional
from telegram import Update
from telegram.ext import ContextTypes
from pathlib import Path
from config import DATA_DIR
from admin import ensure_admin, extract_target_user_id_from_message
from utils import safe_html, profile_link_html

logger = logging.getLogger(__name__)

# Файл для хранения балансов
ECONOMY_FILE = DATA_DIR / "economy.json"

# Настройки экономики
DEFAULT_BALANCE = 0
CURRENCY_NAME = "монет"
CURRENCY_SYMBOL = "🪙"


def load_economy() -> Dict[str, Any]:
    """Загружает данные экономики."""
    if not ECONOMY_FILE.exists():
        return {"balances": {}, "slaves": {}, "usernames": {}}
    try:
        with open(ECONOMY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            data.setdefault("balances", {})
            data.setdefault("slaves", {})
            data.setdefault("usernames", {})
            return data
    except Exception as e:
        logger.error("Failed to read economy data: %s", e)
        return {"balances": {}, "slaves": {}, "usernames": {}}


def save_economy(data: Dict[str, Any]) -> None:
    """Сохраняет данные экономики."""
    try:
        with open(ECONOMY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write economy data: %s", e)


def get_user_balance(user_id: int) -> int:
    """Получает баланс пользователя."""
    data = load_economy()
    return data["balances"].get(str(user_id), DEFAULT_BALANCE)


def set_user_balance(user_id: int, amount: int) -> None:
    """Устанавливает баланс пользователя."""
    data = load_economy()
    data["balances"][str(user_id)] = amount
    save_economy(data)


def add_user_balance(user_id: int, amount: int) -> int:
    """Добавляет к балансу пользователя. Возвращает новый баланс."""
    current_balance = get_user_balance(user_id)
    new_balance = current_balance + amount
    set_user_balance(user_id, new_balance)
    return new_balance


def format_balance(amount: int) -> str:
    """Форматирует сумму для отображения."""
    return f"{amount} {CURRENCY_SYMBOL}"


def calculate_total_wealth(balance: int) -> float:
    """Рассчитывает общее состояние пользователя."""
    life_value = 1000  # За жизнь
    bonus_percentage = 0.30  # 30% от баланса
    total = balance + life_value + (balance * bonus_percentage)
    return round(total, 2)


def save_user_username(user_id: int, username: str) -> None:
    """Сохраняет соответствие username -> user_id для будущих поисков."""
    if not username:
        return
    
    data = load_economy()
    if "usernames" not in data:
        data["usernames"] = {}
    
    # Убираем @ если есть
    clean_username = username.lstrip('@').lower()
    data["usernames"][clean_username] = user_id
    save_economy(data)


def get_user_slave(user_id: int) -> Optional[Dict[str, Any]]:
    """Получает информацию о рабе пользователя."""
    data = load_economy()
    return data["slaves"].get(str(user_id))


def set_user_slave(owner_id: int, slave_id: int, purchase_price: int, slave_name: str) -> None:
    """Устанавливает раба для пользователя."""
    data = load_economy()
    data["slaves"][str(owner_id)] = {
        "slave_id": slave_id,
        "purchase_price": purchase_price,
        "slave_name": slave_name
    }
    save_economy(data)


def remove_user_slave(owner_id: int) -> None:
    """Удаляет раба у пользователя."""
    data = load_economy()
    if str(owner_id) in data["slaves"]:
        del data["slaves"][str(owner_id)]
        save_economy(data)


def get_slave_owner(slave_id: int) -> Optional[int]:
    """Находит владельца раба."""
    data = load_economy()
    for owner_id, slave_info in data["slaves"].items():
        if slave_info["slave_id"] == slave_id:
            return int(owner_id)
    return None


def can_buy_slave(buyer_id: int, target_id: int) -> tuple[bool, str]:
    """Проверяет, может ли пользователь купить раба."""
    # Нельзя купить самого себя
    if buyer_id == target_id:
        return False, "❌ Нельзя купить самого себя в рабство!"
    
    # Проверяем, есть ли уже раб у покупателя
    if get_user_slave(buyer_id):
        return False, "❌ У вас уже есть раб! Максимум 1 раб на пользователя."
    
    # Проверяем, не является ли цель уже чьим-то рабом
    if get_slave_owner(target_id):
        return False, "❌ Этот пользователь уже является чьим-то рабом!"
    
    # Проверяем баланс
    buyer_balance = get_user_balance(buyer_id)
    target_wealth = calculate_total_wealth(get_user_balance(target_id))
    
    if buyer_balance < target_wealth:
        return False, f"❌ Недостаточно средств! Нужно {target_wealth} {CURRENCY_SYMBOL}, у вас {buyer_balance} {CURRENCY_SYMBOL}"
    
    return True, ""


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /баланс - показывает баланс пользователя."""
    if not update.effective_user or not update.message:
        return
    
    if update.effective_user.username:
        save_user_username(update.effective_user.id, update.effective_user.username)
    
    target_id = None
    user_name = None
    
    # Сначала проверяем ответ на сообщение
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
        target_user = update.message.reply_to_message.from_user
        user_name = target_user.first_name or target_user.username or f"Пользователь {target_id}"
        
        # Сохраняем username если есть
        if target_user.username:
            save_user_username(target_id, target_user.username)
    
    # Затем проверяем упоминания в тексте
    elif update.message.entities:
        for entity in update.message.entities:
            if entity.type == "text_mention" and entity.user:
                target_id = entity.user.id
                user_name = entity.user.first_name or entity.user.username or f"Пользователь {target_id}"
                
                # Сохраняем username если есть
                if entity.user.username:
                    save_user_username(target_id, entity.user.username)
                break
            elif entity.type == "mention":
                start = entity.offset
                length = entity.length
                username = update.message.text[start+1:start + length]  # +1 чтобы убрать @
                user_name = f"@{username}"
                
                # Пытаемся найти пользователя разными способами
                user_found = False
                
                # Способ 1: Через get_chat (работает если пользователь взаимодействовал с ботом)
                try:
                    chat = await context.bot.get_chat(f"@{username}")
                    if chat and chat.id:
                        target_id = chat.id
                        user_name = chat.first_name or f"@{username}"
                        user_found = True
                        
                        # Сохраняем username
                        save_user_username(target_id, username)
                except Exception:
                    pass
                
                # Способ 2: Если это групповой чат, пытаемся через get_chat_member
                if not user_found and update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
                    try:
                        chat_member = await context.bot.get_chat_member(update.effective_chat.id, f"@{username}")
                        if chat_member and chat_member.user:
                            target_id = chat_member.user.id
                            user_name = chat_member.user.first_name or f"@{username}"
                            user_found = True
                            
                            # Сохраняем username
                            if chat_member.user.username:
                                save_user_username(target_id, chat_member.user.username)
                    except Exception:
                        pass
                
                # Способ 3: Поиск в сохраненных данных экономики по username
                if not user_found:
                    data = load_economy()
                    usernames = data.get("usernames", {})
                    if username in usernames:
                        target_id = usernames[username]
                        user_name = f"@{username}"
                        user_found = True
                
                # Если пользователь не найден
                if not user_found:
                    await update.message.reply_text(
                        f"❌ Не удалось найти пользователя @{username}.\n"
                        "Причина:\n"
                        "• Пользователь не взаимодействовал с ботом в личные сообщения\n"
                        "Используйте команду в ответ на сообщение этого пользователя."
                    )
                    return
                break
    
    # Проверяем аргументы команды (числовой ID)
    elif context.args and len(context.args) > 0:
        try:
            target_id = int(context.args[0])
            user_name = f"Пользователь {target_id}"
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя.")
            return
    
    # Если целевой пользователь не найден, показываем баланс текущего пользователя
    if not target_id:
        target_id = update.effective_user.id
        user_name = update.effective_user.first_name or "Пользователь"
    
    balance = get_user_balance(target_id)
    total_wealth = calculate_total_wealth(balance)
    slave_info = get_user_slave(target_id)
    
    # Проверяем, является ли пользователь рабом
    owner_id = get_slave_owner(target_id)
    
    # Формируем информацию о рабе или статусе рабства
    slave_display = "ничего"
    slavery_note = ""
    
    if owner_id:
        # Пользователь является рабом
        owner_slave_info = get_user_slave(owner_id)
        if owner_slave_info and owner_slave_info["slave_id"] == target_id:
            purchase_price = owner_slave_info["purchase_price"]
            
            # Пытаемся найти username владельца для создания ссылки
            data = load_economy()
            owner_username = None
            for username, user_id in data.get("usernames", {}).items():
                if user_id == owner_id:
                    owner_username = username
                    break
            
            # Создаем ссылку на профиль владельца
            owner_link = profile_link_html(owner_id, f"Владелец {owner_id}", owner_username)
            slave_display = f"Хозяин: {owner_link}"
            slavery_note = f"\n\n⛓️ <b>Статус рабства:</b>\n💰 Цена выкупа: {format_balance(purchase_price)}\n📝 <i>Пока вы раб, у вас не может быть рабов</i>"
    elif slave_info:
        # Пользователь имеет раба
        slave_id = slave_info["slave_id"]
        slave_name = slave_info["slave_name"]
        
        # Пытаемся найти username раба для создания ссылки
        data = load_economy()
        slave_username = None
        for username, user_id in data.get("usernames", {}).items():
            if user_id == slave_id:
                slave_username = username
                break
        
        # Создаем ссылку на профиль раба
        slave_link = profile_link_html(slave_id, slave_name, slave_username)
        slave_display = f"{slave_link} - раб"
    
    message = (
        f"💰 <b>Баланс {safe_html(user_name)}</b>\n\n"
        f"💵 Деньги: {format_balance(balance)}\n"
        f"💎 Общее состояние: {total_wealth} {CURRENCY_SYMBOL}\n\n"
        f"👥 <b>Вы имеете:</b>\n"
        f"📝 {slave_display}"
        f"{slavery_note}"
    )
    
    await update.message.reply_text(message, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_give_coins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ команда для выдачи монет пользователю."""
    if not await ensure_admin(update):
        return
    
    if not update.message:
        return
    
    # Получаем целевого пользователя
    target_id = extract_target_user_id_from_message(update.message)
    if not target_id:
        await update.message.reply_text(
            "Укажите пользователя и сумму:\n"
            "/give_coins <сумма> (ответом на сообщение)\n"
            "или /give_coins <user_id> <сумма>"
        )
        return
    
    # Парсим аргументы
    parts = (update.message.text or "").strip().split()
    if len(parts) < 2:
        await update.message.reply_text("Укажите сумму для выдачи.")
        return
    
    try:
        if len(parts) >= 3 and parts[1].isdigit():
            # Формат: /give_coins <user_id> <amount>
            amount = int(parts[2])
        else:
            # Формат: /give_coins <amount> (с reply/mention)
            amount = int(parts[1])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return
    
    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной.")
        return
    
    # Выдаем монеты
    old_balance = get_user_balance(target_id)
    new_balance = add_user_balance(target_id, amount)
    
    await update.message.reply_text(
        f"✅ Выдано {format_balance(amount)} пользователю {target_id}\n"
        f"Баланс: {format_balance(old_balance)} → {format_balance(new_balance)}"
    )


async def cmd_take_coins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ команда для снятия монет у пользователя."""
    if not await ensure_admin(update):
        return
    
    if not update.message:
        return
    
    # Получаем целевого пользователя
    target_id = extract_target_user_id_from_message(update.message)
    if not target_id:
        await update.message.reply_text(
            "Укажите пользователя и сумму:\n"
            "/take_coins <сумма> (ответом на сообщение)\n"
            "или /take_coins <user_id> <сумма>"
        )
        return
    
    # Парсим аргументы
    parts = (update.message.text or "").strip().split()
    if len(parts) < 2:
        await update.message.reply_text("Укажите сумму для снятия.")
        return
    
    try:
        if len(parts) >= 3 and parts[1].isdigit():
            # Формат: /take_coins <user_id> <amount>
            amount = int(parts[2])
        else:
            # Формат: /take_coins <amount> (с reply/mention)
            amount = int(parts[1])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return
    
    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной.")
        return
    
    # Снимаем монеты
    old_balance = get_user_balance(target_id)
    new_balance = add_user_balance(target_id, -amount)
    
    await update.message.reply_text(
        f"✅ Снято {format_balance(amount)} у пользователя {target_id}\n"
        f"Баланс: {format_balance(old_balance)} → {format_balance(new_balance)}"
    )


async def cmd_set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ команда для установки баланса пользователя."""
    if not await ensure_admin(update):
        return
    
    if not update.message:
        return
    
    # Получаем целевого пользователя
    target_id = extract_target_user_id_from_message(update.message)
    if not target_id:
        await update.message.reply_text(
            "Укажите пользователя и сумму:\n"
            "/set_balance <сумма> (ответом на сообщение)\n"
            "или /set_balance <user_id> <сумма>"
        )
        return
    
    # Парсим аргументы
    parts = (update.message.text or "").strip().split()
    if len(parts) < 2:
        await update.message.reply_text("Укажите новый баланс.")
        return
    
    try:
        if len(parts) >= 3 and parts[1].isdigit():
            # Формат: /set_balance <user_id> <amount>
            amount = int(parts[2])
        else:
            # Формат: /set_balance <amount> (с reply/mention)
            amount = int(parts[1])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return
    
    if amount < 0:
        await update.message.reply_text("Баланс не может быть отрицательным.")
        return
    
    # Устанавливаем баланс
    old_balance = get_user_balance(target_id)
    set_user_balance(target_id, amount)
    
    await update.message.reply_text(
        f"✅ Установлен баланс {format_balance(amount)} пользователю {target_id}\n"
        f"Было: {format_balance(old_balance)}"
    )


async def cmd_buy_slave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для покупки раба."""
    if not update.effective_user or not update.message:
        return
    
    buyer_id = update.effective_user.id
    
    # Получаем целевого пользователя
    target_id = extract_target_user_id_from_message(update.message)
    if not target_id:
        await update.message.reply_text(
            "Укажите пользователя и сумму:\n"
            "/buy_slave <сумма> (ответом на сообщение)\n"
            "или /buy_slave <user_id> <сумма>"
        )
        return
    
    # Парсим аргументы
    parts = (update.message.text or "").strip().split()
    if len(parts) < 2:
        await update.message.reply_text("Укажите сумму для покупки раба.")
        return
    
    try:
        if len(parts) >= 3 and parts[1].isdigit():
            # Формат: /buy_slave <user_id> <amount>
            amount = int(parts[2])
        else:
            # Формат: /buy_slave <amount> (с reply/mention)
            amount = int(parts[1])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return
    
    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной.")
        return
    
    # Проверяем возможность покупки раба
    can_buy, reason = can_buy_slave(buyer_id, target_id)
    if not can_buy:
        await update.message.reply_text(reason)
        return
    
    # Устанавливаем раба
    set_user_slave(buyer_id, target_id, amount, "Раб")
    
    # Снимаем деньги с покупателя
    add_user_balance(buyer_id, -amount)
    
    await update.message.reply_text(
        f"✅ Вы купили раба за {format_balance(amount)}!\n"
        f"Теперь вы владелец пользователя {target_id}"
    )


async def cmd_free_slave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для освобождения раба."""
    if not await ensure_admin(update):
        return
    
    if not update.message:
        return
    
    # Получаем владельца раба
    owner_id = extract_target_user_id_from_message(update.message)
    if not owner_id:
        await update.message.reply_text(
            "Укажите владельца раба:\n"
            "/free_slave (ответом на сообщение)\n"
            "или /free_slave <owner_id>"
        )
        return
    
    # Удаляем раба
    remove_user_slave(owner_id)
    
    await update.message.reply_text(
        f"✅ Раб пользователя {owner_id} освобожден."
    )


async def cmd_slave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /раб - покупка пользователя в рабство."""
    if not update.effective_user or not update.message:
        return
    
    buyer_id = update.effective_user.id
    
    if update.effective_user.username:
        save_user_username(update.effective_user.id, update.effective_user.username)
    
    target_id = None
    target_name = None
    
    # Сначала проверяем ответ на сообщение
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
        target_user = update.message.reply_to_message.from_user
        target_name = target_user.first_name or target_user.username or f"Пользователь {target_id}"
        
        # Сохраняем username если есть
        if target_user.username:
            save_user_username(target_id, target_user.username)
    
    # Затем проверяем упоминания в тексте
    elif update.message.entities:
        for entity in update.message.entities:
            if entity.type == "text_mention" and entity.user:
                target_id = entity.user.id
                target_name = entity.user.first_name or entity.user.username or f"Пользователь {target_id}"
                
                # Сохраняем username если есть
                if entity.user.username:
                    save_user_username(target_id, entity.user.username)
                break
            elif entity.type == "mention":
                start = entity.offset
                length = entity.length
                username = update.message.text[start+1:start + length]  # +1 чтобы убрать @
                target_name = f"@{username}"
                
                # Пытаемся найти пользователя разными способами
                user_found = False
                
                # Способ 1: Через get_chat (работает если пользователь взаимодействовал с ботом)
                try:
                    chat = await context.bot.get_chat(f"@{username}")
                    if chat and chat.id:
                        target_id = chat.id
                        target_name = chat.first_name or f"@{username}"
                        user_found = True
                        
                        # Сохраняем username
                        save_user_username(target_id, username)
                except Exception:
                    pass
                
                # Способ 2: Если это групповой чат, пытаемся через get_chat_member
                if not user_found and update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
                    try:
                        chat_member = await context.bot.get_chat_member(update.effective_chat.id, f"@{username}")
                        if chat_member and chat_member.user:
                            target_id = chat_member.user.id
                            target_name = chat_member.user.first_name or f"@{username}"
                            user_found = True
                            
                            # Сохраняем username
                            if chat_member.user.username:
                                save_user_username(target_id, chat_member.user.username)
                    except Exception:
                        pass
                
                # Способ 3: Поиск в сохраненных данных экономики по username
                if not user_found:
                    data = load_economy()
                    usernames = data.get("usernames", {})
                    if username in usernames:
                        target_id = usernames[username]
                        target_name = f"@{username}"
                        user_found = True
                
                # Если пользователь не найден
                if not user_found:
                    await update.message.reply_text(
                        f"❌ Не удалось найти пользователя @{username}.\n"
                        "Причина:\n"
                        "• Пользователь не взаимодействовал с ботом в личные сообщения\n"
                        "Используйте команду в ответ на сообщение этого пользователя."
                    )
                    return
                break
    
    # Если целевой пользователь не найден
    if not target_id:
        await update.message.reply_text(
            "❌ Укажите пользователя для покупки в рабство:\n"
            "• /раб @username\n"
            "• /раб (в ответ на сообщение пользователя)"
        )
        return
    
    # Проверяем возможность покупки раба
    can_buy, reason = can_buy_slave(buyer_id, target_id)
    if not can_buy:
        await update.message.reply_text(reason)
        return
    
    # Рассчитываем стоимость (общее состояние цели)
    target_balance = get_user_balance(target_id)
    purchase_price = int(calculate_total_wealth(target_balance))
    
    set_user_slave(buyer_id, target_id, purchase_price, target_name)
    add_user_balance(buyer_id, -purchase_price)
    
    buyer_name = update.effective_user.first_name or "Пользователь"
    
    await update.message.reply_text(
        f"🔗 <b>Покупка в рабство!</b>\n\n"
        f"👤 <b>{safe_html(buyer_name)}</b> купил в рабство <b>{safe_html(target_name)}</b>\n"
        f"💰 Стоимость: {format_balance(purchase_price)}\n\n"
        f"📋 <b>Условия выкупа:</b>\n"
        f"💵 {safe_html(target_name)} может выкупить себя за {format_balance(purchase_price)}\n"
        f"⏰ Цена выкупа зафиксирована на момент покупки",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


async def cmd_buyout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /выкуп - раб выкупает себя из рабства."""
    if not update.effective_user or not update.message:
        return
    
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь рабом
    owner_id = get_slave_owner(user_id)
    if not owner_id:
        await update.message.reply_text(
            "❌ <b>Вы не являетесь рабом!</b>\n\n"
            "💡 Эта команда доступна только для тех, кто находится в рабстве.",
            parse_mode="HTML"
        )
        return
    
    # Получаем информацию о рабстве
    slave_info = get_user_slave(owner_id)
    if not slave_info or slave_info["slave_id"] != user_id:
        await update.message.reply_text(
            "❌ Ошибка в данных рабства. Обратитесь к администратору."
        )
        return
    
    purchase_price = slave_info["purchase_price"]
    user_balance = get_user_balance(user_id)
    
    # Проверяем, хватает ли денег для выкупа
    if user_balance < purchase_price:
        await update.message.reply_text(
            f"💰 <b>Недостаточно средств для выкупа!</b>\n\n"
            f"💵 Ваш баланс: {format_balance(user_balance)}\n"
            f"💎 Нужно для выкупа: {format_balance(purchase_price)}\n"
            f"📈 Не хватает: {format_balance(purchase_price - user_balance)}\n\n"
            f"💪 Продолжайте работать, чтобы заработать недостающую сумму!",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return
    
    # Выкупаем раба
    add_user_balance(user_id, -purchase_price)
    remove_user_slave(owner_id)
    
    user_name = update.effective_user.first_name or "Пользователь"
    
    # Уведомляем раба об успешном выкупе
    await update.message.reply_text(
        f"🎉 <b>СВОБОДА!</b>\n\n"
        f"✅ <b>{safe_html(user_name)}</b>, вы успешно выкупили себя из рабства!\n"
        f"💰 Потрачено: {format_balance(purchase_price)}\n"
        f"💵 Остаток: {format_balance(get_user_balance(user_id))}\n\n"
        f"🕊️ <i>Поздравляем с обретением свободы!</i>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    # Уведомляем владельца о потере раба
    try:
        await context.bot.send_message(
            chat_id=owner_id,
            text=f"💔 <b>Ваш раб выкупил свободу!</b>\n\n"
                 f"👤 <b>{safe_html(user_name)}</b> выкупил себя из рабства\n"
                 f"💰 За сумму: {format_balance(purchase_price)}\n\n"
                 f"🔍 Теперь вы можете найти нового раба!",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception:
        # Если не удалось отправить уведомление владельцу, это не критично
        pass


async def cmd_slave_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /инфо_раб - показывает информацию о рабстве пользователя."""
    if not update.effective_user or not update.message:
        return
    
    user_id = update.effective_user.id
    
    # Проверяем, есть ли у пользователя раб
    slave_info = get_user_slave(user_id)
    if slave_info:
        slave_id = slave_info["slave_id"]
        slave_name = slave_info["slave_name"]
        purchase_price = slave_info["purchase_price"]
        
        # Пытаемся найти username раба для создания ссылки
        data = load_economy()
        slave_username = None
        for username, uid in data.get("usernames", {}).items():
            if uid == slave_id:
                slave_username = username
                break
        
        slave_link = profile_link_html(slave_id, slave_name, slave_username)
        
        await update.message.reply_text(
            f"👑 <b>Информация о вашем рабе:</b>\n\n"
            f"👤 Раб: {slave_link}\n"
            f"💰 Стоимость покупки: {format_balance(purchase_price)}\n"
            f"💵 Текущий баланс раба: {format_balance(get_user_balance(slave_id))}\n\n"
            f"📋 <b>Условия выкупа:</b>\n"
            f"💎 Раб может выкупить себя за {format_balance(purchase_price)}\n"
            f"⚠️ Если у раба будет достаточно денег, он сможет использовать /выкуп",
            parse_mode="HTML"
        )
        return
    
    # Проверяем, является ли пользователь рабом
    owner_id = get_slave_owner(user_id)
    if owner_id:
        # Получаем информацию о владельце
        owner_slave_info = get_user_slave(owner_id)
        if owner_slave_info and owner_slave_info["slave_id"] == user_id:
            purchase_price = owner_slave_info["purchase_price"]
            user_balance = get_user_balance(user_id)
            
            # Пытаемся найти информацию о владельце
            data = load_economy()
            owner_username = None
            for username, uid in data.get("usernames", {}).items():
                if uid == owner_id:
                    owner_username = username
                    break
            
            owner_link = profile_link_html(owner_id, f"Владелец {owner_id}", owner_username)
            
            await update.message.reply_text(
                f"⛓️ <b>Вы находитесь в рабстве:</b>\n\n"
                f"👤 Владелец: {owner_link}\n"
                f"💰 Цена выкупа: {format_balance(purchase_price)}\n"
                f"💵 Ваш баланс: {format_balance(user_balance)}\n"
                f"📈 До свободы: {format_balance(max(0, purchase_price - user_balance))}\n\n"
                f"💪 <b>Как получить свободу:</b>\n"
                f"• Заработайте {format_balance(purchase_price)} с помощью /work\n"
                f"• Используйте команду /выкуп когда накопите нужную сумму\n\n"
                f"🎯 {'✅ Можете выкупиться прямо сейчас!' if user_balance >= purchase_price else '❌ Пока недостаточно средств для выкупа'}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка в данных рабства. Обратитесь к администратору."
            )
        return
    
    # Пользователь свободен
    await update.message.reply_text(
        f"🕊️ <b>Вы свободны!</b>\n\n"
        f"✅ Вы не являетесь рабом и не имеете рабов\n"
        f"💡 Используйте /раб @username чтобы купить кого-то в рабство",
        parse_mode="HTML"
    )


async def cmd_free_slave_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /освободить_раба - освобождает раба без возврата денег."""
    if not update.effective_user or not update.message:
        return
    
    owner_id = update.effective_user.id
    
    # Проверяем, есть ли у пользователя раб
    slave_info = get_user_slave(owner_id)
    if not slave_info:
        await update.message.reply_text(
            "❌ <b>У вас нет раба!</b>\n\n"
            "💡 Используйте /раб @username чтобы купить кого-то в рабство.",
            parse_mode="HTML"
        )
        return
    
    slave_id = slave_info["slave_id"]
    slave_name = slave_info["slave_name"]
    purchase_price = slave_info["purchase_price"]
    
    # Пытаемся найти username раба для создания ссылки
    data = load_economy()
    slave_username = None
    for username, user_id in data.get("usernames", {}).items():
        if user_id == slave_id:
            slave_username = username
            break
    
    slave_link = profile_link_html(slave_id, slave_name, slave_username)
    
    # Освобождаем раба
    remove_user_slave(owner_id)
    
    owner_name = update.effective_user.first_name or "Пользователь"
    
    # Уведомляем владельца об освобождении раба
    await update.message.reply_text(
        f"🕊️ <b>Раб освобожден!</b>\n\n"
        f"✅ Вы освободили {slave_link}\n"
        f"💰 Потраченные на покупку {format_balance(purchase_price)} не возвращаются\n\n"
        f"🔍 Теперь вы можете найти нового раба!",
        parse_mode="HTML", 
        disable_web_page_preview=True
    )
    
    # Уведомляем бывшего раба об освобождении
    try:
        await context.bot.send_message(
            chat_id=slave_id,
            text=f"🎉 <b>ВЫ СВОБОДНЫ!</b>\n\n"
                 f"✅ <b>{safe_html(owner_name)}</b> освободил вас из рабства!\n"
                 f"🕊️ <i>Поздравляем с обретением свободы!</i>\n\n"
                 f"💡 Теперь вы можете покупать рабов сами!",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception:
        # Если не удалось отправить уведомление бывшему рабу, это не критично
        pass
