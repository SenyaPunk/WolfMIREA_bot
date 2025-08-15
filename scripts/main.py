import os
import asyncio
import time
import json
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from typing import Dict, Optional

API_ID = 23651537
API_HASH = '9b6eb8e2dc96f17e0bc724668ed5f56d'
STRING_SESSION = os.getenv('TELEGRAM_STRING_SESSION', None)
DEVICE_MODEL = 'Samsung Galaxy S23'
SYSTEM_VERSION = 'Android 13'
APP_VERSION = '9.5.0'

BIRTHDAY_COOLDOWN = 5400  # 1.5 часа (90 минут)
COOLDOWNS_FILE = 'birthday_cooldowns.json'

BIRTHDAY_GIRL_ID = 1184578059  # Замените на ID аккаунта Жаннет
birthday_girl_used = False  # Флаг, показывающий использовала ли именинница команду

BIRTHDAY_SLIDES = [
    "🤍\n\
🤍\n\
🤍",
    
    "🤍🤍\n\
🤍🤍\n\
🤍🤍\n\
🤍🤍",
    
    "🤍🤍🤍\n\
🤍🤍🤍\n\
🤍🤍🤍\n\
🤍🤍🤍\n\
🤍🤍🤍",
    
    "🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍",
    
    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",
    
    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💖🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍🤍🤍💖🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍🤍🤍💖🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍🤍🤍💖🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍🤍🤍💖🤍🤍🤍",

    "🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍🤍💖💖💖🤍🤍",

    "🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖💖💖💖💖🤍",

    "🤍💗🤍💗🤍💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍",

    "🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖🤍💖🤍🤍",

    "🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💕🤍🤍🤍💕🤍\n\
🤍💕🤍🤍🤍💕🤍\n\
🤍💕🤍🤍🤍💕🤍\n\
🤍💕💕💕💕💕🤍\n\
🤍💕🤍🤍🤍💕🤍\n\
🤍💕🤍🤍🤍💕🤍\n\
🤍💕🤍🤍🤍💕🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💖💖💖🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍🤍💖🤍💖🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖💖💖💖🤍🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍🤍🤍\n\
🤍💖💖💖💖💖🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖💖🤍💖💖🤍\n\
🤍💖🤍💖🤍💖🤍\n\
🤍💖🤍💖🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍💖🤍🤍🤍💖🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗🤍🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗💗💗💗🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍💗💗🤍\n\
🤍💗🤍🤍💗💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗🤍💗🤍💗🤍\n\
🤍💗💗🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗💗💗💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍💗💗💗💗🤍\n\
🤍🤍🤍💗🤍💗🤍\n\
🤍🤍💗🤍🤍💗🤍\n\
🤍💗🤍🤍🤍💗🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍🤍💗💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍🤍🤍💗💗🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍💖🤍🤍🤍💖🤍\n\
💖💕💕💕💕💕💖\n\
💕💕💗💕💗💕💕\n\
💕💗💗💗💗💗💕\n\
💕💗💗💗💗💗💕\n\
💕💕💗💗💗💕💕\n\
💖💕💕💗💕💕💖\n\
🤍💖💕💕💕💖🤍\n\
🤍🤍💖💕💖🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍💕💕💕💕💕🤍\n\
💕💕💗💕💗💕💕\n\
💕💗💗💗💗💗💕\n\
💕💗💗💗💗💗💕\n\
💕💕💗💗💗💕💕\n\
🤍💕💕💗💕💕🤍\n\
🤍🤍💕💕💕🤍🤍\n\
🤍🤍🤍💕🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍💗💗💗💗💗🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍💗🤍💗🤍🤍\n\
🤍🤍💗💗💗🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍💗🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍\n\
🤍🤍🤍🤍🤍🤍🤍",

    "🤍🤍🤍🤍🤍🤍🤍",

    "Ж",
    "Жа",
    "Жан",
    "Жанн",
    "Жанне", 
    "Жаннет, ", 
    "Жаннет, п",
    "Жаннет, по",
    "Жаннет, поз",
    "Жаннет, позд",
    "Жаннет, поздр",
    "Жаннет, поздра",
    "Жаннет, поздрав",
    "Жаннет, поздравл",
    "Жаннет, поздравля",
    "Жаннет, поздравляе",
    "Жаннет, поздравляем",
    "Жаннет, поздравляем с",
    "Жаннет, поздравляем с д",
    "Жаннет, поздравляем с дн",
    "Жаннет, поздравляем с дне",
    "Жаннет, поздравляем с днем",
    "Жаннет, поздравляем с днем р",
    "Жаннет, поздравляем с днем ро",
    "Жаннет, поздравляем с днем рож", 
    "Жаннет, поздравляем с днем рожд",    
    "Жаннет, поздравляем с днем рожде",    
    "Жаннет, поздравляем с днем рожден",    
    "Жаннет, поздравляем с днем рождени",    
    "Жаннет, поздравляем с днем рождения",    
    "Жаннет, поздравляем с днем рождения!",    
    "Жаннет, поздравляем с днем рождения! М",   
    "Жаннет, поздравляем с днем рождения! Мы",  
    "Жаннет, поздравляем с днем рождения! Мы т",    
    "Жаннет, поздравляем с днем рождения! Мы те",  
    "Жаннет, поздравляем с днем рождения! Мы теб",    
    "Жаннет, поздравляем с днем рождения! Мы тебя",    
    "Жаннет, поздравляем с днем рождения! Мы тебя л",    
    "Жаннет, поздравляем с днем рождения! Мы тебя лю",    
    "Жаннет, поздравляем с днем рождения! Мы тебя люб",    
    "Жаннет, поздравляем с днем рождения! Мы тебя люби",    
    "Жаннет, поздравляем с днем рождения! Мы тебя любим",    
    "Жаннет, поздравляем с днем рождения! Мы тебя любим ❤️",    
    "Жаннет, поздравляем с днем рождения! Мы тебя любим ❤️❤️",
    "Жаннет, поздравляем с днем рождения! Мы тебя любим ❤️❤️❤️",    
    "Жаннет, поздравляем с днем рождения! Мы тебя любим ❤️❤️❤️",    
]

