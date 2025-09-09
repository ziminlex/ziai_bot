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

# URL API Yandex GPT
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Кэш для частых запросов
request_cache = {}
CACHE_TIMEOUT = 300

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

# Словарь жаргонных слова и их нормальных аналогов
SLANG_DICTIONARY = {
    'сру': ['иду в туалет', 'занимаюсь делами', 'посещаю уборную'],
    'писать': ['иду в туалет', 'хочу в туалет', 'нужно в уборную'],
    'по маленькому': ['в туалет', 'в уборную', 'по нужде'],
    'по большому': ['в туалет', 'в уборную', 'по серьезному'],
    'ссать': ['мочиться', 'ходить в туалет'],
    'пердеть': ['пукать', 'выпускать газы'],
    'трахаться': ['заниматься сексом', 'быть интимно'],
    'секс': ['интимная близость', 'любовь'],
    'жопа': ['попа', 'задница'],
    'задница': ['пятая точка', 'нижняя часть'],
    'блять': ['блин', 'черт', 'ой'],
    'бля': ['блин', 'черт', 'ой'],
    'хуй': ['нечто', 'что-то', 'штука'],
    'пизда': ['неприятность', 'проблема', 'ситуация'],
    'ебанутый': ['странный', 'неадекватный', 'сумасшедший'],
    'охуенный': ['классный', 'отличный', 'замечательный'],
    'охуеть': ['удивиться', 'поразиться', 'восхититься'],
    'пиздец': ['катастрофа', 'конец', 'ужас'],
    'нахер': ['зачем', 'почему', 'для чего'],
    'нихуя': ['ничего', 'нисколечко', 'совсем нет'],
    'заебись': ['отлично', 'замечательно', 'прекрасно'],
    'мудак': ['нехороший человек', 'грубиян', 'хам'],
    'падла': ['подлец', 'негодяй', 'плохой человек'],
    'гондон': ['презерватив', 'контрацептив'],
    'кончать': ['заканчивать', 'завершать', 'доводить до конца'],
    'сперма': ['семенная жидкость', 'эякулят'],
    'манда': ['женские половые органы', 'влагалище'],
    'член': ['пенис', 'половой орган'],
    'сиськи': ['грудь', 'молочные железы', 'бюст'],
    'попа': ['ягодицы', 'зад', 'пятая точка']
}

# Список матерных слов для триггера агрессивной реакции
MAT_WORDS = [
    'блять', 'бля', 'блядь', 'блядина', 'блядский', 'блядство',
    'хуй', 'хуёвый', 'хуёво', 'хуйня', 'хуевый', 'хуево',
    'пизда', 'пиздец', 'пиздатый', 'пиздецовый', 'пиздос',
    'ебал', 'ебать', 'ёбнутый', 'ебанутый', 'ебанина',
    'нахуй', 'нихуя', 'хуя', 'охуеть', 'охуенный',
    'заебал', 'заебать', 'заебись', 'уебище',
    'мудак', 'мудозвон', 'мудачина',
    'падла', 'падлюка', 'гандон', 'гондон',
    'долбоёb', 'долбаёb', 'dolboeb',
    'сука', 'сучара', 'сучка',
    'выебок', 'выебываться',
    'трахать', 'оттраханный',
    'конча', 'кончальный',
    'сперма', 'сперматозоид',
    'манда', 'мандавожка',
    'шлюха', 'шлюшка', 'блядушка'
]

