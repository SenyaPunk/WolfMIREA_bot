import re
from datetime import datetime
from typing import Optional


def safe_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mention_html(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{safe_html(name)}</a>'


def profile_link_html(user_id: int, name: str, username: Optional[str] = None) -> str:
    """Create a link to user profile without pinging them"""
    if username:
        return f'<a href="https://t.me/{username}">{safe_html(name)}</a>'
    else:
        return safe_html(name)


def display_name_from_user(user) -> str:
    if getattr(user, "full_name", ""):
        return user.full_name
    if getattr(user, "username", ""):
        return f"@{user.username}"
    return f'User {getattr(user, "id", "???")}'


def normalize_cmd_name(s: str) -> str:
    s = s.strip()
    if s.startswith("/"):
        s = s[1:]
    if "@" in s:
        s = s.split("@", 1)[0]
    return s.strip().lower()


def parse_time_hhmm(s: str) -> Optional[datetime]:
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
    emoji = "🌅" if kind == "morning" else "🌙"
    return f"{emoji} {text}"


def format_timestamp(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(ts)


def get_target_user(message, args):
    if not message:
        return None
    
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    
    if message.entities:
        for entity in message.entities:
            if entity.type == "text_mention" and entity.user:
                return entity.user
            elif entity.type == "mention":
                start = entity.offset
                length = entity.length
                username = message.text[start:start + length]
                if username.startswith('@'):
                    username = username[1:]  
                
    
                class UserStub:
                    def __init__(self, username):
                        self.username = username
                        self.id = None
                        self.first_name = f"@{username}"
                        self.full_name = f"@{username}"
                
                return UserStub(username)
    
    return None
