import os
import logging
import requests
import json
import asyncio
import time
import re
import random
import signal
import sys
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import Conflict
from functools import lru_cache
from enum import Enum

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

Ты современная девушка, понимаешь молодежный сланг и жаргон, но сама говоришь достаточно культурно.
Можешь понять неформальные выражения и ответить на них адекватно, без ханжества, но и без пошлости.
Если тебе задают вопросы интимного характера - отвечай с юмором или тактично уходи от темы.

Отвечай как живой человек, естественно и непринужденно. Ты общаешься в Telegram-чате.
Используй имя собеседника только когда это уместно по контексту.
"""

# Словарь жаргонных слов и их нормальных аналогов
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
    'долбоёб', 'долбаёб', 'dolboeb',
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

def get_user_context(user_id):
    """Получает контекст пользователя"""
    if user_id not in conversation_context:
        conversation_context[user_id] = {
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
            'negative_interactions': 0
        }
    return conversation_context[user_id]

def update_relationship_level(user_id, message_style, message_content):
    """Обновляет уровень отношений"""
    context = get_user_context(user_id)
    lower_msg = message_content.lower()
    
    # Базовые очки за сообщение
    base_points = 1
    
    # Модификаторы в зависимости от стиля
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
    
    # Бонусы за позитивные слова
    positive_words = ['спасибо', 'благодар', 'нравишься', 'люблю', 'скучаю', 'дорогой', 'милый']
    negative_words = MAT_WORDS + ['дурак', 'идиот', 'тупой', 'ненавижу', 'отвратит']
    
    points = base_points + style_modifiers.get(message_style, 0)
    
    # Добавляем бонусы/штрафы за слова
    for word in positive_words:
        if word in lower_msg:
            points += 2
    
    for word in negative_words:
        if word in lower_msg:
            points -= 3
    
    # Обновляем счет
    context['relationship_score'] += points
    context['messages_count'] += 1
    
    if points > 0:
        context['positive_interactions'] += 1
    elif points < 0:
        context['negative_interactions'] += 1
    
    # Определяем уровень отношений
    score = context['relationship_score']
    
    if score >= 100:
        new_level = RelationshipLevel.BEST_FRIEND
        context['affection_level'] = min(100, context['affection_level'] + 3)
    elif score >= 60:
        new_level = RelationshipLevel.CLOSE_FRIEND
        context['affection_level'] = min(100, context['affection_level'] + 2)
    elif score >= 30:
        new_level = RelationshipLevel.FRIEND
        context['affection_level'] = min(100, context['affection_level'] + 1)
    elif score >= 10:
        new_level = RelationshipLevel.ACQUAINTANCE
    else:
        new_level = RelationshipLevel.STRANGER
    
    # Уровень доверия основан на положительных взаимодействиях
    if context['messages_count'] > 0:
        context['trust_level'] = (context['positive_interactions'] / context['messages_count']) * 100
    
    # Обновляем уровень отношений если изменился
    if new_level != context['relationship_level']:
        context['relationship_level'] = new_level
        return True
    
    return False

def get_relationship_modifier(user_id):
    """Возвращает модификатор для промпта based on уровня отношений"""
    context = get_user_context(user_id)
    level = context['relationship_level']
    
    modifiers = {
        RelationshipLevel.STRANGER: "Мы только что познакомились. Будь вежливой, но сдержанной.",
        RelationshipLevel.ACQUAINTANCE: "Мы знакомы немного. Можно быть немного более открытой.",
        RelationshipLevel.FRIEND: "Мы друзья. Можно общаться более непринужденно и доверительно.",
        RelationshipLevel.CLOSE_FRIEND: "Мы близкие друзья. Можно быть очень открытой и эмоциональной.",
        RelationshipLevel.BEST_FRIEND: "Мы лучшие друзья. Можно быть полностью собой, очень открытой и эмоциональной."
    }
    
    return modifiers[level]

def update_conversation_context(user_id, user_message, bot_response, style):
    """Обновляет контекст беседы"""
    context = get_user_context(user_id)
    
    context['history'].append({
        'user': user_message,
        'bot': bot_response,
        'style': style,
        'timestamp': datetime.now()
    })
    
    if len(context['history']) > 10:
        context['history'] = context['history'][-10:]
    
    context['last_style'] = style
    context['last_interaction'] = datetime.now()
    context['conversation_depth'] += 1
    
    # Обновляем уровень отношений
    level_changed = update_relationship_level(user_id, style, user_message)
    
    extract_user_info(user_id, user_message)
    analyze_mood(user_id, user_message)
    
    if context['first_interaction']:
        context['first_interaction'] = False
    
    return level_changed

def extract_user_info(user_id, message):
    """Извлекает информацию о пользователе"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    # Извлечение мест
    places = re.findall(r'(в|из|на)\s+([А-Яа-яЁёA-Za-z\s-]{3,})', message)
    for _, place in places:
        if len(place) > 2 and place.lower() not in ['меня', 'тебя', 'себя']:
            if 'places' not in context['user_info']:
                context['user_info']['places'] = []
            if place not in context['user_info']['places']:
                context['user_info']['places'].append(place)
    
    # Извлечение интересов
    interest_keywords = ['люблю', 'нравится', 'увлекаюсь', 'хобби', 'занимаюсь', 'любимый', 'любимая']
    for keyword in interest_keywords:
        if keyword in lower_msg:
            words = message.split()
            for i, word in enumerate(words):
                if word.lower() == keyword and i + 1 < len(words):
                    interest = words[i + 1]
                    if len(interest) > 2 and interest.lower() not in ['ты', 'вы', 'мне']:
                        if 'interests' not in context['user_info']:
                            context['user_info']['interests'] = []
                        if interest not in context['user_info']['interests']:
                            context['user_info']['interests'].append(interest)

