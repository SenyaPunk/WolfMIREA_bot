import asyncio
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import time as dtime, datetime
from pathlib import Path
from typing import Dict, Literal, Optional, Any, Tuple

from zoneinfo import ZoneInfo

from telegram import (
  Update,
  InlineKeyboardButton,
  InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
  Application,
  ApplicationBuilder,
  CommandHandler,
  ContextTypes,
  CallbackQueryHandler,
  MessageHandler,
  filters,
)

# g4f client
from g4f.client import Client as G4FClient

from dotenv import load_dotenv

load_dotenv()



DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_FILE = DATA_DIR / "subscribers.json"       
MARRIAGE_FILE = DATA_DIR / "marriages.json"       
ADMINS_FILE = DATA_DIR / "admins.json"          

DEFAULT_TZ = "Europe/Moscow"
DEFAULT_MORNING = "08:00"
DEFAULT_EVENING = "22:00"

RESERVED_COMMANDS = {
  "start", "help",
  "stop",
  "set_morning", "set_evening", "set_timezone", "settings", "preview",

  "marry", "marriages", "divorce",
  "брак", "браки", "развод",

  "admin_claim", "admins", "admin_add", "admin_remove",
  "cc_set", "cc_set_photo", "cc_remove", "cc_list"
}

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("tg-g4f-greetings")




def load_store() -> Dict[str, dict]:
  if not STORE_FILE.exists():
      return {}
  try:
      with open(STORE_FILE, "r", encoding="utf-8") as f:
          return json.load(f)
  except Exception as e:
      logger.error(f"Failed to read store: {e}")
      return {}


def save_store(store: Dict[str, dict]) -> None:
  try:
      with open(STORE_FILE, "w", encoding="utf-8") as f:
          json.dump(store, f, ensure_ascii=False, indent=2)
  except Exception as e:
      logger.error(f"Failed to write store: {e}")


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




def load_admins() -> Dict[str, Any]:
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
  try:
      with open(ADMINS_FILE, "w", encoding="utf-8") as f:
          json.dump(data, f, ensure_ascii=False, indent=2)
  except Exception as e:
      logger.error("Failed to write admins store: %s", e)


def is_owner(user_id: Optional[int]) -> bool:
  if not user_id:
      return False
  data = load_admins()
  return data.get("owner_id") == user_id


def is_admin(user_id: Optional[int]) -> bool:
  if not user_id:
      return False
  data = load_admins()
  return data.get("owner_id") == user_id or user_id in set(data.get("admins", []))


async def ensure_admin(update: Update) -> bool:
  uid = update.effective_user.id if update.effective_user else None
  if not is_admin(uid):
      if update.effective_chat and update.message:
          await update.message.reply_text("Эта команда доступна только админам.")
      return False
  return True


def normalize_cmd_name(s: str) -> str:
  s = s.strip()
  if s.startswith("/"):
      s = s[1:]
  if "@" in s:
      s = s.split("@", 1)[0]
  return s.strip().lower()


def mention_html(user_id: int, name: str) -> str:
  return f'<a href="tg://user?id={user_id}">{safe_html(name)}</a>'


def display_name_from_user(user) -> str:
  if getattr(user, "full_name", ""):
      return user.full_name
  if getattr(user, "username", ""):
      return f"@{user.username}"
  return str(user.id)


TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_time_hhmm(value: str) -> Optional[dtime]:
  m = TIME_RE.match(value.strip())
  if not m:
      return None
  hh, mm = int(m.group(1)), int(m.group(2))
  return dtime(hour=hh, minute=mm)


def safe_html(text: str) -> str:
  return (
      text.replace("&", "&amp;")
      .replace("<", "&lt;")
      .replace(">", "&gt;")
  )




g4f_client = G4FClient()

