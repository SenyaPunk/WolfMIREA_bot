"""Вспомогательные функции."""
import re
from datetime import datetime
from typing import Optional


def safe_html(text: str) -> str:
    """Экранирует HTML символы."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mention_html(user_id: int, name: str) -> str:
    """Создает HTML упоминание пользователя."""
    return f'<a href="tg://user?id={user_id}">{safe_html(name)}</a>'


def display_name_from_user(user) -> str:
    """Получает отображаемое имя пользователя."""
    if getattr(user, "full_name", ""):
        return user.full_name
    if getattr(user, "username", ""):
        return f"@{user.username}"
    return f"User {getattr(user, "id", "???")}"


def normalize_cmd_name(s: str) -> str:
    """Нормализует имя команды."""
    s = s.strip()
    if s.startswith("/"):
        s = s[1:]
    if "@" in s:
        s = s.split("@", 1)[0]
    return s.strip().lower()


def parse_time_hhmm(s: str) -> Optional[datetime]:
    """Парсит время в формате HH:MM."""
    if not re.match(r"^\d{1,2}:\d{2}$", s):
        return None
    try:
        h, m = map(int, s.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    except ValueError:
        return None


def build_caption(kind: str, text: str) -> str:
    """Создает подпись для поста."""
    emoji = "🌅" if kind == "morning" else "🌙"
    return f"{emoji} {text}"


def format_timestamp(ts: int) -> str:
    """Форматирует timestamp в читаемый вид."""
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(ts)


def get_target_user(message, args):
    """Извлекает целевого пользователя из сообщения или аргументов команды."""
    if not message:
        return None
    
    # Проверяем reply_to_message
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    
    # Проверяем entities на text_mention и mention
    if message.entities:
        for entity in message.entities:
            if entity.type == "text_mention" and entity.user:
                return entity.user
            elif entity.type == "mention":
                # Извлекаем username из текста сообщения
                start = entity.offset
                length = entity.length
                username = message.text[start:start + length]
                if username.startswith('@'):
                    username = username[1:]  # Убираем @
                
                # Ищем пользователя по username среди участников чата
                # Возвращаем объект с username для дальнейшей обработки
                class UserStub:
                    def __init__(self, username):
                        self.username = username
                        self.id = None
                        self.first_name = f"@{username}"
                        self.full_name = f"@{username}"
                
                return UserStub(username)
    
    return None
