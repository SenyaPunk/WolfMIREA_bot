import random
import time
import re
from typing import Dict, Any, Optional, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from storage import load_cooldowns, save_cooldowns

# Максимальное количество выпитого
MAX_DRINKS = 5

# Кулдаун между использованиями команды (в секундах)
DRINKING_COOLDOWN = 3600  # 60 минут

# Типы алкоголя
DRINKS = {
    "jager": {"name": "Ягерь", "emoji": "🟤", "strength": 1.2},
    "cognac": {"name": "Коньяк", "emoji": "🥃", "strength": 1.0},
    "gin": {"name": "Джин", "emoji": "🍸", "strength": 0.8},
    "absinthe": {"name": "Абсент", "emoji": "🟢", "strength": 1.5}
}

# Сообщения по уровням опьянения
DRUNK_MESSAGES = {
    0: {
        "text": "🍺 че нальем в глотку?\nвыбирай хрень какую-нибудь, чтоб вштырило",
        "effects": []
    },
    1: {
        "text": "ммм, бля, заебись пошло\n😊 тепло разливается по кишкам, настроение - пиздец как прёт вверх",
        "effects": ["ебанутый кайф в башке", "улыбка до ушей"]
    },
    2: {
        "text": "ахзвыха, сука, уже в теме!\n мир засиял хуевой радугой, анекдоты рвут пузо, а я чуть не упал от смеха блять",
        "effects": ["дикий ржач", "шатаюсь как хуй в проруби", "веселье на полную"]
    },
    3: {
        "text": "<b>ооо, бля щас заебато пойдет...</b>\nяз<b>ы</b>к заплетается в <b>узел</b>, стены пляшут как шлюхи <b>н</b>о я еще стою",
        "effects": ["пиздец в словах", "стены в танце", "ноги как ватные хуи"]
    },
    4: {
        "text": "<i>бляяяя... кто</i>, сук<i>а</i>, крутит этот ебаный м<b>ир</b>\n\n все вертится как в <i>мясоруб</i>ке, бормочу хуйню, но еще не <b>рухн</b>ул...",
        "effects": ["голову рвет на части", "речь как у дебила", "координация в жопе"]
    },
    5: {
        "text": "🤢 <b>уууух, бля... все, н</b>ахуй, завяз<i>ыва</i>ю...\n\n мир - сплош<i>ной</i> пиздец в карусели, ноги не держат, блевать тянет",
        "effects": ["тошнит как после помойки", "в глазах два мира", "полный пиздец с равновесием"]
    }
}


def get_drinking_cooldown_key(user_id: int, chat_id: int) -> str:
    return f"drink_{user_id}_{chat_id}"


def check_drinking_cooldown(user_id: int, chat_id: int) -> Optional[float]:
    cooldowns = load_cooldowns()
    key = get_drinking_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        return None
    
    last_drink = cooldowns[key].get("last_session", 0)
    current_time = time.time()
    time_passed = current_time - last_drink
    
    if time_passed >= DRINKING_COOLDOWN:
        return None
    
    return DRINKING_COOLDOWN - time_passed


def set_drinking_cooldown(user_id: int, chat_id: int) -> None:
    cooldowns = load_cooldowns()
    key = get_drinking_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    cooldowns[key]["last_session"] = time.time()
    save_cooldowns(cooldowns)