def _gen_text_sync(kind: Literal["morning", "evening"]) -> str:
  if kind == "morning":
      user_prompt = (
          "Сгенерируй очень короткое, тёплое пожелание доброго утра на русском языке для чата Волки вуза МИРЭА "
          "(1–2 предложения). Избегай хэштегов. Разрешено 1–2 уместных эмодзи. "
          "Стиль — дружелюбный, заботливый, вдохновляющий."
      )
      model = "gpt-4o-mini"
  else:
      user_prompt = (
          "Сгенерируй очень короткое, тёплое пожелание спокойной ночи на русском языке для чата Волки вуза МИРЭА"
          "(1–2 предложения). Избегай хэштегов. Разрешено 1–2 уместных эмодзи. "
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
  content = resp.choices[0].message.content  # type: ignore[attr-defined]
  return str(content).strip()


def _gen_image_url_sync(kind: Literal["morning", "evening"]) -> str:
  if kind == "morning":
      image_prompt = (
          "Милый пушистый котёнок утром, мягкий тёплый свет, солнечные лучи, уют, "
          "высокое качество, иллюстрация, детальная шерсть, 4k, warm tones"
      )
      model = "flux"
  else:
      image_prompt = (
          "Милый котёнок спокойно спит под пледом, лунный свет из окна, мягкие тени, "
          "уютная атмосфера, высокое качество, иллюстрация, 4k, night, dreamy"
      )
      model = "flux"

  resp = g4f_client.images.generate(
      model=model,
      prompt=image_prompt,
      response_format="url",
  )
  url = resp.data[0].url  # type: ignore[attr-defined]
  return str(url)


async def generate_text(kind: Literal["morning", "evening"]) -> str:
  try:
      return await asyncio.to_thread(_gen_text_sync, kind)
  except Exception as e:
      logger.exception("Text generation failed: %s", e)
      return "Не удалось сгенерировать текст в этот раз. Попробуем позже"


async def generate_image_url(kind: Literal["morning", "evening"]) -> str:
  try:
      return await asyncio.to_thread(_gen_image_url_sync, kind)
  except Exception as e:
      logger.exception("Image generation failed: %s", e)
      return ""


def build_caption(kind: Literal["morning", "evening"], text: str) -> str:
  if kind == "morning":
      title = "✨ Доброе утро пупсы!"
      accent = "— — — — — — — — — —"
  else:
      title = "🌙 Спокойной ночи пупсы!"
      accent = "— — — — — — — — — —"

  text = safe_html(text)
  caption = (
      f"<b>{title}</b>\n"
      f"<i>{accent}</i>\n"
      f"{text}\n"
      f"<i>{accent}</i>"
  )
  return caption



async def send_greeting(context: ContextTypes.DEFAULT_TYPE) -> None:
  kind: Literal["morning", "evening"] = context.job.data["kind"]  # type: ignore[index]
  chat_id: int = context.job.data["chat_id"]  # type: ignore[index]
  text = await generate_text(kind)
  image_url = await generate_image_url(kind)
  try:
      if image_url:
          await context.bot.send_photo(
              chat_id=chat_id,
              photo=image_url,
              caption=build_caption(kind, text),
              parse_mode=ParseMode.HTML,
          )
      else:
          raise RuntimeError("no image url")
  except Exception as e:
      logger.error("Failed to send image, sending text only: %s", e)
      await context.bot.send_message(
          chat_id=chat_id,
          text=build_caption(kind, text + "\n\n(Изображение временно недоступно)"),
          parse_mode=ParseMode.HTML,
      )


def schedule_for_chat(app: Application, chat_id: int, settings: ChatSettings) -> None:
  if getattr(app, "job_queue", None) is None:
      logger.error(
          'pip install "python-telegram-bot[job-queue]"'
      )
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




def load_marriage() -> Dict[str, Any]:
  if not MARRIAGE_FILE.exists():
      return {"proposals": {}, "marriages": []}
  try:
      with open(MARRIAGE_FILE, "r", encoding="utf-8") as f:
          data = json.load(f)
          data.setdefault("proposals", {})
          data.setdefault("marriages", [])
          return data
  except Exception as e:
      logger.error("Failed to read marriage store: %s", e)
      return {"proposals": {}, "marriages": []}


def save_marriage(data: Dict[str, Any]) -> None:
  try:
      with open(MARRIAGE_FILE, "w", encoding="utf-8") as f:
          json.dump(data, f, ensure_ascii=False, indent=2)
  except Exception as e:
      logger.error("Failed to write marriage store: %s", e)


def is_user_married_in_chat(data: Dict[str, Any], chat_id: int, user_id: int) -> bool:
  for m in data["marriages"]:
      if m["chat_id"] == chat_id and (m["a_id"] == user_id or m["b_id"] == user_id):
          return True
  return False


def find_user_partner_in_chat(data: Dict[str, Any], chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
  for m in data["marriages"]:
      if m["chat_id"] == chat_id and (m["a_id"] == user_id or m["b_id"] == user_id):
          return m
  return None


def find_marriage_of_user(data: Dict[str, Any], chat_id: int, user_id: int):
  for idx, m in enumerate(data["marriages"]):
      if m["chat_id"] == chat_id and (m["a_id"] == user_id or m["b_id"] == user_id):
          return idx, m
  return None, None


def remove_marriage(data: Dict[str, Any], index: int) -> None:
  try:
      data["marriages"].pop(index)
  except Exception:
      pass
  save_marriage(data)



MARRY_DEEPLINK_PREFIX = "marry_"  

async def cmd_marry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  message = update.message
  if not message or not update.effective_chat:
      return

  chat = update.effective_chat
  if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
      await message.reply_text("Команда /брак используется в группе")
      return

  proposer = update.effective_user
  if not proposer:
      return

  target_user = None
  target_username = None

  if message.reply_to_message and message.reply_to_message.from_user:
      target_user = message.reply_to_message.from_user
  else:
      if message.entities:
          for ent in message.entities:
              if ent.type == "text_mention" and ent.user:
                  target_user = ent.user
                  break
              if ent.type == "mention":
                  text = message.text or ""
                  mention_text = text[ent.offset: ent.offset + ent.length]
                  target_username = mention_text.lstrip("@")

  if not target_user and not target_username:
      await message.reply_text(
          "Кого звать в брак?\n"
          "Подсказка: ответьте на сообщение человека командой /брак или упомяните его как «текстовое упоминание» (с выбором из списка). "
          "Обычный @username может не дать боту узнать ID для ЛС."
      )
      return

  if target_user and target_user.id == proposer.id:
      await message.reply_text("Самоотсосы и браки на себе не предусмотрены")
      return

  store = load_marriage()
  chat_id = chat.id

  if is_user_married_in_chat(store, chat_id, proposer.id):
      partner = find_user_partner_in_chat(store, chat_id, proposer.id)
      partner_name = partner["b_name"] if partner["a_id"] == proposer.id else partner["a_name"]
      await message.reply_text(
          f"Вы уже состоите в браке с {safe_html(partner_name)}. Для развода наберите /развод",
          parse_mode=ParseMode.HTML,
      )
      return

  if target_user and is_user_married_in_chat(store, chat_id, target_user.id):
      await message.reply_text("Этот пользователь уже состоит в браке в этом чате.")
      return

  pid = secrets.token_urlsafe(8).replace("_", "-")
  proposer_name = display_name_from_user(proposer)
  proposal: Dict[str, Any] = {
      "id": pid,
      "chat_id": chat_id,
      "proposer_id": proposer.id,
      "proposer_name": proposer_name,
      "target_id": target_user.id if target_user else None,
      "target_username": target_user.username if target_user and target_user.username else (target_username or None),
      "target_name": display_name_from_user(target_user) if target_user else (f"@{target_username}" if target_username else "пользователь"),
      "created_at": int(time.time()),
      "status": "pending",
  }
  store["proposals"][pid] = proposal
  save_marriage(store)

  me = await context.bot.get_me()
  bot_username = me.username
  deep_link = f"https://t.me/{bot_username}?start={MARRY_DEEPLINK_PREFIX}{pid}"

  dm_ok = False
  if target_user:
      try:
          kb = InlineKeyboardMarkup([
              [
                  InlineKeyboardButton("✅ Принять", callback_data=f"accept:{pid}"),
                  InlineKeyboardButton("❌ Отказаться", callback_data=f"decline:{pid}"),
              ]
          ])
          await context.bot.send_message(
              chat_id=target_user.id,
              text=(
                  f"Вам предложение брака от {safe_html(proposer_name)} в чате «{safe_html(chat.title or str(chat.id))}».\n\n"
                  f"Хотите принять?"
              ),
              parse_mode=ParseMode.HTML,
              reply_markup=kb,
          )
          dm_ok = True
      except Exception as e:
          logger.info("Cannot DM target: %s", e)

  open_pm_button = InlineKeyboardMarkup([
      [InlineKeyboardButton("Перейти в лс для ответа", url=deep_link)]
  ])
  await message.reply_text(
      (
          f"{mention_html(proposer.id, proposer_name)} сделал(а) предложение "
          f"{safe_html(proposal['target_name'])}! 💍\n"
          f"{'ЛС отправлено.' if dm_ok else 'Чтобы ответить, откройте ЛС с ботом по кнопке ниже.'}"
      ),
      parse_mode=ParseMode.HTML,
      reply_markup=open_pm_button,
      disable_web_page_preview=True,
  )


async def send_group_result(context: ContextTypes.DEFAULT_TYPE, proposal: Dict[str, Any], accepted: bool, accepter_user: Optional[Any] = None):
  chat_id = proposal["chat_id"]
  a_id = proposal["proposer_id"]
  a_name = proposal["proposer_name"]
  if accepter_user:
      b_id = accepter_user.id
      b_name = display_name_from_user(accepter_user)
  else:
      b_id = proposal.get("target_id") or 0
      b_name = proposal.get("target_name") or "Пользователь"

  if accepted:
      txt = f"💍 Ура! {mention_html(a_id, a_name)} и {mention_html(b_id, b_name)} теперь в браке! Поздравляем! 🎉"
  else:
      txt = f"💔 Увы! {mention_html(a_id, a_name)} и {mention_html(b_id, b_name)} не заключили брак."

  await context.bot.send_message(chat_id=chat_id, text=txt, parse_mode=ParseMode.HTML)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  message = update.message
  if not message:
      return

  chat = update.effective_chat
  text = (message.text or "").strip()
  args = text.split(" ", 1)
  start_param = ""
  if len(args) > 1 and args[0].startswith("/start"):
      start_param = args[1].strip()

  if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
      if not await ensure_admin(update):
          return
      chat_id = chat.id
      store = load_store()
      settings = get_chat_settings(store, chat_id)
      store[str(chat_id)] = settings.to_dict()
      save_store(store)
      schedule_for_chat(context.application, chat_id, settings)
      await message.reply_text(
          "Подписка оформлена! Я буду присылать утренние и вечерние пожелания с котиками.\n"
          "Настроить: /set_morning HH:MM, /set_evening HH:MM, /set_timezone Area/City\n\n"
          "Система браков:\n"
          "• Воспользуйтесь /брак в ответ на сообщение пользователя (или текстовым упоминанием)\n"
          "• Принятие/отказ — в личных сообщениях с ботом\n"
          "• Посмотреть пары: /браки"
      )
      return

  if start_param.startswith(MARRY_DEEPLINK_PREFIX):
      pid = start_param[len(MARRY_DEEPLINK_PREFIX):]
      data = load_marriage()
      prop = data["proposals"].get(pid)
      if not prop or prop.get("status") != "pending":
          await message.reply_text("Ссылка недействительна или предложение уже обработано.")
          return

      kb = InlineKeyboardMarkup([
          [
              InlineKeyboardButton("✅ Принять", callback_data=f"accept:{pid}"),
              InlineKeyboardButton("❌ Отказаться", callback_data=f"decline:{pid}"),
          ]
      ])
      chat_title = f"«{prop['chat_id']}»"
      await message.reply_text(
          f"Предложение брака от {safe_html(prop['proposer_name'])} в чате {chat_title}.\n"
          "Хотите принять?",
          reply_markup=kb,
          parse_mode=ParseMode.HTML,
      )
      return

  await message.reply_text(
      "Привет! Я бот с котиками, пожеланиями и «системой браков».\n"
      "Если вы владелец бота и ещё не назначены: отправьте /admin_claim."
  )


async def cb_marry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  cq = update.callback_query
  if not cq or not update.effective_user:
      return

  user = update.effective_user
  data = cq.data or ""
  if not (data.startswith("accept:") or data.startswith("decline:")):
      await cq.answer()
      return

  action, pid = data.split(":", 1)
  store = load_marriage()
  prop = store["proposals"].get(pid)
  if not prop or prop.get("status") != "pending":
      await cq.answer("Ссылка недействительна или предложение уже обработано.", show_alert=True)
      return

  intended_username = prop.get("target_username")
  intended_id = prop.get("target_id")
  if intended_id and user.id != intended_id:
      await cq.answer("Это предложение адресовано другому пользователю.", show_alert=True)
      return
  if (not intended_id) and intended_username and (getattr(user, "username", None) or "").lower() != intended_username.lower():
      await cq.answer("Это предложение адресовано другому пользователю.", show_alert=True)
      return

  chat_id = prop["chat_id"]
  if action == "accept":
      if is_user_married_in_chat(store, chat_id, prop["proposer_id"]) or is_user_married_in_chat(store, chat_id, user.id):
          prop["status"] = "declined"
          save_marriage(store)
          await cq.answer("Кто-то из вас уже состоит в браке в этом чате.", show_alert=True)
          try:
              await send_group_result(context, prop, accepted=False, accepter_user=user)
          except Exception as e:
              logger.error("Failed to post decline to group: %s", e)
          await cq.edit_message_text("Предложение отклонено: конфликт браков.")
          return

      marriage = {
          "chat_id": chat_id,
          "a_id": prop["proposer_id"],
          "a_name": prop["proposer_name"],
          "b_id": user.id,
          "b_name": display_name_from_user(user),
          "since": int(time.time()),
      }
      store["marriages"].append(marriage)
      prop["status"] = "accepted"
      prop["target_id"] = user.id
      prop["target_name"] = display_name_from_user(user)
      save_marriage(store)

      await cq.answer("Вы приняли предложение 💍", show_alert=False)
      await cq.edit_message_text("Поздравляем! Вы приняли предложение 💍")

      try:
          await send_group_result(context, prop, accepted=True, accepter_user=user)
      except Exception as e:
          logger.error("Failed to post accept to group: %s", e)
      return

  prop["status"] = "declined"
  save_marriage(store)
  await cq.answer("Вы отказались от предложения 💔", show_alert=False)
  await cq.edit_message_text("Вы отказались от предложения 💔")
  try:
      await send_group_result(context, prop, accepted=False, accepter_user=user)
  except Exception as e:
      logger.error("Failed to post decline to group: %s", e)


async def cmd_marriages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  message = update.message
  if not message or not update.effective_chat:
      return
  chat = update.effective_chat
  if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
      await message.reply_text("Команда /браки работает в группе.")
      return

  data = load_marriage()
  pairs = [m for m in data["marriages"] if m["chat_id"] == chat.id]
  if not pairs:
      await message.reply_text("В этом чате пока нет пар 💞")
      return

  def fmt_ts(ts: int) -> str:
      try:
          dt = datetime.fromtimestamp(ts)
          return dt.strftime("%d.%m.%Y")
      except Exception:
          return str(ts)

  lines = []
  for m in pairs:
      a = mention_html(m["a_id"], m["a_name"])
      b = mention_html(m["b_id"], m["b_name"])
      lines.append(f"• {a}  ❤  {b}  (с {fmt_ts(m['since'])})")

  await message.reply_text("Пары этого чата:\n" + "\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_divorce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  message = update.message
  if not message or not update.effective_chat:
      return
  chat = update.effective_chat
  if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
      await message.reply_text("Команда /развод работает в группе.")
      return

  user = update.effective_user
  if not user:
      return

  data = load_marriage()
  idx, marriage = find_marriage_of_user(data, chat.id, user.id)
  if marriage is None:
      await message.reply_text("Вы не состоите в браке в этом чате 💬")
      return

  mentioned_id = None
  if message.reply_to_message and message.reply_to_message.from_user:
      mentioned_id = message.reply_to_message.from_user.id
  else:
      if message.entities:
          for ent in message.entities:
              if ent.type == "text_mention" and ent.user:
                  mentioned_id = ent.user.id
                  break

  a_id, a_name = marriage["a_id"], marriage["a_name"]
  b_id, b_name = marriage["b_id"], marriage["b_name"]
  partner_id = b_id if a_id == user.id else a_id
  partner_name = b_name if a_id == user.id else a_name

  if mentioned_id is not None and mentioned_id != partner_id:
      await message.reply_text(
          f"Похоже, вы состоите в браке с {mention_html(partner_id, partner_name)}.\n"
          f"Если хотите развестись, используйте /развод без упоминания или ответьте на сообщение вашего текущего партнёра.",
          parse_mode=ParseMode.HTML,
      )
      return

  remove_marriage(data, idx)
  await context.bot.send_message(
      chat_id=chat.id,
      text=(
          f"💔 Печальные новости: {mention_html(user.id, display_name_from_user(user))} и "
          f"{mention_html(partner_id, partner_name)} расстались."
      ),
      parse_mode=ParseMode.HTML,
  )




async def admin_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  if update.effective_chat and update.effective_chat.type != ChatType.PRIVATE:
      await update.message.reply_text("Эту команду можно использовать только в личных сообщениях с ботом.")
      return
  uid = update.effective_user.id if update.effective_user else None
  data = load_admins()
  if data.get("owner_id"):
      await update.message.reply_text(f"Владелец уже назначен: {data['owner_id']}.")
      return
  if not uid:
      await update.message.reply_text("Не удалось определить ваш ID.")
      return
  data["owner_id"] = uid
  save_admins(data)
  await update.message.reply_text(f"Вы назначены владельцем бота (owner_id={uid}).")


async def admins_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  if not await ensure_admin(update):
      return
  data = load_admins()
  owner_id = data.get("owner_id")
  admins = data.get("admins", [])
  lines = [f"Owner ID: {owner_id}"]
  if admins:
      lines.append("Admins: " + ", ".join(map(str, admins)))
  else:
      lines.append("Admins: (пусто)")
  await update.message.reply_text("\n".join(lines))


def extract_target_user_id_from_message(message) -> Optional[int]:
  if message.reply_to_message and message.reply_to_message.from_user:
      return message.reply_to_message.from_user.id
  if message.entities:
      for ent in message.entities:
          if ent.type == "text_mention" and ent.user:
              return ent.user.id
  parts = (message.text or "").strip().split()
  if len(parts) > 1 and parts[1].isdigit():
      return int(parts[1])
  return None


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  uid = update.effective_user.id if update.effective_user else None
  if not is_owner(uid):
      await update.message.reply_text("Добавлять админов может только владелец бота.")
      return
  target_id = extract_target_user_id_from_message(update.message)
  if not target_id:
      await update.message.reply_text("Укажите пользователя (реплаем, text_mention или ID): /admin_add <id>")
      return
  data = load_admins()
  if target_id == data.get("owner_id"):
      await update.message.reply_text("Этот пользователь уже владелец.")
      return
  admins = set(data.get("admins", []))
  admins.add(target_id)
  data["admins"] = list(sorted(admins))
  save_admins(data)
  await update.message.reply_text(f"Пользователь {target_id} добавлен в админы.")


async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  uid = update.effective_user.id if update.effective_user else None
  if not is_owner(uid):
      await update.message.reply_text("Удалять админов может только владелец бота.")
      return
  target_id = extract_target_user_id_from_message(update.message)
  if not target_id:
      await update.message.reply_text("Укажите пользователя (реплаем, text_mention или ID): /admin_remove <id>")
      return
  data = load_admins()
  if target_id == data.get("owner_id"):
      await update.message.reply_text("Нельзя удалить владельца.")
      return
  admins = set(data.get("admins", []))
  if target_id in admins:
      admins.remove(target_id)
      data["admins"] = list(sorted(admins))
      save_admins(data)
      await update.message.reply_text(f"Пользователь {target_id} удалён из админов.")
  else:
      await update.message.reply_text("Этот пользователь не админ.")




def cc_list() -> Dict[str, Any]:
  return load_admins().get("custom_commands", {})


def cc_set(cmd: str, payload: Dict[str, Any]) -> None:
  data = load_admins()
  data.setdefault("custom_commands", {})
  data["custom_commands"][cmd] = payload
  save_admins(data)


def cc_remove(cmd: str) -> bool:
  data = load_admins()
  cmds = data.get("custom_commands", {})
  if cmd in cmds:
      del cmds[cmd]
      save_admins(data)
      return True
  return False


async def cc_cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  if not await ensure_admin(update):
      return
  parts = (update.message.text or "").split(" ", 2)
  if len(parts) < 3:
      await update.message.reply_text("Использование: /cc_set <command> <text>")
      return
  cmd = normalize_cmd_name(parts[1])
  if not cmd or cmd in RESERVED_COMMANDS:
      await update.message.reply_text("Нельзя использовать это имя команды (зарезервировано).")
      return
  text = parts[2].strip()
  cc_set(cmd, {"type": "text", "text": text})
  await update.message.reply_text(f"Кастомная команда '/{cmd}' сохранена (текст).")


async def cc_cmd_set_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  if not await ensure_admin(update):
      return
  parts = (update.message.text or "").split(" ", 3)
  if len(parts) < 3:
      await update.message.reply_text("Использование: /cc_set_photo <command> <image_url> [| caption]")
      return
  cmd = normalize_cmd_name(parts[1])
  if not cmd or cmd in RESERVED_COMMANDS:
      await update.message.reply_text("Нельзя использовать это имя команды (зарезервировано).")
      return
  rest = (parts[2] if len(parts) >= 3 else "")
  trailing = (parts[3] if len(parts) >= 4 else "")
  raw = (rest + (" " + trailing if trailing else "")).strip()
  if " | " in raw:
      image_url, caption = raw.split(" | ", 1)
  elif "|" in raw:
      image_url, caption = raw.split("|", 1)
  else:
      image_url, caption = raw, ""
  image_url = image_url.strip()
  caption = caption.strip()
  if not image_url:
      await update.message.reply_text("Укажите image_url.")
      return
  cc_set(cmd, {"type": "photo", "image_url": image_url, "caption": caption})
  await update.message.reply_text(f"Кастомная команда '/{cmd}' сохранена (фото).")


async def cc_cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  if not await ensure_admin(update):
      return
  parts = (update.message.text or "").split(" ", 1)
  if len(parts) < 2:
      await update.message.reply_text("Использование: /cc_remove <command>")
      return
  cmd = normalize_cmd_name(parts[1])
  if cc_remove(cmd):
      await update.message.reply_text(f"Кастомная команда '/{cmd}' удалена.")
  else:
      await update.message.reply_text("Такой команды нет.")


async def cc_cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  cmds = cc_list()
  if not cmds:
      await update.message.reply_text("Кастомных команд пока нет.")
      return
  names = sorted(cmds.keys())
  await update.message.reply_text("Доступные кастомные команды:\n" + ", ".join(f"/{n}" for n in names))


async def custom_command_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  message = update.message
  if not message or not message.text:
      return
  text = message.text.strip()
  if not text.startswith("/"):
      return
  token = text.split()[0]  
  cmd = normalize_cmd_name(token)
  if not cmd or cmd in RESERVED_COMMANDS:
      return  
  cmds = cc_list()
  entry = cmds.get(cmd)
  if not entry:
      return
  try:
      if entry.get("type") == "photo" and entry.get("image_url"):
          await context.bot.send_photo(
              chat_id=message.chat_id,
              photo=entry["image_url"],
              caption=entry.get("caption") or None,
              parse_mode=ParseMode.HTML if entry.get("caption") else None,
          )
      else:
          await message.reply_text(entry.get("text", ""))
  except Exception as e:
      logger.error("Failed to execute custom command '/%s': %s", cmd, e)
      await message.reply_text("Не удалось выполнить команду, попробуйте позже.")


HELP_TEXT = (
  "Привет! Я буду присылать милого котика и тёплые пожелания утром и вечером. А также я просто хороший мальчик, гав\n\n"
  "Основные команды:\n"
  "• /start — подписаться в группе (только админ бота)\n"
  "• /stop — отписаться (только админ бота)\n"
  "• /set_morning HH:MM — время утра (только админ бота)\n"
  "• /set_evening HH:MM — время вечера (только админ бота)\n"
  "• /set_timezone Area/City — часовой пояс (только админ бота)\n"
  "• /settings — показать текущие настройки\n"
  "• /preview [morning|evening] — мгновенный пост (только админ бота)\n\n"
  "Система браков:\n"
  "• /брак (alias: /marry) — предложение\n"
  "• /развод (alias: /divorce) — расторгнуть брак\n"
  "• /браки (alias: /marriages) — список пар\n\n"
  "Админка:\n"
  "• /admin_claim — стать владельцем (только в ЛС, если владелец ещё не назначен)\n"
  "• /admins — список админов (только админ)\n"
  "• /admin_add <id> — добавить админа (только владелец)\n"
  "• /admin_remove <id> — удалить админа (только владелец)\n\n"
  "Кастомные команды (создаёт админ, используют все):\n"
  "• /cc_set <command> <text>\n"
  "• /cc_set_photo <command> <image_url> [| caption]\n"
  "• /cc_remove <command>\n"
  "• /cc_list — посмотреть все\n"
)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
  logger.exception("Unhandled exception while handling update: %s", context.error)


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


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
  image_url = await generate_image_url(kind)
  try:
      if image_url:
          await context.bot.send_photo(
              chat_id=chat_id,
              photo=image_url,
              caption=build_caption(kind, text),
              parse_mode=ParseMode.HTML,
          )
      else:
          raise RuntimeError("no image url")
  except Exception as e:
      logger.error("Preview failed: %s", e)
      await context.bot.send_message(
          chat_id=chat_id,
          text="Не удалось создать превью, попробуйте позже.",
      )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  await update.message.reply_text(HELP_TEXT)



def bootstrap_application() -> Application:
  token = os.environ.get("TELEGRAM_BOT_TOKEN")
  if not token:
      raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")

  app = ApplicationBuilder().token(token).build()
  app.add_error_handler(error_handler)

  app.add_handler(CommandHandler("start", handle_start))
  app.add_handler(CommandHandler("stop", stop))
  app.add_handler(CommandHandler("set_morning", set_morning))
  app.add_handler(CommandHandler("set_evening", set_evening))
  app.add_handler(CommandHandler("set_timezone", set_timezone))
  app.add_handler(CommandHandler("settings", settings_cmd))
  app.add_handler(CommandHandler("preview", preview))
  app.add_handler(CommandHandler("help", help_cmd))

  app.add_handler(CommandHandler("admin_claim", admin_claim))
  app.add_handler(CommandHandler("admins", admins_list))
  app.add_handler(CommandHandler("admin_add", admin_add))
  app.add_handler(CommandHandler("admin_remove", admin_remove))

  app.add_handler(CommandHandler("cc_set", cc_cmd_set))
  app.add_handler(CommandHandler("cc_set_photo", cc_cmd_set_photo))
  app.add_handler(CommandHandler("cc_remove", cc_cmd_remove))
  app.add_handler(CommandHandler("cc_list", cc_cmd_list))

  app.add_handler(CommandHandler(["marry"], cmd_marry, filters=filters.ChatType.GROUPS))
  app.add_handler(CommandHandler(["marriages"], cmd_marriages, filters=filters.ChatType.GROUPS))
  app.add_handler(CommandHandler(["divorce"], cmd_divorce, filters=filters.ChatType.GROUPS))
  app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/брак(?:@\w+)?(?:\s|$)"), cmd_marry))
  app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/браки(?:@\w+)?(?:\s|$)"), cmd_marriages))
  app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^/развод(?:@\w+)?(?:\s|$)"), cmd_divorce))
  app.add_handler(CallbackQueryHandler(cb_marry, pattern=r"^(accept|decline):"))

  app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_command_router))
  app.add_handler(MessageHandler(filters.Regex(r"^/"), custom_command_router))

  store = load_store()
  for chat_id_str, cfg in store.items():
      try:
          chat_id = int(chat_id_str)
      except ValueError:
          continue
      schedule_for_chat(app, chat_id, ChatSettings.from_dict(cfg))

  return app


def main() -> None:
  try:
      app = bootstrap_application()
      logger.info("Bot is starting...")
      app.run_polling(close_loop=False)
  except Exception as e:
      logger.exception("Fatal error: %s", e)


if __name__ == "__main__":
  main()
