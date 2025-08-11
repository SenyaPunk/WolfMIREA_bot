"""Конфигурация и константы бота."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Пути к файлам данных
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_FILE = DATA_DIR / "subscribers.json"       
MARRIAGE_FILE = DATA_DIR / "marriages.json"       
ADMINS_FILE = DATA_DIR / "admins.json"
COOLDOWNS_FILE = DATA_DIR / "cooldowns.json"

# Настройки по умолчанию
DEFAULT_TZ = "Europe/Moscow"
DEFAULT_MORNING = "08:00"
DEFAULT_EVENING = "22:00"

# Зарезервированные команды
RESERVED_COMMANDS = {
    "start", "help",
    "stop",
    "set_morning", "set_evening", "set_timezone", "settings", "preview",
    "marry", "marriages", "divorce",
    "брак", "браки", "развод", "трахнуть",
    "admin_claim", "admins", "admin_add", "admin_remove",
    "cc_set", "cc_set_photo", "cc_remove", "cc_list"
}

# Константы для системы браков
MARRY_DEEPLINK_PREFIX = "marry_"

# Токен бота
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Текст помощи
HELP_TEXT = """
🤖 Бот волчара с котиками и пожеланиями

Основные команды:
• /start — подписаться на пожелания (только админы)
• /stop — отписаться
• /settings — текущие настройки
• /preview [morning/evening] — превью поста

Настройки времени:
• /set_morning HH:MM — время утреннего поста
• /set_evening HH:MM — время вечернего поста  
• /set_timezone Area/City — часовой пояс

Система браков:
• /брак — предложить брак (ответом на сообщение)
• /браки — список пар в чате
• /развод — развестись
• /трахнуть — трахнуть пользователя в чате


Админские команды:
• /admin_claim — стать владельцем (только в ЛС)
• /admins — список админов
• /admin_add — добавить админа
• /admin_remove — удалить админа

Кастомные команды:
• /cc_set <команда> <текст> — создать текстовую команду
• /cc_set_photo <команда> <url> [| подпись] — создать команду с фото
• /cc_remove <команда> — удалить команду
• /cc_list — список команд
"""
