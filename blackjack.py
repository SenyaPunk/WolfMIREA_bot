import asyncio
import random
import time
import logging
import os
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from admin import is_admin

logger = logging.getLogger(__name__)

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
    user_id: int
    username: str
    first_name: str
    cards: List[Card] = field(default_factory=list)
    score: int = 0
    is_bust: bool = False
    is_blackjack: bool = False
    is_stand: bool = False

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

def create_signup_message(game: BlackjackGame, remaining_time: int) -> str:
    """Создать сообщение для набора игроков"""
    minutes = remaining_time // 60
    seconds = remaining_time % 60
    
    players_list = ""
    if game.players:
        players_list = "\n\n👥 **Игроки:**\n"
        for i, player in enumerate(game.players, 1):
            players_list += f"{i}. {player.first_name}\n"
    
    return (
        f"🎰 **БЛЕКДЖЕК - НАБОР ИГРОКОВ**\n\n"
        f"⏰ Время на запись: **{minutes:02d}:{seconds:02d}**\n"
        f"👥 Игроков: **{len(game.players)}/{MAX_PLAYERS}**\n"
        f"🎯 Минимум для начала: **{MIN_PLAYERS} игрока**\n\n"
        f"📋 **Правила:**\n"
        f"• Стандартная колода карт (52 карты)\n"
        f"• Цель: набрать 21 очко или близко к этому\n"
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
    
    # Пытаемся добавить игрока
    if game.add_player(user.id, username, user.first_name):
        await query.answer(f"✅ Вы присоединились к игре!", show_alert=False)
        logger.info(f"Player {user.first_name} ({user.id}) joined blackjack game in chat {chat_id}")
    else:
        # Проверяем, не добавлен ли уже игрок
        for player in game.players:
            if player.user_id == user.id:
                await query.answer("❌ Вы уже в игре!", show_alert=True)
                return
        
        # Игра переполнена
        await query.answer("❌ Игра переполнена!", show_alert=True)

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
        reveal_text += f"\n🤔 **Дилер должен брать карты (меньше 17)...**"
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
    results_message = "🎰 **РЕЗУЛЬТАТЫ ИГРЫ**\n\n"
    results_message += f"🏦 **Дилер:** {game.format_dealer_cards(hide_second=False)} (очки: {game.dealer_score})\n\n"
    
    results_message += "👥 **Результаты игроков:**\n"
    
    for player in game.players:
        result_icon = ""
        result_text = ""
        
        if player.is_bust:
            result_icon = "💥"
            result_text = "Перебор - Проигрыш"
        elif player.is_blackjack and game.dealer_score != 21:
            result_icon = "🎯"
            result_text = "Блекджек - Победа!"
        elif game.dealer_score > 21:
            result_icon = "🏆"
            result_text = "Победа! (у дилера перебор)"
        elif player.score > game.dealer_score:
            result_icon = "🏆"
            result_text = "Победа!"
        elif player.score == game.dealer_score:
            result_icon = "🤝"
            result_text = "Ничья"
        else:
            result_icon = "😞"
            result_text = "Проигрыш"
        
        results_message += f"{result_icon} **{player.first_name}:** {game.format_cards(player.cards)} ({player.score}) - {result_text}\n"
    
    try:
        await context.bot.send_message(
            chat_id=game.chat_id,
            text=results_message,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to send results message: {e}")
    
    # Удаляем игру из активных
    if game.chat_id in active_games:
        del active_games[game.chat_id]
    
    logger.info(f"Blackjack game ended in chat {game.chat_id}")

async def end_signup_phase(context: ContextTypes.DEFAULT_TYPE, game: BlackjackGame):
    """Завершить фазу набора игроков и начать игру"""
    # Проверяем минимальное количество игроков
    if len(game.players) < MIN_PLAYERS:
        try:
            await context.bot.edit_message_text(
                chat_id=game.chat_id,
                message_id=game.signup_message_id,
                text=f"❌ **ИГРА ОТМЕНЕНА**\n\nНедостаточно игроков для начала игры.\nТребуется минимум {MIN_PLAYERS} игрока, записалось: {len(game.players)}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to update signup message: {e}")
        
        # Удаляем игру из активных
        if game.chat_id in active_games:
            del active_games[game.chat_id]
        return
    
    await animated_card_dealing(context, game)

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
        updated_text += f"• **{player.first_name}:** {game.format_cards(player.cards)}\n"
    
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