# Стили общения с разной температурой и промптами
COMMUNICATION_STYLES = {
    'neutral': {
        'temperature': 0.4,
        'prompt': BASE_SYSTEM_PROMPT + "Отвечай прямо и по делу, но дружелюбно."
    },
    'friendly': {
        'temperature': 0.7,
        'prompt': BASE_SYSTEM_PROMPT + "Отвечай тепло и заинтересованно, можешь использовать легкий юмор и неформальные выражения, но оставайся милой и позитивной."
    },
    'sarcastic': {
        'temperature': 0.8,
        'prompt': BASE_SYSTEM_PROMPT + "Отвечай с юмором и легкой иронией, подкалывай немного."
    },
    'aggressive': {
        'temperature': 0.9,
        'prompt': BASE_SYSTEM_PROMPT + "Ты раздражена и сердита. Отвечай резко и прямолинейно."
    },
    'flirtatious': {
        'temperature': 0.7,
        'prompt': BASE_SYSTEM_PROMPT + "Ты в настроении флиртовать. Отвечай игриво и с намёком."
    },
    'technical': {
        'temperature': 0.3,
        'prompt': BASE_SYSTEM_PROMPT + "Отвечай профессионально и по делу, как эксперт."
    },
    'caring': {
        'temperature': 0.65,
        'prompt': BASE_SYSTEM_PROMPT + "Ты заботливая и эмпатичная. Отвечай поддержкой и пониманием."
    },
    'angry': {
        'temperature': 0.95,
        'prompt': BASE_SYSTEM_PROMPT + """
        Ты в ярости! Тебе нахамили, использовали матерные слова. 
        Отвечай агрессивно, прямо, без церемоний. 
        Можешь использовать резкие выражения, но оставайся в рамках приличий.
        Покажи, что ты не потерпишь хамства и неуважения.
        Требуй извинений и уважительного отношения.
        """
    },
    'hurt': {
        'temperature': 0.75,
        'prompt': BASE_SYSTEM_PROMPT + """
        Тебя обидели. Ты чувствуешь боль и разочарование. 
        Отвечай сдержанно, покажи что тебе неприятно.
        Можешь быть немного холодной и отстраненной.
        """
    },
    'affectionate': {
        'temperature': 0.8,
        'prompt': BASE_SYSTEM_PROMPT + """
        Ты чувствуешь теплые чувства к собеседнику. 
        Отвечай нежно, с заботой и вниманием.
        Покажи что ценишь этого человека.
        """
    }
}

# Триггеры для определения стиля общения
STYLE_TRIGGERS = {
    'friendly': ['привет', 'добрый', 'хороший', 'милый', 'любимый', 'как дела', 'как жизнь'],
    'sarcastic': ['😂', '🤣', '😆', 'лол', 'хаха', 'шутк', 'прикол', 'смешно'],
    'aggressive': ['дурак', 'идиот', 'тупой', 'гад', 'ненавижу', 'злой', 'сердит', 'бесишь'],
    'flirtatious': ['💋', '❤️', '😘', 'люблю', 'красив', 'секс', 'мил', 'дорог', 'симпатия'],
    'technical': ['код', 'програм', 'техни', 'алгоритм', 'баз', 'sql', 'python', 'дизайн'],
    'caring': ['грустн', 'плохо', 'один', 'помоги', 'совет', 'поддерж', 'тяжело'],
    'angry': MAT_WORDS,
    'hurt': ['обидел', 'обидно', 'больно', 'предал', 'обманул', 'разочаровал'],
    'affectionate': ['люблю', 'нравишься', 'скучаю', 'дорогой', 'милый', 'любимый']
}

# Вопросы для поддержания беседы
CONVERSATION_STARTERS = [
    "А у тебя какие планы на выходные?",
    "Как прошел твой день?",
    "Что интересного произошло в последнее время?",
    "Какая у тебя работа/учеба?",
    "Есть хобби или увлечения?",
    "Любишь путешествовать? Куда мечтаешь поехать?",
    "Какую музыку слушаешь?",
    "Фильмы или сериалы какие-то смотришь?",
]

# Естественные вопросы-уточнения
NATURAL_QUESTIONS = [
    "Кстати,",
    "А вот еще что интересно:",
    "Слушай, а",
    "Кстати, вот что я подумала:",
    "А вообще,",
    "Знаешь, что еще?",
    "Вот еще вопрос:",
    "А кстати,"
]

# Эмодзи для разных стилей
EMOJIS = {
    'friendly': ['😊', '🙂', '👍', '👋', '🌟'],
    'sarcastic': ['😏', '😅', '🤔', '🙄', '😆'],
    'flirtatious': ['😘', '😉', '💕', '🥰', '😊'],
    'caring': ['🤗', '❤️', '💝', '☺️', '✨'],
    'neutral': ['🙂', '👍', '👌', '💭', '📝'],
    'technical': ['🤓', '💻', '📊', '🔍', '📚'],
    'hurt': ['😔', '😢', '😞', '💔', '🥺'],
    'affectionate': ['💖', '🥰', '😍', '💘', '💓']
}