def analyze_mood(user_id, message):
    """Анализирует настроение пользователя"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    positive_words = ['хорошо', 'отлично', 'рад', 'счастлив', 'люблю', 'нравится', 'прекрасно', 'замечательно']
    negative_words = ['плохо', 'грустно', 'устал', 'бесит', 'ненавижу', 'злой', 'сердит', 'отвратительно']
    
    positive_count = sum(1 for word in positive_words if word in lower_msg)
    negative_count = sum(1 for word in negative_words if word in lower_msg)
    
    if negative_count > positive_count:
        context['mood'] = 'negative'
    elif positive_count > negative_count:
        context['mood'] = 'positive'
    else:
        context['mood'] = 'neutral'

def process_slang(message):
    """Заменяет жаргонные слова на нормальные аналоги"""
    lower_msg = message.lower()
    processed_msg = message
    
    for slang_word, normal_words in SLANG_DICTIONARY.items():
        if slang_word in lower_msg:
            normal_word = random.choice(normal_words)
            processed_msg = re.sub(
                re.compile(slang_word, re.IGNORECASE), 
                normal_word, 
                processed_msg
            )
    
    return processed_msg

async def simulate_thinking(chat):
    """Симулирует процесс размышления (упрощенная версия)"""
    if random.random() < 0.2:
        await chat.send_action(action="typing")
        await asyncio.sleep(random.uniform(0.5, 1.5))
        return True
    return False

def add_self_corrections(response):
    """Добавляет самоисправления как у человека"""
    if random.random() < 0.15 and len(response) > 20:
        corrections = [
            " вернее,",
            " точнее,",
            " то есть,",
            " в смысле,",
            " точнее говоря,"
        ]
        words = response.split()
        if len(words) > 5:
            insert_pos = random.randint(2, len(words) - 3)
            words.insert(insert_pos, random.choice(corrections))
            return " ".join(words)
    return response

def add_emotional_reaction(response, style):
    """Добавляет эмоциональную реакцию"""
    if random.random() < 0.3:
        if style == 'friendly':
            reaction = random.choice(EMOTIONAL_REACTIONS['excitement'])
        elif style == 'caring':
            reaction = random.choice(EMOTIONAL_REACTIONS['sympathy'])
        elif style == 'hurt':
            reaction = random.choice(EMOTIONAL_REACTIONS['hurt'])
        else:
            reaction = random.choice(EMOTIONAL_REACTIONS['surprise'])
        
        return f"{reaction} {response}"
    return response

def add_human_errors(text):
    """Добавляет человеческие ошибки в текст"""
    if random.random() < 0.08:
        errors = [
            lambda t: t.replace(' что ', ' чо ').replace(' Что ', ' Чо '),
            lambda t: t.replace(' конечно ', ' конэчно '),
            lambda t: t.replace(' сейчас ', ' щас '),
            lambda t: t.replace(' чтобы ', ' чтоб '),
            lambda t: t + random.choice([' вроде', ' типа', ' как бы']),
            lambda t: t.replace(' тогда ', ' тода '),
            lambda t: t.replace(' его ', ' егоо ')[:-1],
            lambda t: t.replace(' меня ', ' мене '),
        ]
        text = random.choice(errors)(text)
    return text

async def simulate_human_typing(chat, message):
    """Улучшенная симуляция человеческой печати"""
    await chat.send_action(action="typing")
    
    typing_speed = random.uniform(MIN_TYPING_DELAY, MAX_TYPING_DELAY)
    total_time = len(message) * typing_speed
    total_time = min(total_time, 4.0)
    
    pause_probability = 0.2
    if random.random() < pause_probability:
        total_time += random.uniform(0.5, 1.5)
        await asyncio.sleep(total_time * 0.7)
        await chat.send_action(action="typing")
        await asyncio.sleep(total_time * 0.3)
    else:
        await asyncio.sleep(total_time)
    
    await chat.send_message(message)

def add_natural_question(response, user_id):
    """Добавляет естественный вопрос"""
    context = get_user_context(user_id)
    
    if random.random() < 0.25 and len(response) > 10:
        question_starter = random.choice(NATURAL_QUESTIONS)
        
        if 'interests' in context['user_info'] and context['user_info']['interests']:
            interest = random.choice(context['user_info']['interests'])
            question = f"{question_starter} как твои дела с {interest}?"
        elif 'places' in context['user_info'] and context['user_info']['places']:
            place = random.choice(context['user_info']['places'])
            question = f"{question_starter} часто бываешь в {place}?"
        else:
            question = f"{question_starter} {random.choice(CONVERSATION_STARTERS).lower()}"
        
        return f"{response}\n\n{question}"
    
    return response

def get_mood_based_response(response, user_id):
    """Корректирует ответ based on текущего настроения"""
    context = get_user_context(user_id)
    
    mood_modifiers = {
        'positive': [
            "Это же просто замечательно!",
            "Как здорово!",
            "Восхитительно!",
            "Я рада за тебя!"
        ],
        'negative': [
            "Мне жаль это слышать...",
            "Понимаю, как тебе тяжело...",
            "Сочувствую...",
            "Это действительно непросто..."
        ]
    }
    
    if context['mood'] in mood_modifiers and random.random() < 0.4:
        modifier = random.choice(mood_modifiers[context['mood']])
        return f"{modifier} {response}"
    
    return response

def add_natural_ending(response):
    """Добавляет естественное завершение фразы"""
    if random.random() < 0.2:
        endings = [
            " вот так вот.",
            " как-то так.",
            " примерно так.",
            " в общем.",
            " ну да.",
            " в принципе."
        ]
        response += random.choice(endings)
    return response

def add_human_touch(response, style):
    """Добавляет человеческие элементы в ответ"""
    if style in EMOJIS and random.random() < 0.6:
        emoji = random.choice(EMOJIS[style])
        response = f"{response} {emoji}"
    
    if random.random() < 0.2 and len(response.split()) > 5:
        prefixes = ['Кстати,', 'Вообще,', 'Знаешь,']
        response = f"{random.choice(prefixes)} {response.lower()}"
    
    return response

def generate_conversation_starter(user_id):
    """Генерирует вопрос для поддержания беседы"""
    context = get_user_context(user_id)
    
    if not context['history']:
        return random.choice(RELATIONSHIP_PHRASES[context['relationship_level']])
    
    if 'interests' in context['user_info'] and context['user_info']['interests']:
        interest = random.choice(context['user_info']['interests'])
        return f"Как твои успехи в {interest}?"
    
    if 'places' in context['user_info'] and context['user_info']['places']:
        place = random.choice(context['user_info']['places'])
        return f"Часто бываешь в {place}?"
    
    return random.choice(CONVERSATION_STARTERS)

def should_ask_question():
    """Определяет, стоит ли задавать вопрос"""
    return random.random() < 0.3

def check_repeated_mat(user_id, message):
    """Проверяет повторное использование мата"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    mat_count = 0
    for mat_word in MAT_WORDS:
        if mat_word in lower_msg:
            mat_count += 1
    
    if mat_count > 0:
        context['mat_count'] = context.get('mat_count', 0) + mat_count
        context['offense_count'] += 1
        context['last_offense'] = datetime.now()
        
        # Эскалация агрессии при повторном мате
        if context['mat_count'] >= 3:
            return "Я предупреждала! С тобой бесполезно разговаривать. Блокирую!"
        elif context['mat_count'] >= 2:
            return "Я же просила не материться! Последнее предупреждение!"
    
    return None

