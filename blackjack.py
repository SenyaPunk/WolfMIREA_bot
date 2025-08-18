import asyncio
import random
import time
import logging
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from admin import is_admin
from economy import get_user_balance, add_user_balance

logger = logging.getLogger(__name__)

# Путь к папке с данными
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Константы игры
GAME_SIGNUP_TIME = 60  # 1 минута на набор игроков
MAX_PLAYERS = 5  # Максимум игроков
MIN_PLAYERS = 2  # Минимум игроков для начала игры

# Глобальное хранилище активных игр
active_games: Dict[int, 'BlackjackGame'] = {}

@dataclass
class Card:
    """Карта"""
    suit: str  # ♠️♥️♦️♣️
    rank: str  # A, 2-10, J, Q, K
    value: int  # Числовое значение для подсчета очков
    
    def __str__(self):
        return f"{self.rank}{self.suit}"

@dataclass 
class Player:
    """Игрок в блекджеке"""
    
    def __init__(self, user_id: int, username: str, first_name: str):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.cards: List[Card] = []
        self.score: int = 0
        self.is_bust: bool = False
        self.is_blackjack: bool = False
        self.is_stand: bool = False
        self.bet: int = 0  # текущая ставка игрока
        self.temp_bet: int = 0  # временная ставка во время выбора
        self.slave_bet: bool = False  # ставит ли игрок раба
        self.slave_bet_info: Optional[Dict[str, Any]] = None  # информация о поставленном рабе

