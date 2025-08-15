import logging
from datetime import time as dtime
from zoneinfo import ZoneInfo
from telegram.ext import Application
from telegram.constants import ParseMode
from config import DEFAULT_TZ

logger = logging.getLogger(__name__)

# Настройки поздравления
BIRTHDAY_CHAT_ID = -1002578226318  # ID чата для отправки поздравления (замените на нужный)
BIRTHDAY_TIME = "18:00"  # Время отправки по МСК
BIRTHDAY_GIRL_NAME = "Жаннет"  # Имя именинницы

async def send_birthday_greeting(context) -> None:
    """Отправляет поздравление с днем рождения"""
    try:
        birthday_message = f"""🎉🎂 @zharnet <b>С ДНЕМ РОЖДЕНИЯ, {BIRTHDAY_GIRL_NAME}!</b> 🎂🎉

🌟 От всего чата поздравляем тебя с днем рождения! 
Пусть этот день будет наполнен радостью, смехом и теплом близких людей!

🎁 Желаем тебе:
• Крепкого здоровья и бодрости духа
• Исполнения всех заветных желаний  
• Ярких эмоций и незабываемых моментов
• Любви, счастья и благополучия

🥳 Пусть каждый новый год жизни приносит только самое лучшее!

💖 С любовью и наилучшими пожеланиями! 💖

<b>А также небольшой подарок! Просто напиши: "с днем рождения меня"</b> """

        await context.bot.send_message(
            chat_id=BIRTHDAY_CHAT_ID,
            text=birthday_message,
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Birthday message sent successfully to chat {BIRTHDAY_CHAT_ID}")
        
    except Exception as e:
        logger.error(f"Failed to send birthday message: {e}")

def schedule_birthday_greeting(app: Application) -> None:
    """Планирует ежедневную отправку поздравления в указанное время по МСК"""
    if getattr(app, "job_queue", None) is None:
        logger.error('Job queue not available. Install with pip install "python-telegram-bot[job-queue]"')
        return

    msk_tz = ZoneInfo(DEFAULT_TZ)  # Europe/Moscow
    
    # Удаляем существующие задачи поздравления
    for job in app.job_queue.get_jobs_by_name("birthday_greeting"):
        job.schedule_removal()

    hour, minute = map(int, BIRTHDAY_TIME.split(':'))
    
    # Планируем ежедневную отправку в указанное время по МСК
    app.job_queue.run_daily(
        send_birthday_greeting,
        time=dtime(hour=hour, minute=minute, tzinfo=msk_tz),
        name="birthday_greeting",
        data={"chat_id": BIRTHDAY_CHAT_ID}
    )
    
    logger.info(f"Birthday greeting scheduled for {BIRTHDAY_TIME} MSK daily in chat {BIRTHDAY_CHAT_ID}")

def init_birthday_scheduler(app: Application) -> None:
    """Инициализирует планировщик поздравлений при запуске бота"""
    schedule_birthday_greeting(app)
    logger.info("Birthday scheduler initialized")
