"""Модуль системы настроек."""
from dataclasses import dataclass
from typing import Dict
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ContextTypes
from storage import load_store, save_store
from admin import ensure_admin
from greetings import schedule_for_chat
from utils import parse_time_hhmm
from config import DEFAULT_TZ, DEFAULT_MORNING, DEFAULT_EVENING


@dataclass
class ChatSettings:
    tz: str = DEFAULT_TZ
    morning: str = DEFAULT_MORNING  # "HH:MM"
    evening: str = DEFAULT_EVENING  # "HH:MM"

    @staticmethod
    def from_dict(d: dict) -> "ChatSettings":
        return ChatSettings(
            tz=d.get("tz", DEFAULT_TZ),
            morning=d.get("morning", DEFAULT_MORNING),
            evening=d.get("evening", DEFAULT_EVENING),
        )

    def to_dict(self) -> dict:
        return {"tz": self.tz, "morning": self.morning, "evening": self.evening}


def get_chat_settings(store: Dict[str, dict], chat_id: int) -> ChatSettings:
    return ChatSettings.from_dict(store.get(str(chat_id), {}))


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    store = load_store()
    if str(chat_id) in store:
        del store[str(chat_id)]
        save_store(store)

    if context.application.job_queue:
        for name in (f"morning_{chat_id}", f"evening_{chat_id}"):
            for job in context.application.job_queue.get_jobs_by_name(name):
                job.schedule_removal()

    await update.message.reply_text("Вы отписались. Расписание удалено.")


async def set_morning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Укажите время, например: /set_morning 08:30")
        return

    value = context.args[0]
    t = parse_time_hhmm(value)
    if not t:
        await update.message.reply_text("Некорректное время. Формат HH:MM, напр. 08:30")
        return

    store = load_store()
    settings = get_chat_settings(store, chat_id)
    settings.morning = value
    store[str(chat_id)] = settings.to_dict()
    save_store(store)

    schedule_for_chat(context.application, chat_id, settings)
    await update.message.reply_text(f"Время для утреннего поста установлено на {value}.")


async def set_evening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Укажите время, например: /set_evening 22:15")
        return

    value = context.args[0]
    t = parse_time_hhmm(value)
    if not t:
        await update.message.reply_text("Некорректное время. Формат HH:MM, напр. 22:15")
        return

    store = load_store()
    settings = get_chat_settings(store, chat_id)
    settings.evening = value
    store[str(chat_id)] = settings.to_dict()
    save_store(store)

    schedule_for_chat(context.application, chat_id, settings)
    await update.message.reply_text(f"Время для вечернего поста установлено на {value}.")


async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Укажите часовой пояс, например: /set_timezone Europe/Moscow")
        return

    tz = " ".join(context.args).strip()
    try:
        ZoneInfo(tz)
    except Exception:
        await update.message.reply_text("Некорректный часовой пояс. Пример: Europe/Moscow")
        return

    store = load_store()
    settings = get_chat_settings(store, chat_id)
    settings.tz = tz
    store[str(chat_id)] = settings.to_dict()
    save_store(store)

    schedule_for_chat(context.application, chat_id, settings)
    await update.message.reply_text(f"Часовой пояс установлен: {tz}")


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    s = get_chat_settings(load_store(), chat_id)
    await update.message.reply_text(
        "Текущие настройки:\n"
        f"• Утро: {s.morning}\n"
        f"• Вечер: {s.evening}\n"
        f"• Часовой пояс: {s.tz}"
    )