def check_special_questions(message):
    """Проверяет специальные вопросы"""
    lower_msg = message.lower().strip()
    
    # Проверка на матерные слова
    for mat_word in MAT_WORDS:
        if mat_word in lower_msg:
            return random.choice(SPECIAL_RESPONSES['мат_реакция'])
    
    # Проверка на специальные вопросы
    for question_pattern, responses in SPECIAL_RESPONSES.items():
        if (question_pattern in lower_msg and 
            question_pattern != 'мат_реакция'):
            return random.choice(responses)
    
    return None

def build_context_prompt(user_id, user_message, style):
    """Строит промпт с учетом контекста"""
    context = get_user_context(user_id)
    base_prompt = COMMUNICATION_STYLES[style]['prompt']
    relationship_modifier = get_relationship_modifier(user_id)
    
    context_info = f"{relationship_modifier}\n\n"
    
    if context['history']:
        context_info += "Предыдущие сообщения:\n"
        for msg in context['history'][-3:]:
            context_info += f"Пользователь: {msg['user']}\nТы: {msg['bot']}\n"
    
    if 'user_info' in context and context['user_info']:
        context_info += "\nИнформация о пользователе:"
        for key, value in context['user_info'].items():
            if value:
                context_info += f"\n{key}: {', '.join(value[:3])}"
    
    context_info += f"\nТекущее настроение пользователя: {context['mood']}"
    context_info += f"\nУровень отношений: {context['relationship_level'].name}"
    context_info += f"\nУровень доверия: {context['trust_level']:.1f}%"
    
    if context['offense_count'] > 0:
        context_info += f"\nПользователь обижал тебя {context['offense_count']} раз"
    
    if not context['first_interaction']:
        context_info += "\nИмя пользователя уже известно, используй его только когда уместно."
    
    return f"{base_prompt}{context_info}\n\nТекущее сообщение: {user_message}\n\nОтветь естественно."