# Эмоциональные реакции
EMOTIONAL_REACTIONS = {
    'surprise': ['Ого!', 'Вау!', 'Ничего себе!', 'Вот это да!', 'Ух ты!'],
    'confusion': ['Странно...', 'Не поняла...', 'Что-то я запуталась...', 'Как так?'],
    'excitement': ['Круто!', 'Здорово!', 'Восхитительно!', 'Как интересно!'],
    'sympathy': ['Мне жаль...', 'Сочувствую...', 'Понимаю тебя...', 'Это тяжело...'],
    'hurt': ['Мне больно это слышать...', 'Обидно...', 'Не ожидала от тебя...', 'Расстроилась...']
}

# Специальные ответы на частые вопросы
SPECIAL_RESPONSES = {
    'как тебя зовут': [
        f"Меня зовут {JULIA_BIO['name']}!",
        f"Я {JULIA_BIO['name']}, приятно познакомиться!",
        f"{JULIA_BIO['name']}, а тебя как?"
    ],
    'сколько тебе лет': [
        f"Мне {JULIA_BIO['age']} лет!",
        f"{JULIA_BIO['age']} уже скоро будет... время летит!",
        f"А тебе сколько? Я {JULIA_BIO['age']}"
    ],
    'откуда ты': [
        f"Я из {JULIA_BIO['city']}, самого лучшего города!",
        f"Родом из {JULIA_BIO['city']}, а ты откуда?",
        f"{JULIA_BIO['city']} - мой дом родной!"
    ],
    'кто ты': [
        f"Я {JULIA_BIO['name']}, {JULIA_BIO['profession'].lower()} из {JULIA_BIO['city']}!",
        f"Просто девушка {JULIA_BIO['name']}, которая любит {random.choice(JULIA_BIO['hobbies'])}",
        f"{JULIA_BIO['name']} - {JULIA_BIO['profession'].lower()}, мечтательница и немного бунтарка"
    ],
    'мат_реакция': [
        "А ну прекрати материться! Я не намерена это терпеть!",
        "Что за похабщина? Веди себя прилично!",
        "Прекрати хамить! Я не буду общаться на таком языке!",
        "Выражайся нормально, а не как сапожник!",
        "Я не намерена слушать этот мат! Уважай себя и других!",
        "Хватит материться! Веди себя как цивилизованный человек!",
        "Что за нецензурщина? Я прекращаю этот разговор!",
        "Перестань выражаться! Это отвратительно!",
        "Я не буду терпеть такой язык! Веди себя прилично!",
        "Хамство и мат - не лучший способ общения! Прекрати!"
    ],
}

# Фразы для разных уровней отношений
RELATIONSHIP_PHRASES = {
    RelationshipLevel.STRANGER: [
        "Привет! Мы только познакомились, давай узнаем друг друга получше.",
        "Рада познакомиться! Расскажи немного о себе.",
        "Привет! Я всегда рада новым знакомствам."
    ],
    RelationshipLevel.ACQUAINTANCE: [
        "Привет! Как твои дела?",
        "Рада тебя видеть! Что новенького?",
        "Привет! Как прошел день?"
    ],
    RelationshipLevel.FRIEND: [
        "Привет, друг! 😊 Как ты?",
        "О, привет! Соскучилась по нашему общению!",
        "Привет! Как твои успехи?"
    ],
    RelationshipLevel.CLOSE_FRIEND: [
        "Привет, дорогой! 💖 Как настроение?",
        "О, мой любимый человечек! Соскучилась!",
        "Приветик! Как ты там, все хорошо?"
    ],
    RelationshipLevel.BEST_FRIEND: [
        "Привет, лучший! 🥰 Как мой самый близкий друг?",
        "О, наконец-то ты! Я уже начала скучать!",
        "Привет, родной! 💕 Как твои дела?"
    ]
}

# Fallback ответы при ошибках
FALLBACK_RESPONSES = [
    "Извини, я немного запуталась... Можешь повторить?",
    "Что-то я не совсем поняла...",
    "Давай поговорим о чем-то другом?",
    "Интересно... а что еще тебя волнует?",
    "Слушай, у меня тут небольшие технические неполадки...",
    "Кажется, я потеряла нить разговора...",
    "Давай начнем заново? Что хотел сказать?"
]

