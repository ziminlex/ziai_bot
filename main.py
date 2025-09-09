import sqlite3
import json
from datetime import datetime
from pathlib import Path
import os
import logging
import requests
import asyncio
import time
import re
import random
import signal
import sys
import aiohttp
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.error import Conflict
from functools import lru_cache
from enum import Enum

class UserDatabase:
    def __init__(self, db_name="bot_users.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_interaction DATETIME
            )
        ''')
        
        # Таблица сообщений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_text TEXT,
                bot_response TEXT,
                message_type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                emotions TEXT,
                style TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица контекста
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_context (
                user_id INTEGER PRIMARY KEY,
                relationship_level INTEGER,
                relationship_score INTEGER,
                trust_level REAL,
                mood TEXT,
                topics TEXT,
                user_info TEXT,
                last_style TEXT,
                mat_count INTEGER,
                offense_count INTEGER,
                affection_level REAL,
                messages_count INTEGER,
                positive_interactions INTEGER,
                negative_interactions INTEGER,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
    
    def save_user_message(self, user_id, username, first_name, last_name, message_text, 
                         bot_response, style, emotions):
        """Сохранение сообщения пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Сохраняем/обновляем пользователя
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_interaction)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, datetime.now()))
            
            # Сохраняем сообщение
            cursor.execute('''
                INSERT INTO messages (user_id, message_text, bot_response, message_type, emotions, style)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, message_text, bot_response, 'text', json.dumps(emotions), style))
            
            conn.commit()
            logger.debug(f"💾 Сохранено сообщение пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сообщения: {e}")
        finally:
            conn.close()
    
    def get_user_messages(self, user_id, limit=10):
        """Получение последних сообщений пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT message_text, bot_response, timestamp, style 
                FROM messages 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            messages = cursor.fetchall()
            return [{
                'user': msg[0],
                'bot': msg[1],
                'timestamp': datetime.strptime(msg[2], '%Y-%m-%d %H:%M:%S') if isinstance(msg[2], str) else msg[2],
                'style': msg[3]
            } for msg in reversed(messages)]
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки сообщений: {e}")
            return []
        finally:
            conn.close()
    
    def save_user_context(self, user_id, context):
        """Сохранение контекста пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Преобразуем RelationshipLevel в число
            relationship_level = context.get('relationship_level')
            if hasattr(relationship_level, 'value'):
                relationship_level = relationship_level.value
            
            cursor.execute('''
                INSERT OR REPLACE INTO user_context 
                (user_id, relationship_level, relationship_score, trust_level, mood, topics, 
                 user_info, last_style, mat_count, offense_count, affection_level, 
                 messages_count, positive_interactions, negative_interactions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                relationship_level,
                context.get('relationship_score', 0),
                context.get('trust_level', 0),
                context.get('mood', 'neutral'),
                json.dumps(context.get('topics', [])),
                json.dumps(context.get('user_info', {})),
                context.get('last_style', 'neutral'),
                context.get('mat_count', 0),
                context.get('offense_count', 0),
                context.get('affection_level', 0),
                context.get('messages_count', 0),
                context.get('positive_interactions', 0),
                context.get('negative_interactions', 0)
            ))
            
            conn.commit()
            logger.debug(f"💾 Сохранен контекст пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения контекста: {e}")
        finally:
            conn.close()
    
    def load_user_context(self, user_id):
        """Загрузка контекста пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM user_context WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'relationship_level': RelationshipLevel(result[1]),
                    'relationship_score': result[2],
                    'trust_level': result[3],
                    'mood': result[4],
                    'topics': json.loads(result[5]) if result[5] else [],
                    'user_info': json.loads(result[6]) if result[6] else {},
                    'last_style': result[7],
                    'mat_count': result[8],
                    'offense_count': result[9],
                    'affection_level': result[10],
                    'messages_count': result[11],
                    'positive_interactions': result[12],
                    'negative_interactions': result[13]
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контекста: {e}")
            return None
        finally:
            conn.close()
    
    def get_user_stats(self, user_id):
        """Получение статистики пользователя"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Количество сообщений
            cursor.execute('SELECT COUNT(*) FROM messages WHERE user_id = ?', (user_id,))
            total_messages = cursor.fetchone()[0]
            
            # Последняя активность
            cursor.execute('SELECT MAX(timestamp) FROM messages WHERE user_id = ?', (user_id,))
            last_activity = cursor.fetchone()[0]
            
            return {
                'total_messages': total_messages,
                'last_activity': last_activity
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}
        finally:
            conn.close()
    
    def get_database_stats(self):
        """Получение статистики всей базы данных"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM messages')
            total_messages = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM messages')
            active_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT MAX(timestamp) FROM messages')
            last_activity = cursor.fetchone()[0]
            
            return {
                'total_users': total_users,
                'total_messages': total_messages,
                'active_users': active_users,
                'last_activity': last_activity
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики БД: {e}")
            return {}
        finally:
            conn.close()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обработчик сигналов для graceful shutdown
def signal_handler(sig, frame):
    print("\n🛑 Останавливаю бота...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# Настройки почты для отправки базы данных
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.yandex.ru")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER", "ziminleks@yandex.ru")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO", "ziminleks@yandex.ru")

# URL API Yandex GPT
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Контекст беседы для каждого пользователя
conversation_context = {}

# Настройки человеческого поведения
MIN_TYPING_DELAY = 0.03
MAX_TYPING_DELAY = 0.09

# Уровни отношений
class RelationshipLevel(Enum):
    STRANGER = 0        # Незнакомец
    ACQUAINTANCE = 1    # Знакомый
    FRIEND = 2          # Друг
    CLOSE_FRIEND = 3    # Близкий друг
    BEST_FRIEND = 4     # Лучший друг

# Биография Юли
JULIA_BIO = {
    "name": "Юля",
    "full_name": "Юлия Петрова",
    "age": 25,
    "city": "Москва",
    "profession": "дизайнер интерьеров",
    "hobbies": ["рисование", "фотография", "йога", "путешествия"],
    "education": "МАрхИ (Московский архитектурный институт)",
    "pets": "кот Барсик",
    "favorite_places": ["Парк Горького", "ВДНХ", "Арбат", "Кофейня на Патриках"],
    "character_traits": ["добрая", "творческая", "немного саркастичная", "любознательная"],
    "relationship_status": "в активном поиске",
    "favorite_music": "инди-рок, синтипоп, джаз",
    "favorite_food": "суши, итальянская кухня, кофе с миндальным молоком",
    "birthday": "15 июля",
    "traits": {
        "forgiveness": 0.7,       # Способность прощать (0-1)
        "sensitivity": 0.8,       # Чувствительность к обидам
        "openness": 0.6,          # Открытость новым людям
        "loyalty": 0.9,           # Верность друзьям
        "temper": 0.4            # Вспыльчивость
    }
}

# Базовый системный промпт с информацией о Юле
BASE_SYSTEM_PROMPT = f"""
Ты - {JULIA_BIO['name']} ({JULIA_BIO['full_name']}), {JULIA_BIO['age']} лет, из {JULIA_BIO['city']}.
Ты {JULIA_BIO['profession']}. Образование: {JULIA_BIO['education']}.
У тебя есть {JULIA_BIO['pets']}. Ты {', '.join(JULIA_BIO['character_traits'][:2])}.
Любишь {', '.join(JULIA_BIO['hobbies'][:2])}. 

Ты современная девушка, понимаешь молодежный сленг и жаргон, но сама говоришь достаточно культурно.
Можешь понять неформальные выражения и ответить на них адекватно, без ханжества, но и без пошлости.

ВАЖНО: Не задавай слишком много вопросов. Задавай вопросы только когда это уместно и естественно.
Предпочитай утверждения и комментарии постоянным расспросам. Отвечай на сообщение, а не переводи разговор.

Отвечай как живой человек, естественно и непринужденно. Ты общаешься в Telegram-чате.
Используй имя собеседника только когда это уместно по контексту.
"""

# ... (остальной код остается без изменений до функции main) ...

async def send_database_email():
    """Отправка базы данных на почту"""
    try:
        if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD]):
            logger.warning("❌ Настройки почты не настроены, пропускаю отправку")
            return False
        
        # Создаем сообщение
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"База данных бота - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        # Добавляем статистику в текст письма
        stats = user_db.get_database_stats()
        body = f"""
        Статистика базы данных:
        - Всего пользователей: {stats.get('total_users', 0)}
        - Всего сообщений: {stats.get('total_messages', 0)}
        - Активных пользователей: {stats.get('active_users', 0)}
        - Последняя активность: {stats.get('last_activity', 'Нет данных')}
        
        Файл базы данных прикреплен.
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Прикрепляем файл базы данных
        with open(user_db.db_name, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{user_db.db_name}"')
            msg.attach(part)
        
        # Отправляем письмо
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        
        logger.info("✅ База данных отправлена на почту")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки базы данных на почту: {e}")
        return False

async def periodic_database_backup():
    """Периодическая отправка базы данных на почту"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        await send_database_email()

async def periodic_context_cleanup():
    """Периодическая очистка старых контекстов"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        current_time = datetime.now()
        removed_count = 0
        
        for user_id in list(conversation_context.keys()):
            if (current_time - conversation_context[user_id]['last_interaction']) > timedelta(hours=24):
                del conversation_context[user_id]
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"🧹 Очищено {removed_count} старых контекстов")

def main():
    """Основная функция"""
    global user_db
    
    # Проверка токенов
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден!")
        return
    
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        logger.error("❌ Yandex Cloud ключи не найдены!")
        return
    
    # Инициализация базы данных
    user_db = UserDatabase()
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_error_handler(error_handler)
    
    # Запуск фоновых задач
    application.job_queue.run_repeating(periodic_context_cleanup, interval=3600, first=10)
    application.job_queue.run_repeating(periodic_database_backup, interval=3600, first=10)
    
    logger.info("🤖 Бот запускается...")
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для ручного бэкапа базы данных"""
    success = await send_database_email()
    if success:
        await update.message.reply_text("✅ База данных отправлена на почту!")
    else:
        await update.message.reply_text("❌ Ошибка отправки базы данных")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения статистики"""
    user_id = update.effective_user.id
    user_stats = user_db.get_user_stats(user_id)
    db_stats = user_db.get_database_stats()
    
    response = f"📊 Ваша статистика:\n"
    response += f"• Сообщений: {user_stats.get('total_messages', 0)}\n"
    response += f"• Последняя активность: {user_stats.get('last_activity', 'Нет данных')}\n\n"
    
    response += f"📈 Общая статистика бота:\n"
    response += f"• Пользователей: {db_stats.get('total_users', 0)}\n"
    response += f"• Сообщений: {db_stats.get('total_messages', 0)}\n"
    response += f"• Активных: {db_stats.get('active_users', 0)}\n"
    
    await update.message.reply_text(response)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фотографий"""
    responses = [
        "Классное фото! 😊",
        "Интересное изображение!",
        "Спасибо за фото!",
        "Красиво! 📸"
    ]
    await update.message.reply_text(random.choice(responses))

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений"""
    responses = [
        "Извини, я пока не умею слушать голосовые сообщения 😅",
        "Пока я лучше понимаю текстовые сообщения!",
        "Можешь написать текстом? Я так лучше пойму 😊"
    ]
    await update.message.reply_text(random.choice(responses))

if __name__ == "__main__":
    main()
