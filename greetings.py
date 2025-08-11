"""Модуль системы приветствий."""
import asyncio
import logging
import base64
import tempfile
import os
from datetime import time as dtime
from typing import Literal
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, Application
from g4f.client import Client as G4FClient

from utils import build_caption, parse_time_hhmm
from generate_image import FusionBrainAPI

logger = logging.getLogger(__name__)
g4f_client = G4FClient()

fusion_api = FusionBrainAPI(
    'https://api-key.fusionbrain.ai/',
    '9154F36CA2E78090F7772F11A6BEA9C3',
    'C5C0BA88525F433CF1817485DA5E1511'
)

def _gen_text_sync(kind: Literal["morning", "evening"]) -> str:
    if kind == "morning":
        user_prompt = (
            "Сгенерируй очень короткое, тёплое пожелание доброго утра на русском языке для чата Волки вуза МИРЭА "
            "(1–2 предложения). Избегай хэштегов. Разрешено 1 уместный эмодзи. "
            "Стиль — дружелюбный, заботливый, вдохновляющий."
        )
        model = "gpt-4o-mini"
    else:
        user_prompt = (
            "Сгенерируй очень короткое, тёплое пожелание спокойной ночи на русском языке для чата Волки вуза МИРЭА"
            "(1–2 предложения). Избегай хэштегов. Разрешено 1 уместный эмодзи. "
            "Стиль — уютный, нежный, успокаивающий."
        )
        model = "gpt-4o-mini"

    resp = g4f_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Ты — дружелюбный и веселый автор коротких тёплых пожеланий."},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = resp.choices[0].message.content
    return str(content).strip()


def _gen_image_sync(kind: Literal["morning", "evening"]) -> str:
    """FusionBrain API"""
    try:
        if kind == "morning":
            image_prompt = (
                "Милый пушистый котёнок утром, мягкий тёплый свет, солнечные лучи, уют, "
                "высокое качество, иллюстрация, детальная шерсть, 4k, warm tones"
            )
        else:
            image_prompt = (
                "Милый котёнок спокойно спит под пледом, лунный свет из окна, мягкие тени, "
                "уютная атмосфера, высокое качество, иллюстрация, 4k, night, dreamy"
            )

        pipeline_id = fusion_api.get_pipeline()
        if not pipeline_id:
            logger.error("Не удалось получить pipeline ID")
            return ""

        uuid = fusion_api.generate(image_prompt, pipeline_id)
        if not uuid:
            logger.error("Не удалось запустить генерацию")
            return ""

        files = fusion_api.check_generation(uuid, attempts=15, delay=8)
        if not files:
            logger.error("Не удалось получить изображение")
            return ""

        # base64 в файл
        image_base64 = files[0]
        image_data = base64.b64decode(image_base64)
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.write(image_data)
        temp_file.close()
        
        return temp_file.name

    except Exception as e:
        logger.error("Ошибка генерации изображения: %s", e)
        return ""


async def generate_text(kind: Literal["morning", "evening"]) -> str:
    try:
        return await asyncio.to_thread(_gen_text_sync, kind)
    except Exception as e:
        logger.exception("Text generation failed: %s", e)
        return "Не удалось сгенерировать текст в этот раз. Попробуем позже"


async def generate_image_path(kind: Literal["morning", "evening"]) -> str:
    try:
        return await asyncio.to_thread(_gen_image_sync, kind)
    except Exception as e:
        logger.exception("Image generation failed: %s", e)
        return ""


async def send_greeting(context: ContextTypes.DEFAULT_TYPE) -> None:
    kind: Literal["morning", "evening"] = context.job.data["kind"]
    chat_id: int = context.job.data["chat_id"]
    text = await generate_text(kind)
    image_path = await generate_image_path(kind)
    
    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=build_caption(kind, text),
                    parse_mode=ParseMode.HTML,
                )
            os.unlink(image_path)
        else:
            raise RuntimeError("no image file")
    except Exception as e:
        logger.error("Failed to send image, sending text only: %s", e)
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_caption(kind, text + "\n\n(Изображение временно недоступно)"),
            parse_mode=ParseMode.HTML,
        )
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


def schedule_for_chat(app: Application, chat_id: int, settings) -> None:
    if getattr(app, "job_queue", None) is None:
        logger.error('pip install "python-telegram-bot[job-queue]"')
        return

    for name in (f"morning_{chat_id}", f"evening_{chat_id}"):
        for job in app.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    tz = ZoneInfo(settings.tz)
    t_morning = parse_time_hhmm(settings.morning)
    t_evening = parse_time_hhmm(settings.evening)

    if t_morning:
        app.job_queue.run_daily(
            send_greeting,
            time=dtime(hour=t_morning.hour, minute=t_morning.minute, tzinfo=tz),
            name=f"morning_{chat_id}",
            data={"kind": "morning", "chat_id": chat_id},
            chat_id=chat_id,
        )

    if t_evening:
        app.job_queue.run_daily(
            send_greeting,
            time=dtime(hour=t_evening.hour, minute=t_evening.minute, tzinfo=tz),
            name=f"evening_{chat_id}",
            data={"kind": "evening", "chat_id": chat_id},
            chat_id=chat_id,
        )

    logger.info("Scheduled chat %s -> morning=%s, evening=%s, tz=%s",
                chat_id, settings.morning, settings.evening, settings.tz)


async def preview_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from admin import ensure_admin
    
    if not await ensure_admin(update):
        return
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    arg = (context.args[0].lower() if context.args else "morning")
    kind: Literal["morning", "evening"] = "morning" if arg not in ("evening", "night", "вечер") else "evening"

    await update.message.reply_text(
        "Готовлю для вас пост... ☕️🐾" if kind == "morning" else "Готовлю уютный вечерний пост... 🌙🐾"
    )
    text = await generate_text(kind)
    image_path = await generate_image_path(kind)
    
    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=build_caption(kind, text),
                    parse_mode=ParseMode.HTML,
                )
            # Удаляем временный файл
            os.unlink(image_path)
        else:
            raise RuntimeError("no image file")
    except Exception as e:
        logger.error("Preview failed: %s", e)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Не удалось создать превью, попробуйте позже.",
        )
        # Удаляем временный файл при ошибке
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)
