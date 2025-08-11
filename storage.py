"""Модуль для работы с хранилищем данных."""
import json
import logging
from typing import Dict, Any
from pathlib import Path
from config import STORE_FILE, MARRIAGE_FILE, ADMINS_FILE, COOLDOWNS_FILE

logger = logging.getLogger(__name__)


def load_store() -> Dict[str, dict]:
    """Загружает данные подписчиков."""
    if not STORE_FILE.exists():
        return {}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        logger.error("Failed to read store: %s", e)
        return {}


def save_store(data: Dict[str, dict]) -> None:
    """Сохраняет данные подписчиков."""
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write store: %s", e)


def load_marriage() -> Dict[str, Any]:
    """Загружает данные браков."""
    if not MARRIAGE_FILE.exists():
        return {"proposals": {}, "marriages": []}
    try:
        with open(MARRIAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {"proposals": {}, "marriages": []}
    except Exception as e:
        logger.error("Failed to read marriage store: %s", e)
        return {"proposals": {}, "marriages": []}


def save_marriage(data: Dict[str, Any]) -> None:
    """Сохраняет данные браков."""
    try:
        with open(MARRIAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write marriage store: %s", e)


def load_admins() -> Dict[str, Any]:
    """Загружает данные админов."""
    import os
    data = {"owner_id": 0, "admins": [], "custom_commands": {}}
    if ADMINS_FILE.exists():
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                data.update(loaded or {})
        except Exception as e:
            logger.error("Failed to read admins store: %s", e)
    if not data.get("owner_id"):
        owner_env = os.environ.get("BOT_OWNER_ID")
        if owner_env and owner_env.isdigit():
            data["owner_id"] = int(owner_env)
            save_admins(data)
    data.setdefault("admins", [])
    data.setdefault("custom_commands", {})
    return data


def save_admins(data: Dict[str, Any]) -> None:
    """Сохраняет данные админов."""
    try:
        with open(ADMINS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write admins store: %s", e)


def load_cooldowns() -> Dict[str, Dict[str, float]]:
    """Загружает данные кулдаунов."""
    if not COOLDOWNS_FILE.exists():
        return {}
    try:
        with open(COOLDOWNS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        logger.error("Failed to read cooldowns: %s", e)
        return {}


def save_cooldowns(data: Dict[str, Dict[str, float]]) -> None:
    """Сохраняет данные кулдаунов."""
    try:
        with open(COOLDOWNS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write cooldowns: %s", e)


def check_cooldown(user_id: int, chat_id: int, command: str, cooldown_seconds: int) -> tuple[bool, int]:
    """
    Проверяет кулдаун для команды.
    
    Returns:
        tuple: (можно_использовать, оставшееся_время_в_секундах)
    """
    import time
    
    cooldowns = load_cooldowns()
    key = f"{user_id}_{chat_id}"
    
    if key not in cooldowns:
        cooldowns[key] = {}
    
    current_time = time.time()
    last_used = cooldowns[key].get(command, 0)
    
    if current_time - last_used >= cooldown_seconds:
        # Кулдаун прошел, обновляем время
        cooldowns[key][command] = current_time
        save_cooldowns(cooldowns)
        return True, 0
    else:
        # Кулдаун еще активен
        remaining = int(cooldown_seconds - (current_time - last_used))
        return False, remaining