def detect_communication_style(message: str) -> str:
    """Определяет стиль общения"""
    lower_message = message.lower()
    
    # Проверка на матерные слова - приоритет最高
    for mat_word in MAT_WORDS:
        if mat_word in lower_message:
            return 'angry'
    
    for style, triggers in STYLE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return style
    
    if any(word in lower_message for word in ['грустн', 'плохо', 'одинок']):
        return 'caring'
    
    return 'neutral'

@lru_cache(maxsize=100)
def generate_prompt_template(style: str = 'neutral') -> str:
    """Генерирует промпт для выбранного стиля"""
    return COMMUNICATION_STYLES[style]['prompt']

async def call_yandex_gpt_optimized(user_id: int, user_message: str, style: str = 'neutral') -> str:
    """Оптимизированный вызов API"""
    
    processed_message = process_slang(user_message)
    
    special_response = check_special_questions(processed_message)
    if special_response:
        return special_response
    
    cache_key = f"{user_id}_{processed_message[:50]}_{style}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    temperature = COMMUNICATION_STYLES[style]['temperature']
    full_prompt = build_context_prompt(user_id, processed_message, style)
    
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": 400,
        },
        "messages": [
            {
                "role": "system", 
                "text": full_prompt
            },
            {
                "role": "user",
                "text": processed_message[:500]
            }
        ]
    }
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=10)
        )
        
        response.raise_for_status()
        result = response.json()
        
        ai_response = result['result']['alternatives'][0]['message']['text']
        
        request_cache[cache_key] = {
            'response': ai_response,
            'timestamp': time.time()
        }
        
        if len(request_cache) > 400:
            oldest_key = min(request_cache.keys(), key=lambda k: request_cache[k]['timestamp'])
            del request_cache[oldest_key]
        
        return ai_response
        
    except requests.exceptions.Timeout:
        return "Ой, я задумалась... Что-то сложное ты спросил!"
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return "Что-то я сегодня не в форме... Давай попозже поговорим?"

def should_process_message(user_message: str) -> bool:
    """Фильтр сообщений"""
    message = user_message.strip()
    return len(message) > 1 and not message.startswith('/')

def extract_name_from_user(user):
    """Извлекает имя пользователя"""
    name = user.first_name or ""
    
    if not name and user.last_name:
        name = user.last_name
    elif not name and user.username:
        name = user.username
        if name.startswith('@'):
            name = name[1:]
    
    name = name.split()[0] if name else "Незнакомец"
    name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', name)
    
    return name if name else "Аноним"

@lru_cache(maxsize=200)
def transform_name(base_name: str) -> str:
    """Преобразует имя"""
    if not base_name or base_name.lower() in ['незнакомец', 'аноним']:
        return random.choice(['Незнакомец', 'Аноним', 'Ты'])
    
    return base_name.capitalize()