session = StringSession(STRING_SESSION) if STRING_SESSION else 'birthday_userbot'
client = TelegramClient(
    session,
    API_ID,
    API_HASH,
    device_model=DEVICE_MODEL,
    system_version=SYSTEM_VERSION,
    app_version=APP_VERSION
)

def load_cooldowns() -> Dict:
    """Загружает кулдауны из файла"""
    try:
        with open(COOLDOWNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_cooldowns(cooldowns: Dict) -> None:
    """Сохраняет кулдауны в файл"""
    try:
        with open(COOLDOWNS_FILE, 'w', encoding='utf-8') as f:
            json.dump(cooldowns, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save cooldowns: {e}")

def get_birthday_cooldown_key(user_id: int, chat_id: int) -> str:
    """Генерирует ключ для кулдауна команды день рождения"""
    return f"birthday_{user_id}_{chat_id}"

def check_birthday_cooldown(user_id: int, chat_id: int) -> Optional[float]:
    """Проверяет кулдаун команды день рождения"""
    cooldowns = load_cooldowns()
    key = get_birthday_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        return None
    
    last_birthday = cooldowns[key].get("last_use", 0)
    current_time = time.time()
    time_passed = current_time - last_birthday
    
    if time_passed >= BIRTHDAY_COOLDOWN:
        return None
    
    return BIRTHDAY_COOLDOWN - time_passed

def set_birthday_cooldown(user_id: int, chat_id: int) -> None:
    """Устанавливает кулдаун для команды день рождения"""
    cooldowns = load_cooldowns()
    key = get_birthday_cooldown_key(user_id, chat_id)
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    cooldowns[key]["last_use"] = time.time()
    save_cooldowns(cooldowns)

def format_time_remaining(seconds: float) -> str:
    """Форматирует оставшееся время кулдауна"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    elif minutes > 0:
        return f"{minutes} мин."
    else:
        return f"{int(seconds)} сек."

@client.on(events.NewMessage)
async def birthday_handler(event):
    """Обработчик сообщения "с днем рождения меня" - интерактивное поздравление с днем рождения"""
    # Проверяем, содержит ли сообщение нужный текст (регистронезависимо)
    if not event.message.text or "с днем рождения меня" not in event.message.text.lower():
        return
    
    user_id = event.sender_id
    chat_id = event.chat_id
    
    global birthday_girl_used
    if not birthday_girl_used and user_id != BIRTHDAY_GIRL_ID:
        # Удаляем сообщение пользователя
        try:
            await event.delete()
        except Exception as e:
            print(f"Failed to delete user message: {e}")
        
        # Отправляем сообщение об ошибке
        error_msg = await client.send_message(
            chat_id,
            "❌ **Вы не Жаннет!**\n\n"
            "🎂 Сначала именинница должна использовать команду!"
        )
        
        # Удаляем сообщение об ошибке через 5 секунд
        await asyncio.sleep(5)
        try:
            await error_msg.delete()
        except Exception as e:
            print(f"Failed to delete error message: {e}")
        return
    
    # Проверяем кулдаун
    remaining_time = check_birthday_cooldown(user_id, chat_id)
    if remaining_time is not None:
        # Удаляем сообщение пользователя
        try:
            await event.delete()
        except Exception as e:
            print(f"Failed to delete user message: {e}")
        
        # Отправляем предупреждение о кулдауне
        warning_msg = await client.send_message(
            chat_id,
            f"🎂 **Чуть-чуть надо подождать=)**\n\n"
            f"⏰ Следующее поздравление через {format_time_remaining(remaining_time)}\n"
        )
        
        # Удаляем предупреждение через 5 секунд
        await asyncio.sleep(5)
        try:
            await warning_msg.delete()
        except Exception as e:
            print(f"Failed to delete warning message: {e}")
        return
    
    # Удаляем сообщение пользователя
    try:
        await event.delete()
    except Exception as e:
        print(f"Failed to delete user message: {e}")
    
    # Устанавливаем кулдаун
    set_birthday_cooldown(user_id, chat_id)
    
    # Отправляем первый слайд
    birthday_msg = await client.send_message(chat_id, BIRTHDAY_SLIDES[0])
    
    start_time = time.time()
    animation_duration = 120  # 1 минута
    slide_delay = 0.5  # Пауза между слайдами (увеличена для избежания flood control)
    current_slide = 0
    
    while time.time() - start_time < animation_duration:
        await asyncio.sleep(slide_delay)
        
        # Переходим к следующему слайду (кроме последнего - финального)
        current_slide = (current_slide + 1) % (len(BIRTHDAY_SLIDES) - 1)
        
        try:
            await birthday_msg.edit(BIRTHDAY_SLIDES[current_slide])
        except Exception as e:
            if "429" in str(e):  # Too Many Requests
                print(f"Rate limit hit, waiting...")
                await asyncio.sleep(5)
                try:
                    await birthday_msg.edit(BIRTHDAY_SLIDES[current_slide])
                except Exception as retry_e:
                    print(f"Failed to edit birthday message after retry: {retry_e}")
                    break
            else:
                print(f"Failed to edit birthday message: {e}")
                break
    
    try:
        await birthday_msg.edit(BIRTHDAY_SLIDES[-1])
    except Exception as e:
        print(f"Failed to set final birthday message: {e}")
    
    if user_id == BIRTHDAY_GIRL_ID:
        birthday_girl_used = True
        print(f"Birthday girl used the command, now everyone can use it!")
    
    print(f"Birthday animation completed for user {user_id} in chat {chat_id}")

async def main():
    await client.start()
    print('🎂 Birthday UserBot запущен!')
    print('📱 Устройство: Samsung Galaxy S23')
    print('🤖 Команда: "с днем рождения меня" - интерактивное поздравление с днем рождения')
    print('⏰ Кулдаун: 1.5 часа')
    
    # Ожидаем события
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())