def format_time_remaining(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes > 0:
        return f"{minutes} мин."
    else:
        return f"{int(seconds)} сек."


def create_drink_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру выбора напитков"""
    buttons = []
    row = []
    
    for drink_id, drink_info in DRINKS.items():
        button = InlineKeyboardButton(
            f"{drink_info['emoji']} {drink_info['name']}", 
            callback_data=f"drink:{user_id}:{drink_id}:1"
        )
        row.append(button)
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    return InlineKeyboardMarkup(buttons)


def create_continue_keyboard(user_id: int, drink_type: str, level: int) -> InlineKeyboardMarkup:
    """Создать клавиатуру для продолжения питья"""
    if level >= MAX_DRINKS:
        return InlineKeyboardMarkup([])
    
    drink_info = DRINKS.get(drink_type, DRINKS["cognac"])
    button = InlineKeyboardButton(
        f"🍻 Выпить еще {drink_info['name']}?", 
        callback_data=f"drink:{user_id}:{drink_type}:{level + 1}"
    )
    
    return InlineKeyboardMarkup([[button]])


def parse_html_segments(text: str) -> List[Dict[str, Any]]:
    """Разбить текст на сегменты с информацией о форматировании"""
    segments = []
    current_pos = 0
    
    # Находим все HTML теги
    tag_pattern = r'<(/?)([bi])>'
    matches = list(re.finditer(tag_pattern, text))
    
    for match in matches:
        # Добавляем текст до тега
        if match.start() > current_pos:
            plain_text = text[current_pos:match.start()]
            if plain_text:
                segments.append({
                    'type': 'text',
                    'content': plain_text,
                    'formatting': []
                })
        
        # Добавляем тег
        is_closing = match.group(1) == '/'
        tag_type = match.group(2)
        segments.append({
            'type': 'tag',
            'tag_type': tag_type,
            'is_closing': is_closing,
            'content': match.group(0)
        })
        
        current_pos = match.end()
    
    # Добавляем оставшийся текст
    if current_pos < len(text):
        remaining_text = text[current_pos:]
        if remaining_text:
            segments.append({
                'type': 'text',
                'content': remaining_text,
                'formatting': []
            })
    
    return segments


def apply_drunk_effect_to_text(text: str, level: int) -> str:
    """Применить эффекты опьянения только к тексту (без HTML)"""
    if level < 3:
        return text
    
    drunk_text = text
    
    if level >= 3:
        # Замена некоторых букв
        replacements = {
            'с': 'ш', 'з': 'ж', 'т': 'ц', 'п': 'б'
        }
        for old, new in replacements.items():
            if random.random() < 0.3:  # 30% шанс замены
                drunk_text = drunk_text.replace(old, new)
    
    if level >= 4:
        # Добавление лишних букв
        words = drunk_text.split()
        for i, word in enumerate(words):
            if random.random() < 0.4 and len(word) > 3:
                # Удваиваем случайную букву
                pos = random.randint(1, len(word) - 1)
                words[i] = word[:pos] + word[pos] + word[pos:]
        drunk_text = ' '.join(words)
    
    if level >= 4:
        # Добавление междометий между словами (реже и в курсиве)
        interjections = ['хик', 'ууух', 'блин', 'ой', 'эээ']
        if random.random() < 0.25:  # Только 25% шанс добавления междометия
            # Находим все пробелы в тексте
            words = drunk_text.split(' ')
            if len(words) > 1:  # Есть хотя бы два слова
                # Выбираем случайную позицию между словами
                insert_pos = random.randint(1, len(words) - 1)
                # Вставляем междометие с пробелами
                interjection = f"<i>{random.choice(interjections)}</i>"
                words.insert(insert_pos, interjection)
                drunk_text = ' '.join(words)
    
    if level >= 5:
        # Максимальное опьянение - много ошибок
        drunk_text = drunk_text.replace('о', 'а').replace('е', 'и')
        if random.random() < 0.3:  # Уменьшили шанс с 50% до 30%
            drunk_text += " <i>икает</i>"
    
    return drunk_text


def reconstruct_html_text(segments: List[Dict[str, Any]], level: int) -> str:
    """Восстановить HTML текст с примененными эффектами опьянения"""
    result = ""
    
    for segment in segments:
        if segment['type'] == 'text':
            # Применяем эффекты опьянения только к текстовым сегментам
            processed_text = apply_drunk_effect_to_text(segment['content'], level)
            result += processed_text
        elif segment['type'] == 'tag':
            # HTML теги добавляем как есть
            result += segment['content']
    
    return result


def validate_html_tags(text: str) -> str:
    """Проверить и исправить HTML теги"""
    # Стек для отслеживания открытых тегов
    tag_stack = []
    result = ""
    
    # Находим все теги
    tag_pattern = r'<(/?)([bi])>'
    last_pos = 0
    
    for match in re.finditer(tag_pattern, text):
        # Добавляем текст до тега
        result += text[last_pos:match.start()]
        
        is_closing = match.group(1) == '/'
        tag_type = match.group(2)
        
        if is_closing:
            # Закрывающий тег
            if tag_stack and tag_stack[-1] == tag_type:
                tag_stack.pop()
                result += match.group(0)
            # Если тег не соответствует последнему открытому, игнорируем его
        else:
            # Открывающий тег
            tag_stack.append(tag_type)
            result += match.group(0)
        
        last_pos = match.end()
    
    # Добавляем оставшийся текст
    result += text[last_pos:]
    
    # Закрываем все незакрытые теги
    while tag_stack:
        tag = tag_stack.pop()
        result += f"</{tag}>"
    
    return result


def apply_drunk_effect(text: str, level: int, drink_type: str) -> str:
    """Применить эффекты опьянения к тексту с сохранением HTML"""
    if level < 3:
        return text
    
    try:
        # Разбираем текст на сегменты
        segments = parse_html_segments(text)
        
        # Восстанавливаем текст с примененными эффектами
        result = reconstruct_html_text(segments, level)
        
        # Проверяем и исправляем HTML теги
        result = validate_html_tags(result)
        
        return result
    
    except Exception as e:
        # В случае ошибки возвращаем оригинальный текст
        print(f"Error in apply_drunk_effect: {e}")
        return text


async def cmd_drink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /выпить"""
    message = update.message
    if not message or not update.effective_user:
        return
    
    user = update.effective_user
    chat_id = message.chat.id
    
    # Проверяем кулдаун
    remaining_time = check_drinking_cooldown(user.id, chat_id)
    if remaining_time is not None:
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except Exception as e:
            print(f"Failed to delete user message: {e}")
        
        # Отправляем предупреждение
        warning_msg = await context.bot.send_message(
            chat_id,
            f"🚫 <b>Вы еще не протрезвели!</b>\n\n"
            f"⏰ Попробуйте снова через {format_time_remaining(remaining_time)}\n"
            f"💡 <i>Нужно время, чтобы восстановиться...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Удаляем предупреждение через 3 секунды
        async def delete_warning(context):
            try:
                await context.bot.delete_message(chat_id, warning_msg.message_id)
            except Exception as e:
                print(f"Failed to delete warning message: {e}")
        
        context.job_queue.run_once(delete_warning, 3)
        return
    
    # Создаем сообщение с выбором напитков
    keyboard = create_drink_keyboard(user.id)
    
    await message.reply_text(
        DRUNK_MESSAGES[0]["text"],
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )


async def cb_drink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопок питья"""
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, user_id_str, drink_type, level_str = query.data.split(":")
        user_id = int(user_id_str)
        level = int(level_str)
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка обработки команды.")
        return
    
    # Проверяем, что кнопку нажал тот же пользователь
    if query.from_user.id != user_id:
        await query.answer("🚫 Это не ваш напиток!", show_alert=True)
        return
    
    # Проверяем лимит
    if level > MAX_DRINKS:
        await query.answer("🤢 Хватит! Вы уже выпили слишком много!", show_alert=True)
        return
    
    # Получаем информацию о напитке
    drink_info = DRINKS.get(drink_type, DRINKS["cognac"])
    
    # Создаем сообщение об опьянении
    base_message = DRUNK_MESSAGES[level]["text"]
    
    # Применяем эффекты опьянения к тексту (начиная с 3-го уровня)
    drunk_message = apply_drunk_effect(base_message, level, drink_type)
    
    full_message = drunk_message 
    
    # Создаем клавиатуру для продолжения (если не достигнут лимит)
    keyboard = create_continue_keyboard(user_id, drink_type, level)
    
    # Если достигнут максимум, устанавливаем кулдаун
    if level >= MAX_DRINKS:
        set_drinking_cooldown(user_id, query.message.chat.id)
        full_message += f"\n\n🚫 <b>Всё, хватит на сегодня!</b>\n⏰ <i>Следующая попойка через {DRINKING_COOLDOWN // 60} минут</i>"
    
    try:
        await query.edit_message_text(
            full_message,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        # В случае ошибки отправляем сообщение без HTML форматирования
        try:
            # Удаляем все HTML теги для безопасности
            safe_message = re.sub(r'<[^>]+>', '', full_message)
            await query.edit_message_text(
                safe_message,
                reply_markup=keyboard
            )
        except Exception:
            # Если и это не работает, отправляем новое сообщение
            safe_message = re.sub(r'<[^>]+>', '', full_message)
            await query.message.reply_text(
                safe_message,
                reply_markup=keyboard
            )
