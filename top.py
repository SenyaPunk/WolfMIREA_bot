"""Система топов пользователей."""
import logging
from typing import List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from economy import load_economy, format_balance
from blackjack import get_blackjack_leaderboard
from utils import safe_html, profile_link_html

logger = logging.getLogger(__name__)


def get_balance_leaderboard() -> List[Dict[str, Any]]:
    """Возвращает топ пользователей по балансу."""
    data = load_economy()
    balances = data.get("balances", {})
    usernames = data.get("usernames", {})
    
    players = []
    for user_id_str, balance in balances.items():
        if balance <= 0:  # Пропускаем пользователей с нулевым или отрицательным балансом
            continue
            
        user_id = int(user_id_str)
        
        # Ищем имя пользователя
        user_name = f"Пользователь {user_id}"
        username = None
        for uname, uid in usernames.items():
            if uid == user_id:
                user_name = f"@{uname}"
                username = uname
                break
        
        players.append({
            "user_id": user_id,
            "name": user_name,
            "username": username,
            "balance": balance
        })
    
    # Сортируем по балансу (убывание)
    players.sort(key=lambda x: -x["balance"])
    
    return players


def format_balance_top(players: List[Dict[str, Any]]) -> str:
    """Форматирует топ по балансу."""
    if not players:
        return "📊 <b>ТОП ПО БАЛАНСУ</b>\n\n❌ Нет данных для отображения"
    
    message = "📊 <b>ТОП ПО БАЛАНСУ</b>\n\n"
    
    for i, player in enumerate(players[:10], 1):  # Показываем топ-10
        medal = ""
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."
        
        # Используем profile_link_html для создания ссылок без пинга
        user_link = profile_link_html(player['user_id'], player['name'], player.get('username'))
        message += f"{medal} <b>{user_link}</b> — {format_balance(player['balance'])}\n"
    
    return message


def format_blackjack_top(players: List[Dict[str, Any]]) -> str:
    """Форматирует топ по блекджеку."""
    if not players:
        return "🎰 <b>ТОП ПО БЛЕКДЖЕКУ</b>\n\n❌ Нет данных для отображения"
    
    message = "🎰 <b>ТОП ПО БЛЕКДЖЕКУ</b>\n\n"
    
    for i, player in enumerate(players[:10], 1):  # Показываем топ-10
        medal = ""
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."
        
        wins = player['wins']
        losses = player['losses']
        draws = player['draws']
        games = player['games']
        
        # Рассчитываем процент побед
        win_rate = (wins / games * 100) if games > 0 else 0
        
        # Используем profile_link_html для создания ссылок без пинга
        user_link = profile_link_html(player['user_id'], player['name'], player.get('username'))
        message += (f"{medal} <b>{user_link}</b>\n"
                   f"    🏆 {wins} побед | 🤝 {draws} ничьих | 💥 {losses} поражений\n"
                   f"    📊 {games} игр | 📈 {win_rate:.1f}% побед\n\n")
    
    return message


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /top - показывает топ пользователей."""
    if not update.message:
        return
    
    # Получаем топ по балансу
    balance_players = get_balance_leaderboard()
    message = format_balance_top(balance_players)
    
    # Создаем кнопку для переключения на блекджек
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 BlackJack", callback_data="top_switch:blackjack")]
    ])
    
    await update.message.reply_text(
        message,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML, 
        disable_web_page_preview=True

    )


async def cb_top_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик переключения между топами."""
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    
    switch_to = query.data.split(":", 1)[1]
    
    if switch_to == "blackjack":
        # Переключаемся на топ по блекджеку
        blackjack_players = get_blackjack_leaderboard()
        message = format_blackjack_top(blackjack_players)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 По монетам", callback_data="top_switch:balance")]
        ])
    
    elif switch_to == "balance":
        # Переключаемся на топ по балансу
        balance_players = get_balance_leaderboard()
        message = format_balance_top(balance_players)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 BlackJack", callback_data="top_switch:blackjack")]
        ])
    
    else:
        return
    
    try:
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to edit top message: {e}")