def load_blackjack_stats() -> Dict[str, Any]:
    """Загружает статистику блекджека."""
    stats_file = DATA_DIR / "blackjack_stats.json"
    if not stats_file.exists():
        return {"stats": {}}
    try:
        with open(stats_file, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            data.setdefault("stats", {})
            return data
    except Exception as e:
        logger.error("Failed to read blackjack stats: %s", e)
        return {"stats": {}}


def save_blackjack_stats(data: Dict[str, Any]) -> None:
    """Сохраняет статистику блекджека."""
    stats_file = DATA_DIR / "blackjack_stats.json"
    try:
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to write blackjack stats: %s", e)


def update_player_stats(user_id: int, result: str, user_name: str) -> None:
    """Обновляет статистику игрока. result: 'win', 'loss', 'draw'"""
    data = load_blackjack_stats()
    user_key = str(user_id)
    
    if user_key not in data["stats"]:
        data["stats"][user_key] = {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "games": 0,
            "name": user_name
        }
    
    stats = data["stats"][user_key]
    stats["name"] = user_name  # Обновляем имя на случай изменения
    stats["games"] += 1
    
    if result == "win":
        stats["wins"] += 1
    elif result == "loss":
        stats["losses"] += 1
    elif result == "draw":
        stats["draws"] += 1
    
    save_blackjack_stats(data)


def get_blackjack_leaderboard() -> List[Dict[str, Any]]:
    """Возвращает топ игроков по блекджеку, отсортированный по победам, ничьим, поражениям."""
    data = load_blackjack_stats()
    players = []
    
    for user_id, stats in data["stats"].items():
        players.append({
            "user_id": int(user_id),
            "name": stats["name"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "draws": stats["draws"],
            "games": stats["games"]
        })
    
    # Сортируем: сначала по победам (убывание), потом по ничьим (убывание), потом по поражениям (возрастание)
    players.sort(key=lambda x: (-x["wins"], -x["draws"], x["losses"]))
    
    return players

class BlackjackGame:
    """Игра в блекджек"""
    
    def __init__(self, chat_id: int, admin_id: int):
        self.chat_id = chat_id
        self.admin_id = admin_id
        self.players: List[Player] = []
        self.deck: List[Card] = []
        self.dealer_cards: List[Card] = []
        self.dealer_score: int = 0
        self.is_signup_phase = True
        self.is_game_active = False
        self.signup_end_time = time.time() + GAME_SIGNUP_TIME
        self.signup_message_id: Optional[int] = None
        self.has_photo_message = False
        self.game_messages: List[int] = []  # ID сообщений игры для удаления
        self.current_player_index: int = 0  # Индекс текущего игрока
        self.dealer_hidden_card: Optional[Card] = None  # Скрытая карта дилера
        self.player_ids: Set[int] = set()  # ID игроков для фильтрации сообщений
        self.is_betting_phase: bool = False  # фаза ставок
        self.current_betting_player: int = 0  # индекс игрока, который делает ставку
        
    def create_deck(self) -> List[Card]:
        """Создать стандартную колоду карт"""
        suits = ['♠️', '♥️', '♦️', '♣️']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        
        deck = []
        for suit in suits:
            for rank in ranks:
                if rank == 'A':
                    value = 11  # Туз изначально 11, потом может стать 1
                elif rank in ['J', 'Q', 'K']:
                    value = 10
                else:
                    value = int(rank)
                    
                deck.append(Card(suit, rank, value))
        
        random.shuffle(deck)
        return deck
    
    def calculate_score(self, cards: List[Card]) -> int:
        """Подсчитать очки с учетом тузов"""
        score = sum(card.value for card in cards)
        aces = sum(1 for card in cards if card.rank == 'A')
        
        # Конвертируем тузы из 11 в 1, если нужно
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
            
        return score
    
    def add_player(self, user_id: int, username: str, first_name: str) -> bool:
        """Добавить игрока в игру"""
        if len(self.players) >= MAX_PLAYERS:
            return False
            
        # Проверяем, не добавлен ли уже игрок
        for player in self.players:
            if player.user_id == user_id:
                return False
                
        self.players.append(Player(user_id, username, first_name))
        self.player_ids.add(user_id)
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """Удалить игрока из игры"""
        for i, player in enumerate(self.players):
            if player.user_id == user_id:
                self.players.pop(i)
                self.player_ids.discard(user_id)
                return True
        return False
    
    def get_signup_keyboard(self) -> InlineKeyboardMarkup:
        """Создать клавиатуру для записи в игру"""
        button = InlineKeyboardButton(
            f"🎰 Присоединиться к игре {len(self.players)}/{MAX_PLAYERS}",
            callback_data=f"bj_join:{self.chat_id}"
        )
        return InlineKeyboardMarkup([[button]])
    
    def get_game_keyboard(self, player_index: int) -> InlineKeyboardMarkup:
        """Создать клавиатуру для хода игрока"""
        hit_button = InlineKeyboardButton(
            "🃏 Взять карту",
            callback_data=f"bj_hit:{self.chat_id}:{player_index}"
        )
        stand_button = InlineKeyboardButton(
            "✋ Остановиться", 
            callback_data=f"bj_stand:{self.chat_id}:{player_index}"
        )
        return InlineKeyboardMarkup([[hit_button, stand_button]])
    
    def format_cards(self, cards: List[Card]) -> str:
        """Форматировать карты для отображения"""
        return " ".join(str(card) for card in cards)
    
    def format_dealer_cards(self, hide_second: bool = True) -> str:
        """Форматировать карты дилера (с возможностью скрыть вторую карту)"""
        if not self.dealer_cards:
            return ""
        
        if hide_second and len(self.dealer_cards) >= 2:
            return f"{self.dealer_cards[0]} 🂠"
        else:
            return " ".join(str(card) for card in self.dealer_cards)
    
    def start_game(self):
        """Начать игру"""
        self.is_signup_phase = False
        self.is_game_active = True
        self.deck = self.create_deck()
        
        # Первый круг - всем по одной карте открыто
        for player in self.players:
            card = self.deck.pop()
            player.cards.append(card)
        
        # Дилеру первая карта открыто
        dealer_first_card = self.deck.pop()
        self.dealer_cards.append(dealer_first_card)
        
        # Второй круг - всем по второй карте открыто
        for player in self.players:
            card = self.deck.pop()
            player.cards.append(card)
            player.score = self.calculate_score(player.cards)
            
            # Проверяем блекджек
            if player.score == 21:
                player.is_blackjack = True
        
        # Дилеру вторая карта закрыто
        dealer_hidden_card = self.deck.pop()
        self.dealer_cards.append(dealer_hidden_card)
        self.dealer_hidden_card = dealer_hidden_card
        self.dealer_score = self.calculate_score(self.dealer_cards)
    
    def get_current_player(self) -> Optional[Player]:
        """Получить текущего игрока"""
        if 0 <= self.current_player_index < len(self.players):
            return self.players[self.current_player_index]
        return None
    
    def next_player(self) -> bool:
        """Перейти к следующему игроку. Возвращает True если есть следующий игрок"""
        self.current_player_index += 1
        
        # Пропускаем игроков с блекджеком или перебором
        while (self.current_player_index < len(self.players) and 
               (self.players[self.current_player_index].is_blackjack or 
                self.players[self.current_player_index].is_bust or
                self.players[self.current_player_index].is_stand)):
            self.current_player_index += 1
        
        return self.current_player_index < len(self.players)
    
    def create_game_status_message(self) -> str:
        """Создать сообщение с текущим состоянием игры"""
        message = "🎰 **БЛЕКДЖЕК - ИГРА ИДЕТ**\n\n"
        
        # Показываем карты дилера
        dealer_visible_score = self.dealer_cards[0].value if self.dealer_cards else 0
        message += f"🏦 **Дилер:** {self.format_dealer_cards()} (очки: {dealer_visible_score}+?)\n\n"
        
        # Показываем карты игроков
        message += "👥 **Игроки:**\n"
        for i, player in enumerate(self.players):
            status_icon = ""
            if player.is_blackjack:
                status_icon = "🎯"
            elif player.is_bust:
                status_icon = "💥"
            elif player.is_stand:
                status_icon = "✋"
            elif i == self.current_player_index:
                status_icon = "👉"
            
            message += f"{status_icon} **{player.first_name}:** {self.format_cards(player.cards)} (очки: {player.score})\n"
        
        current_player = self.get_current_player()
        if current_player:
            message += f"\n🎯 **Ход игрока:** {current_player.first_name}"
        
        return message

    def get_betting_keyboard(self, player_index: int) -> InlineKeyboardMarkup:
        """Создать клавиатуру для ставок"""
        from economy import get_user_balance, get_user_slave
        
        player = self.players[player_index]
        balance = get_user_balance(player.user_id)
        slave_info = get_user_slave(player.user_id)
        
        buttons = []
        # Кнопки фишек
        chip_buttons = []
        for chip in [5, 25, 50]:
            if not player.slave_bet and balance >= player.temp_bet + chip:
                chip_buttons.append(InlineKeyboardButton(
                    f"💰 {chip}",
                    callback_data=f"bj_bet_add:{self.chat_id}:{player_index}:{chip}"
                ))
            else:
                chip_buttons.append(InlineKeyboardButton(
                    f"❌ {chip}",
                    callback_data="disabled"
                ))
        
        if slave_info and not player.slave_bet and player.temp_bet == 0:
            chip_buttons.append(InlineKeyboardButton(
                "👤 Раб",
                callback_data=f"bj_bet_slave:{self.chat_id}:{player_index}"
            ))
        else:
            chip_buttons.append(InlineKeyboardButton(
                "❌ Раб",
                callback_data="disabled"
            ))
        
        buttons.append(chip_buttons)
        
        # Кнопки управления
        control_buttons = []
        if player.temp_bet > 0 or player.slave_bet:
            control_buttons.append(InlineKeyboardButton(
                "🗑️ Сбросить",
                callback_data=f"bj_bet_reset:{self.chat_id}:{player_index}"
            ))
            control_buttons.append(InlineKeyboardButton(
                "✅ Принять",
                callback_data=f"bj_bet_accept:{self.chat_id}:{player_index}"
            ))
        
        if control_buttons:
            buttons.append(control_buttons)
        
        return InlineKeyboardMarkup(buttons)

async def cb_blackjack_bet_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка добавления фишек к ставке"""
    from economy import get_user_balance
    
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str, player_index_str, chip_str = query.data.split(":")
        chat_id = int(chat_id_str)
        player_index = int(player_index_str)
        chip = int(chip_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем фазу ставок и правильного игрока
    if (not game.is_betting_phase or 
        player_index != game.current_betting_player or 
        game.players[player_index].user_id != query.from_user.id):
        await query.answer("❌ Сейчас не ваш ход для ставки!", show_alert=True)
        return
    
    player = game.players[player_index]
    
    # Проверяем, что нет ставки рабом
    if player.slave_bet:
        await query.answer("❌ Нельзя добавлять деньги к ставке рабом!", show_alert=True)
        return
    
    # Проверяем баланс
    balance = get_user_balance(player.user_id)
    if balance < player.temp_bet + chip:
        await query.answer("❌ Недостаточно средств!", show_alert=True)
        return
    
    # Добавляем фишку к ставке
    player.temp_bet += chip
    await query.answer(f"💰 Добавлено {chip} монет. Ставка: {player.temp_bet}", show_alert=False)
    
    # Обновляем сообщение
    await update_betting_message(context, game, player_index)

def create_signup_message(game: BlackjackGame, remaining_time: int) -> str:
    """Создать сообщение для набора игроков"""
    minutes = remaining_time // 60
    seconds = remaining_time % 60
    
    players_list = ""
    if game.players:
        players_list = "\n\n👥 **Игроки:**\n"
        for i, player in enumerate(game.players, 1):
            balance = get_user_balance(player.user_id)
            players_list += f"{i}. {player.first_name} (💰 {balance} монет)\n"
    
    return (
        f"🎰 **БЛЕКДЖЕК - НАБОР ИГРОКОВ**\n\n"
        f"⏰ Время на запись: **{minutes:02d}:{seconds:02d}**\n"
        f"👥 Игроков: **{len(game.players)}/{MAX_PLAYERS}**\n"
        f"🎯 Минимум для начала: **{MIN_PLAYERS} игрока**\n"
        f"💰 **Минимальный баланс: 20 монет**\n\n"
        f"📋 **Правила:**\n"
        f"• Стандартная колода карт (52 карты)\n"
        f"• Цель: набрать 21 очко или **близко к этому** путем нажатием на Взять карту. Если вы превысите 21 очко - вы проиграете (перебор)\n"
        f"• Туз = 1 или 11, фигуры = 10\n"
        f"• Больше 21 = проигрыш\n\n"
        f"⚡ **Команды админа:**\n"
        f"• `/блекджек+30сек` - добавить 30 секунд\n"
        f"• `/блекджек_начать` - начать досрочно"
        f"{players_list}"
    )

async def cmd_blackjack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /блекджек - начать игру (только для админов)"""
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    
    # Проверяем, что команду вызвал админ
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам!")
        return
    
    # Проверяем, что команда используется в группе
    if update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("❌ Блекджек можно играть только в группах!")
        return
    
    chat_id = update.effective_chat.id
    
    # Проверяем, нет ли уже активной игры в этом чате
    if chat_id in active_games:
        await update.message.reply_text("🎰 Игра уже идет! Дождитесь окончания текущей игры.")
        return
    
    # Создаем новую игру
    game = BlackjackGame(chat_id, update.effective_user.id)
    active_games[chat_id] = game
    
    # Создаем сообщение о наборе
    keyboard = game.get_signup_keyboard()
    message_text = create_signup_message(game, 60)
    
    try:
        # Пытаемся найти фото в папке res
        photo_path = "res/list.jpg"
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                message = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                game.has_photo_message = True
        else:
            message = await context.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            game.has_photo_message = False
    except Exception as e:
        logger.warning(f"Failed to send photo, sending text message: {e}")
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        game.has_photo_message = False
    
    game.signup_message_id = message.message_id
    
    # Запускаем таймер обновления
    asyncio.create_task(update_signup_timer(context, game))

async def cmd_blackjack_add_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /блекджек+30сек - добавить 30 секунд к таймеру"""
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    
    # Проверяем, что команду вызвал админ
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам!")
        return
    
    chat_id = update.effective_chat.id
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await update.message.reply_text("❌ Нет активной игры в блекджек!")
        return
    
    game = active_games[chat_id]
    
    # Проверяем, что игра еще в фазе набора
    if not game.is_signup_phase:
        await update.message.reply_text("❌ Игра уже началась!")
        return
    
    # Добавляем 30 секунд
    game.signup_end_time += 30
    
    # Удаляем команду админа
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete admin command: {e}")
    
    logger.info(f"Admin {update.effective_user.id} added 30 seconds to blackjack game in chat {chat_id}")

async def cmd_blackjack_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /блекджек_начать - начать игру досрочно"""
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    
    # Проверяем, что команду вызвал админ
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам!")
        return
    
    chat_id = update.effective_chat.id
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await update.message.reply_text("❌ Нет активной игры в блекджек!")
        return
    
    game = active_games[chat_id]
    
    # Проверяем, что игра еще в фазе набора
    if not game.is_signup_phase:
        await update.message.reply_text("❌ Игра уже началась!")
        return
    
    # Проверяем минимальное количество игроков
    if len(game.players) < MIN_PLAYERS:
        await update.message.reply_text(f"❌ Нужно минимум {MIN_PLAYERS} игрока для начала игры!")
        return
    
    # Удаляем команду админа
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete admin command: {e}")
    
    # Принудительно завершаем фазу набора
    game.signup_end_time = time.time()
    
    logger.info(f"Admin {update.effective_user.id} force-started blackjack game in chat {chat_id}")

async def cb_blackjack_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия кнопки присоединения к игре"""
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str = query.data.split(":")
        chat_id = int(chat_id_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем, что игра еще в фазе набора
    if not game.is_signup_phase:
        await query.answer("❌ Игра уже началась!", show_alert=True)
        return
    
    user = query.from_user
    username = user.username or ""
    
    balance = get_user_balance(user.id)
    if balance < 20:
        await query.answer("❌ Для участия нужно минимум 20 монет на балансе!", show_alert=True)
        return
    
    # Пытаемся добавить игрока
    if game.add_player(user.id, username, user.first_name):
        await query.answer(f"✅ Вы присоединились к игре!", show_alert=False)
        logger.info(f"Player {user.first_name} ({user.id}) joined blackjack game in chat {chat_id}")
        
        try:
            remaining_time = int(game.signup_end_time - time.time())
            keyboard = game.get_signup_keyboard()
            message_text = create_signup_message(game, remaining_time)
            
            if game.has_photo_message:
                await context.bot.edit_message_caption(
                    chat_id=game.chat_id,
                    message_id=game.signup_message_id,
                    caption=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.signup_message_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Failed to update signup message after player join: {e}")
            
    else:
        # Проверяем, не добавлен ли уже игрок
        for player in game.players:
            if player.user_id == user.id:
                await query.answer("❌ Вы уже участвуете в игре!", show_alert=True)
                return
        
        if len(game.players) >= MAX_PLAYERS:
            await query.answer("❌ Игра заполнена! Максимум игроков достигнут.", show_alert=True)
        else:
            await query.answer("❌ Не удалось присоединиться к игре!", show_alert=True)

async def cb_blackjack_hit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия кнопки 'Взять карту'"""
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str, player_index_str = query.data.split(":")
        chat_id = int(chat_id_str)
        player_index = int(player_index_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем, что это ход правильного игрока
    if (player_index != game.current_player_index or 
        game.players[player_index].user_id != query.from_user.id):
        await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    player = game.players[player_index]
    
    # Показываем анимацию "Достаю карту для игрока..."
    animation_text = f"🎰 **БЛЕКДЖЕК - ИГРА ИДЕТ**\n\n"
    animation_text += f"🏦 **Дилер:** {game.format_dealer_cards()} (очки: {game.dealer_cards[0].value}+?)\n\n"
    animation_text += "👥 **Игроки:**\n"
    for i, p in enumerate(game.players):
        status_icon = ""
        if p.is_blackjack:
            status_icon = "🎯"
        elif p.is_bust:
            status_icon = "💥"
        elif p.is_stand:
            status_icon = "✋"
        elif i == game.current_player_index:
            status_icon = "👉"
        
        animation_text += f"{status_icon} **{p.first_name}:** {game.format_cards(p.cards)} (очки: {p.score})\n"
    
    animation_text += f"\n🃏 **Достаю карту для {player.first_name}...**"
    
    # Обновляем сообщение с анимацией
    if game.game_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game.game_messages[-1],
                text=animation_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning(f"Failed to edit message with animation: {e}")
    
    await asyncio.sleep(2)
    
    # Выдаем карту
    if game.deck:
        card = game.deck.pop()
        player.cards.append(card)
        player.score = game.calculate_score(player.cards)
        
        if player.score > 21:
            player.is_bust = True
            await query.answer(f"💥 Перебор! У вас {player.score} очков.", show_alert=True)
            # Переходим к следующему игроку только при перебое
            await continue_game(context, game)
        else:
            await query.answer(f"🃏 Вы взяли {card}. Очки: {player.score}", show_alert=False)
            keyboard = game.get_game_keyboard(game.current_player_index)
            message_text = game.create_game_status_message()
            
            try:
                # Обновляем сообщение с новым состоянием
                await context.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.game_messages[-1],
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send updated game message: {e}")

async def cb_blackjack_stand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия кнопки 'Остановиться'"""
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str, player_index_str = query.data.split(":")
        chat_id = int(chat_id_str)
        player_index = int(player_index_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем, что это ход правильного игрока
    if (player_index != game.current_player_index or 
        game.players[player_index].user_id != query.from_user.id):
        await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return
    
    player = game.players[player_index]
    player.is_stand = True
    
    await query.answer(f"✋ Вы остановились с {player.score} очками.", show_alert=False)
    
    # Переходим к следующему игроку или завершаем игру
    await continue_game(context, game)

async def continue_game(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Продолжить игру - перейти к следующему игроку или завершить"""
    if game.next_player():
        current_player = game.get_current_player()
        if current_player:
            # Показываем анимацию перехода
            transition_text = f"🎰 **БЛЕКДЖЕК - ИГРА ИДЕТ**\n\n"
            transition_text += f"🏦 **Дилер:** {game.format_dealer_cards()} (очки: {game.dealer_cards[0].value}+?)\n\n"
            transition_text += "👥 **Игроки:**\n"
            for i, p in enumerate(game.players):
                status_icon = ""
                if p.is_blackjack:
                    status_icon = "🎯"
                elif p.is_bust:
                    status_icon = "💥"
                elif p.is_stand:
                    status_icon = "✋"
                elif i == game.current_player_index:
                    status_icon = "👉"
                
                transition_text += f"{status_icon} **{p.first_name}:** {game.format_cards(p.cards)} (очки: {p.score})\n"
            
            transition_text += f"\n🔄 **Перехожу к игроку {current_player.first_name}...**"
            
            # Обновляем сообщение с анимацией перехода
            if game.game_messages:
                try:
                    await context.bot.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.game_messages[-1],
                        text=transition_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit message with transition: {e}")
            
            await asyncio.sleep(2)
            
            # Показываем игровое меню для нового игрока
            keyboard = game.get_game_keyboard(game.current_player_index)
            message_text = game.create_game_status_message()
            
            try:
                await context.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.game_messages[-1],
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send game message: {e}")
    else:
        # Все игроки завершили ходы, играет дилер
        await dealer_turn(context, game)

async def dealer_turn(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Ход дилера с анимацией"""
    # Убираем кнопки и показываем переход к дилеру
    transition_text = f"🎰 **БЛЕКДЖЕК - ХОД ДИЛЕРА**\n\n"
    transition_text += f"🏦 **Дилер:** {game.format_dealer_cards()} (очки: {game.dealer_cards[0].value}+?)\n\n"
    transition_text += "👥 **Игроки завершили ходы:**\n"
    for player in game.players:
        status_icon = ""
        if player.is_blackjack:
            status_icon = "🎯"
        elif player.is_bust:
            status_icon = "💥"
        elif player.is_stand:
            status_icon = "✋"
        
        transition_text += f"{status_icon} **{player.first_name}:** {game.format_cards(player.cards)} (очки: {player.score})\n"
    
    transition_text += f"\n🎲 **Дилер открывает карты...**"
    
    if game.game_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game.game_messages[-1],
                text=transition_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning(f"Failed to edit message: {e}")
    
    await asyncio.sleep(3)
    
    # Открываем скрытую карту дилера
    game.dealer_score = game.calculate_score(game.dealer_cards)
    
    reveal_text = f"🎰 **БЛЕКДЖЕК - ХОД ДИЛЕРА**\n\n"
    reveal_text += f"🏦 **Дилер открыл карты:** {game.format_dealer_cards(hide_second=False)} (очки: {game.dealer_score})\n\n"
    reveal_text += "👥 **Игроки:**\n"
    for player in game.players:
        status_icon = ""
        if player.is_blackjack:
            status_icon = "🎯"
        elif player.is_bust:
            status_icon = "💥"
        elif player.is_stand:
            status_icon = "✋"
        
        reveal_text += f"{status_icon} **{player.first_name}:** {game.format_cards(player.cards)} (очки: {player.score})\n"
    
    if game.dealer_score < 17:
        reveal_text += f"\n🤔 **Выбираю взять карту...**"
    elif game.dealer_score == 21:
        reveal_text += f"\n🎯 **У дилера блекджек!**"
    elif game.dealer_score > 21:
        reveal_text += f"\n💥 **У дилера перебор!**"
    else:
        reveal_text += f"\n✋ **Дилер останавливается**"
    
    try:
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.game_messages[-1],
            text=reveal_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit dealer reveal message: {e}")
    
    await asyncio.sleep(3)
    
    # Дилер берет карты пока у него меньше 17
    while game.dealer_score < 17:
        if game.deck:
            # Анимация взятия карты дилером
            taking_text = reveal_text + f"\n\n🃏 **Дилер берет карту...**"
            
            try:
                await context.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.game_messages[-1],
                    text=taking_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to edit taking card message: {e}")
            
            await asyncio.sleep(2)
            
            # Берем карту
            card = game.deck.pop()
            game.dealer_cards.append(card)
            game.dealer_score = game.calculate_score(game.dealer_cards)
            
            # Обновляем сообщение с новой картой
            reveal_text = f"🎰 **БЛЕКДЖЕК - ХОД ДИЛЕРА**\n\n"
            reveal_text += f"🏦 **Дилер:** {game.format_dealer_cards(hide_second=False)} (очки: {game.dealer_score})\n\n"
            reveal_text += "👥 **Игроки:**\n"
            for player in game.players:
                status_icon = ""
                if player.is_blackjack:
                    status_icon = "🎯"
                elif player.is_bust:
                    status_icon = "💥"
                elif player.is_stand:
                    status_icon = "✋"
                
                reveal_text += f"{status_icon} **{player.first_name}:** {game.format_cards(player.cards)} (очки: {player.score})\n"
            
            reveal_text += f"\n🃏 **Дилер взял:** {card}"
            
            if game.dealer_score > 21:
                reveal_text += f"\n💥 **У дилера перебор!**"
            elif game.dealer_score >= 17:
                reveal_text += f"\n✋ **Дилер останавливается**"
            else:
                reveal_text += f"\n🤔 **Дилер должен брать еще...**"
            
            try:
                await context.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.game_messages[-1],
                    text=reveal_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to edit dealer card message: {e}")
            
            await asyncio.sleep(3)
    
    # Финальная пауза перед результатами
    final_dealer_text = reveal_text + f"\n\n⏳ **Подсчитываю результаты...**"
    
    try:
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.game_messages[-1],
            text=final_dealer_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit final dealer message: {e}")
    
    await asyncio.sleep(3)
    await end_game(context, game)

async def end_game(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Завершить игру и показать результаты"""
    from economy import (get_user_balance, add_user_balance, get_user_slave, 
                        set_user_slave, remove_user_slave, get_slave_owner)
    
    results_message = "🎰 **РЕЗУЛЬТАТЫ ИГРЫ**\n\n"
    results_message += f"🏦 **Дилер:** {game.format_dealer_cards(hide_second=False)} (очки: {game.dealer_score})\n\n"
    
    results_message += "👥 **Результаты игроков:**\n"
    
    winners = []
    slave_players = []  # игроки, которые поставили рабов
    slave_participating = []  # рабы, которые сами играют
    
    for player in game.players:
        result_icon = ""
        result_text = ""
        is_winner = False
        result_type = "loss"  # по умолчанию поражение
        
        if player.is_bust:
            result_icon = "💥"
            result_text = "Перебор - Проигрыш"
            result_type = "loss"
        elif player.is_blackjack and game.dealer_score != 21:
            result_icon = "🎯"
            result_text = "Блекджек - Победа!"
            is_winner = True
            result_type = "win"
        elif game.dealer_score > 21:
            result_icon = "🏆"
            result_text = "Победа! (у дилера перебор)"
            is_winner = True
            result_type = "win"
        elif player.score > game.dealer_score:
            result_icon = "🏆"
            result_text = "Победа!"
            is_winner = True
            result_type = "win"
        elif player.score == game.dealer_score:
            result_icon = "🤝"
            result_text = "Ничья"
            result_type = "draw"
        else:
            result_icon = "😞"
            result_text = "Проигрыш"
            result_type = "loss"
        
        if is_winner:
            winners.append(player)
        
        if player.slave_bet:
            slave_players.append(player)
        
        # Проверяем, является ли игрок рабом
        if get_slave_owner(player.user_id):
            slave_participating.append(player)
        
        update_player_stats(player.user_id, result_type, player.first_name)
        
        results_message += f"{result_icon} **{player.first_name}:** {game.format_cards(player.cards)} ({player.score}) - {result_text}\n"
    
    try:
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=results_message,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to send results message: {e}")
    
    try:
        await process_game_results(context, game, winners, slave_players, slave_participating)
    except Exception as e:
        logger.error(f"Error processing game results: {e}")
    
    # Удаляем игру из активных (всегда выполняется, даже если была ошибка в обработке результатов)
    if game.chat_id in active_games:
        del active_games[game.chat_id]
        logger.info(f"Game cleanup completed for chat {game.chat_id}")

async def process_game_results(context, game, winners, slave_players, slave_participating):
    """Обрабатывает результаты игры с упрощенной логикой рабов"""
    from economy import (add_user_balance, get_user_slave, set_user_slave, 
                        remove_user_slave, get_slave_owner)
    
    # Сначала обрабатываем обычные денежные выплаты для всех игроков
    for player in game.players:
        if not player.slave_bet:  # только денежные ставки
            if player.is_blackjack and game.dealer_score != 21:
                add_user_balance(player.user_id, int(player.bet * 2.5))
            elif game.dealer_score > 21 and not player.is_bust:
                add_user_balance(player.user_id, player.bet * 2)
            elif player.score > game.dealer_score and not player.is_bust:
                add_user_balance(player.user_id, player.bet * 2)
            elif player.score == game.dealer_score and not player.is_bust:
                add_user_balance(player.user_id, player.bet)
    
    # Теперь обрабатываем ставки рабами по упрощенным правилам
    for slave_player in slave_players:
        slave_info = slave_player.slave_bet_info
        if not slave_info:
            continue
            
        slave_id = slave_info["slave_id"]
        slave_name = slave_info["slave_name"]
        purchase_price = slave_info["purchase_price"]
        owner = slave_player  # хозяин
        
        # Проверяем, участвует ли раб в игре как игрок
        slave_as_player = next((p for p in game.players if p.user_id == slave_id), None)
        slave_is_winner = slave_as_player and slave_as_player in winners
        
        slave_has_tie = slave_as_player and not slave_as_player.is_bust and slave_as_player.score == game.dealer_score
        
        if slave_has_tie:
            set_user_slave(owner.user_id, slave_id, purchase_price, slave_name)
            await context.bot.send_message(
                chat_id=game.chat_id,
                text=f"🤝 Раб {slave_name} сыграл вничью с дилером - остается у хозяина {owner.first_name}"
            )
            continue
        
        if not winners:  # дилер единственный победитель
            set_user_slave(owner.user_id, slave_id, purchase_price, slave_name)
            # Хозяину выдается штраф в размере стоимости покупки раба
            add_user_balance(owner.user_id, -purchase_price)  # отнимаем деньги (штраф)
            
            await context.bot.send_message(
                chat_id=game.chat_id,
                text=f"🏦 Дилер выиграл! Раб {slave_name} остается у хозяина {owner.first_name}, но хозяин получает штраф {purchase_price} монет"
            )
            continue
        
        # Правило 1: Если один из победителей сам раб - он получает ТОЛЬКО свободу
        if slave_is_winner:
            # Раб получает свободу
            await context.bot.send_message(
                chat_id=game.chat_id,
                text=f"🎉 Раб {slave_name} выиграл и получил свободу!"
            )
            try:
                await context.bot.send_message(
                    chat_id=slave_id,
                    text=f"🎉 Вы выиграли в блекджек и получили свободу!"
                )
            except:
                pass
            
            # Остальные победители (кроме раба) получают деньги поровну
            other_winners = [w for w in winners if w.user_id != slave_id]
            if other_winners:
                share_per_winner = purchase_price // len(other_winners)
                for winner in other_winners:
                    add_user_balance(winner.user_id, share_per_winner)
                
                await context.bot.send_message(
                    chat_id=game.chat_id,
                    text=f"💰 {len(other_winners)} других победителей получают по {share_per_winner} монет за освобожденного раба"
                )
            continue
        
        # Правило 2: Если победитель один и это хозяин - получает раба обратно + деньги
        if len(winners) == 1 and winners[0] == owner:
            set_user_slave(owner.user_id, slave_id, purchase_price, slave_name)
            # Денежный выигрыш уже начислен выше
            await context.bot.send_message(
                chat_id=game.chat_id,
                text=f"🏆 {owner.first_name} выиграл и возвращает себе раба {slave_name}!"
            )
            continue
        
        # Правило 3: Если победитель один и он НЕ бот и НЕ раб - получает раба
        if len(winners) == 1:
            winner = winners[0]
            # Проверяем, что победитель не раб
            if not get_slave_owner(winner.user_id):
                set_user_slave(winner.user_id, slave_id, purchase_price, slave_name)
                await context.bot.send_message(
                    chat_id=game.chat_id,
                    text=f"👑 {winner.first_name} выиграл и получает раба {slave_name}!"
                )
                try:
                    await context.bot.send_message(
                        chat_id=slave_id,
                        text=f"⛓️ У вас новый хозяин: {winner.first_name}!"
                    )
                except:
                    pass
                continue
        
        # Правило 4: Во всех остальных случаях раб считается как деньги
        # Победители получают долю от стоимости раба
        if winners:
            share_per_winner = purchase_price // len(winners)
            for winner in winners:
                add_user_balance(winner.user_id, share_per_winner)
            
            await context.bot.send_message(
                chat_id=game.chat_id,
                text=f"💰 {len(winners)} победителей получают по {share_per_winner} монет за раба {slave_name}"
            )


async def show_betting_for_player(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame, player_index: int):
    """Показать интерфейс ставок для игрока"""
    from economy import get_user_balance, get_user_slave
    
    player = game.players[player_index]
    balance = get_user_balance(player.user_id)
    slave_info = get_user_slave(player.user_id)
    
    betting_text = f"🎰 **БЛЕКДЖЕК - СТАВКИ**\n\n"
    betting_text += f"👤 **Ход игрока:** {player.first_name}\n"
    betting_text += f"💰 **Баланс:** {balance} монет\n"
    
    if player.slave_bet and player.slave_bet_info:
        betting_text += f"👤 **Ставка:** Раб {player.slave_bet_info['slave_name']}\n\n"
    else:
        betting_text += f"🎯 **Текущая ставка:** {player.temp_bet} монет\n\n"
    
    # Показываем других игроков и их ставки
    betting_text += "👥 **Игроки:**\n"
    for i, p in enumerate(game.players):
        if i < player_index:
            if p.slave_bet and p.slave_bet_info:
                betting_text += f"✅ **{p.first_name}:** Раб {p.slave_bet_info['slave_name']}\n"
            else:
                betting_text += f"✅ **{p.first_name}:** {p.bet} монет\n"
        elif i == player_index:
            betting_text += f"👉 **{p.first_name}:** делает ставку...\n"
        else:
            betting_text += f"⏳ **{p.first_name}:** ожидает\n"
    
    betting_text += f"\n💡 **Выберите фишки для ставки:**"
    
    keyboard = game.get_betting_keyboard(player_index)
    
    try:
        betting_msg = await context.bot.send_message(
            chat_id=game.chat_id,
            text=betting_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        game.game_messages.append(betting_msg.message_id)
    except Exception as e:
        logger.error(f"Failed to send betting message: {e}")

async def cb_blackjack_bet_slave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ставки рабом"""
    from economy import get_user_slave, remove_user_slave
    
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str, player_index_str = query.data.split(":")
        chat_id = int(chat_id_str)
        player_index = int(player_index_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем фазу ставок и правильного игрока
    if (not game.is_betting_phase or 
        player_index != game.current_betting_player or 
        game.players[player_index].user_id != query.from_user.id):
        await query.answer("❌ Сейчас не ваш ход для ставки!", show_alert=True)
        return
    
    player = game.players[player_index]
    slave_info = get_user_slave(player.user_id)
    
    # Проверяем, есть ли раб
    if not slave_info:
        await query.answer("❌ У вас нет раба!", show_alert=True)
        return
    
    # Проверяем, что нет денежной ставки
    if player.temp_bet > 0:
        await query.answer("❌ Нельзя ставить раба вместе с деньгами!", show_alert=True)
        return
    
    # Ставим раба
    player.slave_bet = True
    player.slave_bet_info = slave_info.copy()
    
    # Забираем раба у игрока
    remove_user_slave(player.user_id)
    
    await query.answer(f"👤 Поставлен раб: {slave_info['slave_name']}", show_alert=False)
    
    # Обновляем сообщение
    await update_betting_message(context, game, player_index)

async def update_betting_message(context, game, player_index):
    """Обновляет сообщение ставок"""
    from economy import get_user_balance, get_user_slave
    
    player = game.players[player_index]
    balance = get_user_balance(player.user_id)
    
    betting_text = f"🎰 **БЛЕКДЖЕК - СТАВКИ**\n\n"
    betting_text += f"👤 **Ход игрока:** {player.first_name}\n"
    betting_text += f"💰 **Баланс:** {balance} монет\n"
    
    if player.slave_bet and player.slave_bet_info:
        betting_text += f"👤 **Ставка:** Раб {player.slave_bet_info['slave_name']}\n\n"
    else:
        betting_text += f"🎯 **Текущая ставка:** {player.temp_bet} монет\n\n"
    
    # Показываем других игроков и их ставки
    betting_text += "👥 **Игроки:**\n"
    for i, p in enumerate(game.players):
        if i < player_index:
            if p.slave_bet and p.slave_bet_info:
                betting_text += f"✅ **{p.first_name}:** Раб {p.slave_bet_info['slave_name']}\n"
            else:
                betting_text += f"✅ **{p.first_name}:** {p.bet} монет\n"
        elif i == player_index:
            betting_text += f"👉 **{p.first_name}:** делает ставку...\n"
        else:
            betting_text += f"⏳ **{p.first_name}:** ожидает\n"
    
    betting_text += f"\n💡 **Выберите фишки для ставки:**"
    
    keyboard = game.get_betting_keyboard(player_index)
    
    try:
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.game_messages[-1],
            text=betting_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to update betting message: {e}")

async def cb_blackjack_bet_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка сброса ставки"""
    from economy import get_user_balance, set_user_slave
    
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str, player_index_str = query.data.split(":")
        chat_id = int(chat_id_str)
        player_index = int(player_index_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем фазу ставок и правильного игрока
    if (not game.is_betting_phase or 
        player_index != game.current_betting_player or 
        game.players[player_index].user_id != query.from_user.id):
        await query.answer("❌ Сейчас не ваш ход для ставки!", show_alert=True)
        return
    
    player = game.players[player_index]
    
    if player.slave_bet and player.slave_bet_info:
        slave_info = player.slave_bet_info
        set_user_slave(player.user_id, slave_info["slave_id"], 
                      slave_info["purchase_price"], slave_info["slave_name"])
        player.slave_bet = False
        player.slave_bet_info = None
        await query.answer("🗑️ Ставка раба сброшена!", show_alert=False)
    else:
        player.temp_bet = 0
        await query.answer("🗑️ Ставка сброшена!", show_alert=False)
    
    # Обновляем сообщение
    await update_betting_message(context, game, player_index)

async def cb_blackjack_bet_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка принятия ставки"""
    from economy import get_user_balance, add_user_balance
    
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    
    await query.answer()
    
    # Парсим данные callback
    try:
        _, chat_id_str, player_index_str = query.data.split(":")
        chat_id = int(chat_id_str)
        player_index = int(player_index_str)
    except (ValueError, IndexError):
        await query.answer("❌ Ошибка обработки команды.", show_alert=True)
        return
    
    # Проверяем, есть ли активная игра
    if chat_id not in active_games:
        await query.answer("❌ Игра уже завершена!", show_alert=True)
        return
    
    game = active_games[chat_id]
    
    # Проверяем фазу ставок и правильного игрока
    if (not game.is_betting_phase or 
        player_index != game.current_betting_player or 
        game.players[player_index].user_id != query.from_user.id):
        await query.answer("❌ Сейчас не ваш ход для ставки!", show_alert=True)
        return
    
    player = game.players[player_index]
    
    if player.slave_bet:
        # Ставка рабом
        if not player.slave_bet_info:
            await query.answer("❌ Ошибка данных раба!", show_alert=True)
            return
        
        player.bet = player.slave_bet_info["purchase_price"]  # для отображения
        await query.answer(f"✅ Ставка рабом {player.slave_bet_info['slave_name']} принята!", show_alert=False)
    else:
        # Денежная ставка
        if player.temp_bet <= 0:
            await query.answer("❌ Сделайте ставку перед принятием!", show_alert=True)
            return
        
        # Списываем деньги и подтверждаем ставку
        if not add_user_balance(player.user_id, -player.temp_bet):
            await query.answer("❌ Ошибка списания средств!", show_alert=True)
            return
        
        player.bet = player.temp_bet
        await query.answer(f"✅ Ставка {player.bet} монет принята!", show_alert=False)
    
    player.temp_bet = 0
    
    # Переходим к следующему игроку или начинаем игру
    game.current_betting_player += 1
    
    if game.current_betting_player >= len(game.players):
        # Все игроки сделали ставки, начинаем игру
        game.is_betting_phase = False
        await animated_card_dealing(context, game)
    else:
        # Переходим к следующему игроку
        try:
            await context.bot.delete_message(
                chat_id=game.chat_id,
                message_id=game.game_messages[-1]
            )
            game.game_messages.pop()
        except Exception as e:
            logger.warning(f"Failed to delete betting message: {e}")
        
        await show_betting_for_player(context, game, game.current_betting_player)

async def animated_card_dealing(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Анимированная раздача карт"""
    try:
        # Удаляем сообщение о наборе игроков
        await context.bot.delete_message(
            chat_id=game.chat_id,
            message_id=game.signup_message_id
        )
    except Exception as e:
        logger.warning(f"Failed to delete signup message: {e}")
    
    # Начальное сообщение
    initial_text = "🎰 **БЛЕКДЖЕК - ИГРА НАЧАЛАСЬ!**\n\nРаздача карт..."
    
    try:
        game_msg = await context.bot.send_message(
            chat_id=game.chat_id,
            text=initial_text,
            parse_mode=ParseMode.MARKDOWN
        )
        game.game_messages.append(game_msg.message_id)
    except Exception as e:
        logger.error(f"Failed to send initial message: {e}")
        return
    
    await asyncio.sleep(3)
    
    # Создаем колоду и начинаем игру
    game.is_signup_phase = False
    game.is_game_active = True
    game.deck = game.create_deck()
    
    # Показываем список игроков
    players_text = "🎰 **БЛЕКДЖЕК - ИГРА НАЧАЛАСЬ!**\n\n👥 **Игроки получили:**\n"
    for player in game.players:
        players_text += f"• **{player.first_name}:** \n"
    
    try:
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game_msg.message_id,
            text=players_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
    
    await asyncio.sleep(2)
    
    # Первый круг - раздаем по одной карте каждому игроку
    for i, player in enumerate(game.players):
        card = game.deck.pop()
        player.cards.append(card)
        
        # Обновляем сообщение с новой картой
        updated_text = "🎰 **БЛЕКДЖЕК - ИГРА НАЧАЛАСЬ!**\n\n👥 **Игроки получили:**\n"
        for j, p in enumerate(game.players):
            if j <= i:
                updated_text += f"• **{p.first_name}:** {game.format_cards(p.cards)}\n"
            else:
                updated_text += f"• **{p.first_name}:** \n"
        
        try:
            await context.bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game_msg.message_id,
                text=updated_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
        
        await asyncio.sleep(1.5)
    
    # Дилер получает первую карту
    dealer_first_card = game.deck.pop()
    game.dealer_cards.append(dealer_first_card)
    
    updated_text = "🎰 **БЛЕКДЖЕК - ИГРА НАЧАЛАСЬ!**\n\n"
    updated_text += f"🏦 **Дилер:** {dealer_first_card}\n\n"
    updated_text += "👥 **Игроки получили:**\n"
    for player in game.players:
        updated_text += f"• **{player.first_name}:** {game.format_cards(p.cards)}\n"
    
    try:
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game_msg.message_id,
            text=updated_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
    
    await asyncio.sleep(2)
    
    # Второй круг - раздаем вторую карту игрокам
    for i, player in enumerate(game.players):
        card = game.deck.pop()
        player.cards.append(card)
        player.score = game.calculate_score(player.cards)
        
        # Проверяем блекджек
        if player.score == 21:
            player.is_blackjack = True
        
        # Обновляем сообщение
        updated_text = "🎰 **БЛЕКДЖЕК - ИГРА НАЧАЛАСЬ!**\n\n"
        updated_text += f"🏦 **Дилер:** {dealer_first_card} + 🂠\n\n"
        updated_text += "👥 **Игроки получили:**\n"
        for j, p in enumerate(game.players):
            if j <= i:
                cards_text = game.format_cards(p.cards)
                score_text = f" (очки: {p.score})"
                if p.is_blackjack:
                    score_text += " 🎯"
                updated_text += f"• **{p.first_name}:** {cards_text}{score_text}\n"
            else:
                updated_text += f"• **{p.first_name}:** {game.format_cards(p.cards)}\n"
        
        try:
            await context.bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game_msg.message_id,
                text=updated_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
        
        await asyncio.sleep(1.5)
    
    # Дилер получает вторую карту (скрытую)
    dealer_hidden_card = game.deck.pop()
    game.dealer_cards.append(dealer_hidden_card)
    game.dealer_hidden_card = dealer_hidden_card
    game.dealer_score = game.calculate_score(game.dealer_cards)
    
    await asyncio.sleep(2)
    
    # Финальное сообщение о раздаче
    final_text = "🎰 **БЛЕКДЖЕК - РАЗДАЧА ЗАВЕРШЕНА**\n\n"
    final_text += f"🏦 **Дилер:** {dealer_first_card} + 🂠\n\n"
    final_text += "👥 **Игроки:**\n"
    for player in game.players:
        cards_text = game.format_cards(player.cards)
        score_text = f" (очки: {player.score})"
        if player.is_blackjack:
            score_text += " 🎯"
        final_text += f"• **{player.first_name}:** {cards_text}{score_text}\n"
    
    try:
        await context.bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game_msg.message_id,
            text=final_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
    
    await asyncio.sleep(3)
    
    # Начинаем ходы игроков
    current_player = game.get_current_player()
    if current_player and not current_player.is_blackjack:
        keyboard = game.get_game_keyboard(game.current_player_index)
        message_text = game.create_game_status_message()
        
        try:
            msg = await context.bot.send_message(
                chat_id=game.chat_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            game.game_messages.append(msg.message_id)
        except Exception as e:
            logger.error(f"Failed to send game message: {e}")
    else:
        # Если у первого игрока блекджек, переходим к следующему
        await continue_game(context, game)

async def update_signup_timer(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Обновлять таймер набора игроков"""
    while game.is_signup_phase and time.time() < game.signup_end_time:
        remaining_time = int(game.signup_end_time - time.time())
        
        if remaining_time <= 0:
            break
        
        # Обновляем сообщение каждые 5 секунд
        if remaining_time % 5 == 0 or remaining_time <= 10:
            try:
                keyboard = game.get_signup_keyboard()
                message_text = create_signup_message(game, remaining_time)
                
                if game.has_photo_message:
                    await context.bot.edit_message_caption(
                        chat_id=game.chat_id,
                        message_id=game.signup_message_id,
                        caption=message_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await context.bot.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.signup_message_id,
                        text=message_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                    )
            except Exception as e:
                logger.warning(f"Failed to update signup message: {e}")
        
        await asyncio.sleep(1)
    
    # Время вышло или игра началась досрочно
    if game.is_signup_phase:
        await end_signup_phase(context, game)

async def end_signup_phase(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Завершить фазу набора игроков"""
    if len(game.players) < MIN_PLAYERS:
        # Недостаточно игроков - отменяем игру
        cancel_text = f"❌ **ИГРА ОТМЕНЕНА**\n\nНедостаточно игроков для начала игры!\nТребуется минимум {MIN_PLAYERS} игрока, записалось: {len(game.players)}"
        
        try:
            if game.has_photo_message:
                await context.bot.edit_message_caption(
                    chat_id=game.chat_id,
                    message_id=game.signup_message_id,
                    caption=cancel_text,
                    reply_markup=None,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=game.chat_id,
                    message_id=game.signup_message_id,
                    text=cancel_text,
                    reply_markup=None,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.error(f"Failed to send cancel message: {e}")
        
        # Удаляем игру из активных
        if game.chat_id in active_games:
            del active_games[game.chat_id]
        
        logger.info(f"Blackjack game cancelled in chat {game.chat_id} - not enough players")
        return
    
    # Достаточно игроков - начинаем фазу ставок
    game.is_signup_phase = False
    game.is_betting_phase = True
    game.current_betting_player = 0
    
    logger.info(f"Starting betting phase for blackjack game in chat {game.chat_id} with {len(game.players)} players")
    
    # Показываем интерфейс ставок для первого игрока
    await show_betting_for_player(context, game, 0)

async def message_filter_task(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Задача для удаления сообщений не от игроков во время игры"""
    # Эта функция будет вызываться из обработчика сообщений в main.py
    # Здесь мы просто сохраняем ссылку на игру для использования в main.py
    pass

async def delete_non_game_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Удалять сообщения не по теме во время игры"""
    # TODO: Реализовать удаление сообщений не по теме
    # Это требует отслеживания всех сообщений в чате во время игры
    # и удаления тех, которые не связаны с игрой
    pass

def is_game_active(chat_id: int) -> bool:
    """Проверить, идет ли активная игра в чате"""
    return chat_id in active_games and active_games[chat_id].is_game_active

def is_player_in_game(chat_id: int, user_id: int) -> bool:
    """Проверить, является ли пользователь игроком в активной игре"""
    if chat_id not in active_games:
        return False
    return user_id in active_games[chat_id].player_ids