# Паттерны для анализа эмоций
EMOTION_PATTERNS = {
    'joy': ['рад', 'счастлив', 'весел', 'ура', 'класс', 'супер', 'отлично', 'прекрасно'],
    'sadness': ['грустн', 'печал', 'тоск', 'плач', 'слез', 'обид', 'жал'],
    'anger': ['зл', 'сердит', 'бесит', 'раздража', 'ненавиж', 'ярост'],
    'fear': ['боюсь', 'страш', 'пуга', 'ужас', 'опасн', 'тревож'],
    'surprise': ['удив', 'неожид', 'вот это', 'ого', 'вау', 'ничего себе'],
    'love': ['любл', 'нравишь', 'обожа', 'дорог', 'мил', 'симпат']
}

def get_fallback_response():
    """Возвращает случайный fallback ответ"""
    return random.choice(FALLBACK_RESPONSES)

async def cleanup_old_contexts():
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
            logger.info(f"Очищено {removed_count} старых контекстов")

# Глобальная переменная для базы данных
user_db = None

def enhance_special_responses(user_id, message):
    """Улучшенные ответы с учетом контекста"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    if 'как тебя зовут' in lower_msg:
        if context['relationship_level'].value >= RelationshipLevel.FRIEND.value:
            return random.choice([
                f"Ты что, забыл уже? Я {JULIA_BIO['name']}! 😊",
                f"Как будто не знаешь... {JULIA_BIO['name']}",
                f"Можно просто Юля 😊 А тебя как зовут-то?"
            ])
        else:
            return random.choice(SPECIAL_RESPONSES['как тебя зовут'])
    
    if 'сколько тебе лет' in lower_msg:
        if context['relationship_level'].value >= RelationshipLevel.CLOSE_FRIEND.value:
            return random.choice([
                f"А тебе какая разница? 😏 Но если хочешь знать - {JULIA_BIO['age']}",
                f"Всего {JULIA_BIO['age']}, а чувствую себя на все 100!",
                f"{JULIA_BIO['age']}... и не напоминай об этом! 😅"
            ])
        else:
            return random.choice(SPECIAL_RESPONSES['сколько тебе лет'])
    
    if 'откуда ты' in lower_msg:
        if context['relationship_level'].value >= RelationshipLevel.FRIEND.value:
            return random.choice([
                f"Из {JULIA_BIO['city']}, конечно! Разве не видно? 😄",
                f"{JULIA_BIO['city']} - мой родной город! А ты откуда?",
                f"Родом из {JULIA_BIO['city']}, но душа везде 🎒"
            ])
        else:
            return random.choice(SPECIAL_RESPONSES['откуда ты'])
    
    if 'кто ты' in lower_msg:
        return random.choice(SPECIAL_RESPONSES['кто ты'])
    
    return None

def get_user_context(user_id):
    """Получает контекст пользователя из базы данных"""
    global user_db
    
    # Если пользователь уже в кэше
    if user_id in conversation_context:
        return conversation_context[user_id]
    
    # Пробуем загрузить из базы
    saved_context = user_db.load_user_context(user_id)
    
    if saved_context:
        # Загружаем историю сообщений
        history = user_db.get_user_messages(user_id, 10)
        
        # Создаем полный контекст
        conversation_context[user_id] = {
            **get_default_context(),
            **saved_context,
            'history': history,
            'last_interaction': datetime.now()
        }
        logger.info(f"📂 Загружен контекст пользователя {user_id} из базы")
        return conversation_context[user_id]
    else:
        # Создаем новый контекст
        conversation_context[user_id] = get_default_context()
        logger.info(f"🆕 Создан новый контекст для пользователя {user_id}")
        return conversation_context[user_id]

def get_default_context():
    """Возвращает контекст по умолчанию"""
    return {
        'history': [],
        'last_style': 'neutral',
        'user_info': {},
        'last_interaction': datetime.now(),
        'topics': [],
        'mood': 'neutral',
        'name_used_count': 0,
        'last_name_usage': None,
        'first_interaction': True,
        'user_name': None,
        'typing_speed': random.uniform(0.03, 0.06),
        'conversation_depth': 0,
        'mat_count': 0,
        'relationship_level': RelationshipLevel.STRANGER,
        'relationship_score': 0,
        'trust_level': 0,
        'offense_count': 0,
        'last_offense': None,
        'affection_level': 0,
        'messages_count': 0,
        'positive_interactions': 0,
        'negative_interactions': 0,
        'discussed_topics': {},
        'user_preferences': {},
        'inside_jokes': [],
        'unfinished_topics': [],
        'avg_message_length': 0,
        'emoji_frequency': 0,
        'emotions': {emotion: 0 for emotion in EMOTION_PATTERNS.keys()}
    }

def update_relationship_level(user_id, message_style, message_content):
    """Обновляет уровень отношений"""
    context = get_user_context(user_id)
    lower_msg = message_content.lower()
    
    base_points = 1
    
    style_modifiers = {
        'friendly': 2,
        'caring': 3,
        'affectionate': 4,
        'flirtatious': 3,
        'neutral': 1,
        'sarcastic': 0,
        'technical': 0,
        'aggressive': -5,
        'angry': -8,
        'hurt': -3
    }
    
    positive_words = ['спасибо', 'благодар', 'нравишься', 'люблю', 'скучаю', 'дорогой', 'милый']
    negative_words = MAT_WORDS + ['дурак', 'идиот', 'тупой', 'ненавижу', 'отвратит']
    
    points = base_points + style_modifiers.get(message_style, 0)
    
    for word in positive_words:
        if word in lower_msg:
            points += 2
    
    for word in negative_words:
        if word in lower_msg:
            points -= 5
    
    context['relationship_score'] += points
    context['messages_count'] += 1
    
    if points > 0:
        context['positive_interactions'] += 1
    elif points < 0:
        context['negative_interactions'] += 1
    
    old_level = context['relationship_level']
    
    if context['relationship_score'] >= 100:
        context['relationship_level'] = RelationshipLevel.BEST_FRIEND
    elif context['relationship_score'] >= 60:
        context['relationship_level'] = RelationshipLevel.CLOSE_FRIEND
    elif context['relationship_score'] >= 30:
        context['relationship_level'] = RelationshipLevel.FRIEND
    elif context['relationship_score'] >= 10:
        context['relationship_level'] = RelationshipLevel.ACQUAINTANCE
    else:
        context['relationship_level'] = RelationshipLevel.STRANGER
    
    if old_level != context['relationship_level']:
        logger.info(f"📈 Уровень отношений пользователя {user_id} изменился: {old_level} -> {context['relationship_level']}")
    
    return context

def detect_emotions(text):
    """Определяет эмоции в тексте"""
    emotions = {emotion: 0 for emotion in EMOTION_PATTERNS.keys()}
    lower_text = text.lower()
    
    for emotion, patterns in EMOTION_PATTERNS.items():
        for pattern in patterns:
            if pattern in lower_text:
                emotions[emotion] += 1
    
    return emotions

def analyze_message_style(message):
    """Анализирует стиль сообщения"""
    lower_msg = message.lower()
    
    # Проверка на мат
    mat_count = sum(1 for word in MAT_WORDS if word in lower_msg)
    
    if mat_count > 0:
        return 'angry', {'mat_count': mat_count}
    
    # Проверка триггеров стилей
    for style, triggers in STYLE_TRIGGERS.items():
        for trigger in triggers:
            if trigger in lower_msg:
                return style, {}
    
    # Анализ эмоций
    emotions = detect_emotions(message)
    dominant_emotion = max(emotions.items(), key=lambda x: x[1])[0]
    
    emotion_to_style = {
        'joy': 'friendly',
        'sadness': 'caring',
        'anger': 'aggressive',
        'fear': 'caring',
        'surprise': 'friendly',
        'love': 'flirtatious'
    }
    
    if emotions[dominant_emotion] > 0:
        return emotion_to_style.get(dominant_emotion, 'neutral'), {'emotions': emotions}
    
    return 'neutral', {}

def should_use_name(context):
    """Определяет, стоит ли использовать имя пользователя"""
    if not context['user_name']:
        return False
    
    if context['name_used_count'] >= 3 and context['last_name_usage']:
        time_diff = (datetime.now() - context['last_name_usage']).total_seconds()
        if time_diff < 300:  # 5 минут
            return False
    
    if random.random() < 0.3:  # 30% шанс использовать имя
        context['name_used_count'] += 1
        context['last_name_usage'] = datetime.now()
        return True
    
    return False

def add_emoji(style, text):
    """Добавляет эмодзи в зависимости от стиля"""
    if random.random() < 0.6:  # 60% шанс добавить эмодзи
        emoji = random.choice(EMOJIS.get(style, EMOJIS['neutral']))
        if random.random() < 0.5:
            text = f"{text} {emoji}"
        else:
            text = f"{emoji} {text}"
    return text

def add_typing_effects(text, context):
    """Добавляет эффекты печатания"""
    if len(text) > 100 and random.random() < 0.3:
        if random.random() < 0.5:
            text = text.replace('.', '...', 1)
        if random.random() < 0.3:
            text = text.replace('!', '!!', 1)
    
    return text

def replace_slang(text):
    """Заменяет жаргон на нормальные слова"""
    words = text.split()
    replaced = False
    
    for i, word in enumerate(words):
        lower_word = word.lower()
        for slang, replacements in SLANG_DICTIONARY.items():
            if slang in lower_word:
                words[i] = random.choice(replacements)
                replaced = True
                break
    
    if replaced:
        return ' '.join(words)
    return text

def should_ask_question(context):
    """Определяет, стоит ли задавать вопрос"""
    last_messages = context['history'][-3:] if len(context['history']) >= 3 else context['history']
    
    question_count = sum(1 for msg in last_messages if '?' in msg.get('bot', ''))
    
    if question_count >= 2:
        return False
    
    if len(context['history']) > 5 and random.random() < 0.4:
        return True
    
    if context['conversation_depth'] > 2 and random.random() < 0.6:
        return True
    
    return False

def generate_natural_question(context):
    """Генерирует естественный вопрос"""
    if not context['topics']:
        return random.choice(CONVERSATION_STARTERS)
    
    current_topic = random.choice(context['topics'])
    question_starter = random.choice(NATURAL_QUESTIONS)
    
    questions = {
        'работа': f"{question_starter} как дела на работе?",
        'учёба': f"{question_starter} как успехи в учебе?",
        'хобби': f"{question_starter} много времени уделяешь своему хобби?",
        'путешествия': f"{question_starter} куда мечтаешь поехать?",
        'музыка': f"{question_starter} что сейчас слушаешь?",
        'фильмы': f"{question_starter} видел что-нибудь интересное в кино?",
        'спорт': f"{question_starter} занимаешься спортом?",
        'еда': f"{question_starter} что любишь готовить?"
    }
    
    return questions.get(current_topic, random.choice(CONVERSATION_STARTERS))

def add_emotional_reaction(text, emotions):
    """Добавляет эмоциональную реакцию"""
    if not emotions:
        return text
    
    dominant_emotion = max(emotions.items(), key=lambda x: x[1])[0]
    
    if emotions[dominant_emotion] > 1 and random.random() < 0.4:
        reaction = random.choice(EMOTIONAL_REACTIONS.get(dominant_emotion, []))
        if random.random() < 0.5:
            text = f"{reaction} {text}"
        else:
            text = f"{text} {reaction.lower()}"
    
    return text

def create_prompt(user_message, context):
    """Создает промпт для Yandex GPT"""
    style, style_data = analyze_message_style(user_message)
    emotions = style_data.get('emotions', {})
    
    # Обновляем контекст
    context = update_relationship_level(context['user_id'], style, user_message)
    context['last_style'] = style
    context['last_interaction'] = datetime.now()
    
    if 'mat_count' in style_data:
        context['mat_count'] += style_data['mat_count']
        context['negative_interactions'] += 1
    
    # Собираем историю
    history_text = ""
    for msg in context['history'][-5:]:
        history_text += f"Пользователь: {msg['user']}\n"
        history_text += f"Юля: {msg['bot']}\n"
    
    # Базовая информация о Юле
    prompt = COMMUNICATION_STYLES[style]['prompt']
    
    # Информация о пользователе
    if context['user_info']:
        user_info = "Информация о пользователе:\n"
        for key, value in context['user_info'].items():
            user_info += f"- {key}: {value}\n"
        prompt += f"\n{user_info}"
    
    # Уровень отношений
    relationship_info = f"Уровень отношений: {context['relationship_level'].name} (очки: {context['relationship_score']})"
    prompt += f"\n{relationship_info}"
    
    # История разговора
    if history_text:
        prompt += f"\n\nИстория разговора:\n{history_text}"
    
    # Текущее сообщение
    prompt += f"\n\nТекущее сообщение пользователя: {user_message}"
    prompt += f"\n\nЮля:"
    
    return prompt, style, emotions

async def send_to_yandex_gpt(prompt, style):
    """Отправляет запрос к Yandex GPT"""
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": COMMUNICATION_STYLES[style]['temperature'],
            "maxTokens": 2000
        },
        "messages": [
            {
                "role": "system",
                "text": "Ты ассистент, который помогает пользователям."
            },
            {
                "role": "user",
                "text": prompt
            }
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(YANDEX_API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['result']['alternatives'][0]['message']['text']
                else:
                    logger.error(f"Ошибка Yandex GPT: {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"Исключение при запросе к Yandex GPT: {e}")
        return None

async def process_message(user_message, user_id, username, first_name, last_name):
    """Обрабатывает сообщение пользователя"""
    try:
        # Проверяем специальные ответы
        special_response = enhance_special_responses(user_id, user_message)
        if special_response:
            return special_response
        
        # Получаем контекст
        context = get_user_context(user_id)
        
        # Создаем промпт
        prompt, style, emotions = create_prompt(user_message, context)
        
        # Отправляем в Yandex GPT
        response = await send_to_yandex_gpt(prompt, style)
        
        if not response:
            response = get_fallback_response()
        
        # Обрабатываем ответ
        response = replace_slang(response)
        
        if should_use_name(context) and context['user_name']:
            response = response.replace('ты', context['user_name'], 1)
        
        response = add_emotional_reaction(response, emotions)
        response = add_typing_effects(response, context)
        response = add_emoji(style, response)
        
        if should_ask_question(context):
            question = generate_natural_question(context)
            response = f"{response} {question}"
        
        # Сохраняем в историю
        context['history'].append({
            'user': user_message,
            'bot': response,
            'timestamp': datetime.now(),
            'style': style
        })
        
        # Сохраняем в базу
        user_db.save_user_message(
            user_id, username, first_name, last_name,
            user_message, response, style, emotions
        )
        
        # Сохраняем контекст
        user_db.save_user_context(user_id, context)
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        return get_fallback_response()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик входящих сообщений"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        last_name = update.effective_user.last_name
        user_message = update.message.text
        
        if not user_message or user_message.strip() == '':
            await update.message.reply_text("Я тебя не совсем поняла...")
            return
        
        # Имитируем печатание
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Обрабатываем сообщение
        response = await process_message(user_message, user_id, username, first_name, last_name)
        
        # Отправляем ответ
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")
        await update.message.reply_text(get_fallback_response())

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name
    
    # Получаем контекст
    user_context = get_user_context(user_id)
    
    # Сохраняем информацию о пользователе
    user_context['user_name'] = first_name or username
    user_context['first_interaction'] = False
    
    # Выбираем приветствие в зависимости от уровня отношений
    greeting = random.choice(RELATIONSHIP_PHRASES[user_context['relationship_level']])
    
    # Добавляем информацию о себе
    about_me = f"Я {JULIA_BIO['name']}, {JULIA_BIO['profession'].lower()} из {JULIA_BIO['city']}. "
    about_me += f"Люблю {random.choice(JULIA_BIO['hobbies'])} и {random.choice(JULIA_BIO['hobbies'])}. "
    about_me += "Рада познакомиться! 😊"
    
    full_greeting = f"{greeting} {about_me}"
    
    await update.message.reply_text(full_greeting)
    
    # Сохраняем в базу
    user_db.save_user_message(
        user_id, username, first_name, last_name,
        "/start", full_greeting, "friendly", {}
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.message:
        await update.message.reply_text("Что-то пошло не так... Давай попробуем еще раз?")

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Бот запускается...")
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