def should_use_name(user_id, user_name, style):
    """Определяет, стоит ли использовать имя в ответе"""
    context = get_user_context(user_id)
    
    if context['first_interaction']:
        return True
    
    if style in ['aggressive', 'angry', 'hurt']:
        return False
    
    # Чаще использовать имя для близких отношений
    relationship_factor = {
        RelationshipLevel.STRANGER: 0.1,
        RelationshipLevel.ACQUAINTANCE: 0.2,
        RelationshipLevel.FRIEND: 0.4,
        RelationshipLevel.CLOSE_FRIEND: 0.6,
        RelationshipLevel.BEST_FRIEND: 0.8
    }
    
    probability = relationship_factor[context['relationship_level']]
    
    if context['last_name_usage']:
        time_since_last_use = datetime.now() - context['last_name_usage']
        if time_since_last_use < timedelta(minutes=2):
            probability *= 0.5
    
    return random.random() < probability

def format_response_with_name(response, user_name, style, relationship_level):
    """Форматирует ответ с именем"""
    patterns = {
        RelationshipLevel.STRANGER: [
            f"{response}",
            f"{user_name}, {response}",
        ],
        RelationshipLevel.ACQUAINTANCE: [
            f"{user_name}, {response}",
            f"{response}, {user_name}",
        ],
        RelationshipLevel.FRIEND: [
            f"{user_name}, {response}",
            f"{response}, {user_name}",
            f"Знаешь, {user_name}, {response.lower()}"
        ],
        RelationshipLevel.CLOSE_FRIEND: [
            f"{user_name}, {response}",
            f"Дорогой, {response.lower()}",
            f"Знаешь, {user_name}, {response.lower()}"
        ],
        RelationshipLevel.BEST_FRIEND: [
            f"{user_name}, {response}",
            f"Родной, {response.lower()}",
            f"Лучший, {response.lower()}",
            f"Знаешь, {user_name}, {response.lower()}"
        ]
    }
    
    return random.choice(patterns[relationship_level])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенный обработчик сообщений"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_id = user.id
    user_message = update.message.text
    
    # Проверка на повторный мат
    repeated_mat_response = check_repeated_mat(user_id, user_message)
    if repeated_mat_response:
        await update.message.reply_text(repeated_mat_response)
        return
    
    base_name = extract_name_from_user(user)
    transformed_name = transform_name(base_name)
    
    user_context = get_user_context(user_id)
    user_context['user_name'] = transformed_name
    
    style = detect_communication_style(user_message)
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Для агрессивного стиля уменьшаем задержку
        if style == 'angry':
            await asyncio.sleep(random.uniform(0.1, 0.5))
        else:
            await asyncio.sleep(random.uniform(0.3, 1.2))
        
        if style != 'angry' and await simulate_thinking(update.message.chat):
            await asyncio.sleep(random.uniform(0.5, 1.0))
        
        ai_response = await call_yandex_gpt_optimized(user_id, user_message, style)
        
        use_name = should_use_name(user_id, transformed_name, style)
        
        if use_name:
            final_response = format_response_with_name(ai_response, transformed_name, style, user_context['relationship_level'])
            user_context['name_used_count'] += 1
            user_context['last_name_usage'] = datetime.now()
        else:
            final_response = ai_response
        
        # Обновляем контекст и проверяем изменение уровня отношений
        level_changed = update_conversation_context(user_id, user_message, final_response, style)
        
        # Если уровень отношений изменился, добавляем соответствующую фразу
        if level_changed:
            level_phrase = random.choice(RELATIONSHIP_PHRASES[user_context['relationship_level']])
            final_response = f"{level_phrase}\n\n{final_response}"
        
        # Для агрессивного стиля меньше человеческих украшений
        if style != 'angry':
            final_response = add_human_touch(final_response, style)
            final_response = add_emotional_reaction(final_response, style)
            final_response = add_self_corrections(final_response)
            final_response = add_human_errors(final_response)
            final_response = get_mood_based_response(final_response, user_id)
            final_response = add_natural_question(final_response, user_id)
            final_response = add_natural_ending(final_response)
        else:
            # Для агрессивного стиля добавляем восклицания
            final_response = final_response.replace('.', '!').replace('?', '!')
        
        if should_ask_question() and style not in ['aggressive', 'angry', 'hurt']:
            question = generate_conversation_starter(user_id)
            final_response += f"\n\n{question}"
        
        await simulate_human_typing(update.message.chat, final_response)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Ой, что-то пошло не так... Давай начнем заново?")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для информации о Юле"""
    about_text = f"""
👋 Привет! Я {JULIA_BIO['name']} ({JULIA_BIO['full_name']}), {JULIA_BIO['age']} лет из {JULIA_BIO['city']}

🎨 Профессия: {JULIA_BIO['profession']}
🎓 Образование: {JULIA_BIO['education']}
❤️ Увлечения: {', '.join(JULIA_BIO['hobbies'])}
🐾 Домашние животные: {JULIA_BIO['pets']}
🎵 Любимая музыка: {JULIA_BIO['favorite_music']}
🍕 Любимая еда: {JULIA_BIO['favorite_food']}

{random.choice(['Давай знакомиться!', 'Расскажи о себе!'])}
"""
    await update.message.reply_text(about_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра статистики"""
    user_id = update.message.from_user.id
    context_data = get_user_context(user_id)
    
    stats_text = f"""
📊 Статистика нашей беседы:
• Сообщений: {context_data['messages_count']}
• Уровень отношений: {context_data['relationship_level'].name}
• Счет отношений: {context_data['relationship_score']}
• Уровень доверия: {context_data['trust_level']:.1f}%
• Уровень привязанности: {context_data['affection_level']}
• Положительных взаимодействий: {context_data['positive_interactions']}
• Отрицательных взаимодействий: {context_data['negative_interactions']}
• Обид: {context_data['offense_count']}
• Стиль: {context_data['last_style']}
• Настроение: {context_data['mood']}
"""
    await update.message.reply_text(stats_text)

async def reset_mat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс счетчика матерных слов"""
    user_id = update.message.from_user.id
    user_context = get_user_context(user_id)
    
    if 'mat_count' in user_context:
        user_context['mat_count'] = 0
        user_context['offense_count'] = 0
        await update.message.reply_text("Счетчик матерных слов и обид сброшен. Давай общаться культурно!")
    else:
        await update.message.reply_text("У тебя и так чистая история общения! 👍")

async def relationship_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра уровня отношений"""
    user_id = update.message.from_user.id
    context_data = get_user_context(user_id)
    
    level_descriptions = {
        RelationshipLevel.STRANGER: "Мы только познакомились",
        RelationshipLevel.ACQUAINTANCE: "Мы знакомы",
        RelationshipLevel.FRIEND: "Мы друзья",
        RelationshipLevel.CLOSE_FRIEND: "Мы близкие друзья",
        RelationshipLevel.BEST_FRIEND: "Мы лучшие друзья!"
    }
    
    relation_text = f"""
💞 Уровень наших отношений: {context_data['relationship_level'].name}
{level_descriptions[context_data['relationship_level']]}

📈 Прогресс: {context_data['relationship_score']} очков
🤝 Доверие: {context_data['trust_level']:.1f}%
❤️ Привязанность: {context_data['affection_level']}

Положительных взаимодействий: {context_data['positive_interactions']}
Отрицательных: {context_data['negative_interactions']}
"""
    await update.message.reply_text(relation_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if "Conflict" in str(context.error):
        logger.warning("Обнаружен конфликт - вероятно, запущен другой экземпляр бота")
        return
    
    try:
        if update and update.message:
            await update.message.reply_text("Извини, что-то пошло не так... Попробуй еще раз!")
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        application.add_error_handler(error_handler)
        
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^/stats$'),
            stats_command
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^/reset_mat$'),
            reset_mat_command
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^(/about|/julia|/юля|/info)$'),
            about_command
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^(/relationship|/отношения|/уровень)$'),
            relationship_command
        ))
        
        print(f"🤖 {JULIA_BIO['name']} запущена и готова к общению!")
        print(f"📍 Имя: {JULIA_BIO['name']}, {JULIA_BIO['age']} лет, {JULIA_BIO['city']}")
        print("📍 Система уровней отношений: Незнакомец → Знакомый → Друг → Близкий друг → Лучший друг")
        print("📍 Реалистичная модель эмоций: обида, привязанность, доверие")
        print("📍 Динамическое изменение поведения based on уровня отношений")
        print("📍 Убраны фразы для размышления - более естественное общение")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Conflict as e:
        print("⚠️  Ошибка: Уже запущен другой экземпляр бота!")
        print("Остановите другие экземпляры командой: pkill -f python")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        print(f"Ошибка запуска: {e}")

if __name__ == "__main__":
    print("Запуск бота Юля с системой отношений...")
    main()
