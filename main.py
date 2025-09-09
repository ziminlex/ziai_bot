import aiohttp
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
    
    # Уровень доверия основан на положительных взаимодействиях
    if context['messages_count'] > 0:
        context['trust_level'] = (context['positive_interactions'] / context['messages_count']) * 100
    
    # Определяем новый уровень отношений
    if context['relationship_score'] >= 100:
        new_level = RelationshipLevel.BEST_FRIEND
    elif context['relationship_score'] >= 60:
        new_level = RelationshipLevel.CLOSE_FRIEND
    elif context['relationship_score'] >= 30:
        new_level = RelationshipLevel.FRIEND
    elif context['relationship_score'] >= 10:
        new_level = RelationshipLevel.ACQUAINTANCE
    else:
        new_level = RelationshipLevel.STRANGER
    
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
        if len(place) > 2 and place.lower() not in ['меня', 'тебя', 'себя', 'гитаре']:
            if 'places' not in context['user_info']:
                context['user_info']['places'] = []
            if place not in context['user_info']['places']:
                context['user_info']['places'].append(place)
    
    # Извлечение интересов - улучшенная версия
    interest_patterns = [
        r'(люблю|нравится|увлекаюсь|занимаюсь|обожаю)\s+([а-яА-ЯёЁ\s]{3,20})',
        r'(хобби|увлечение|интерес)\s*[:-]?\s*([а-яА-ЯёЁ\s]{3,20})',
        r'(играю|занимаюсь)\s+на\s+([а-яА-ЯёЁ]{3,15})',
        r'(слушаю|люблю)\s+([а-яА-ЯёЁ]{3,15})\s+музыку',
    ]
    
    for pattern in interest_patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        for _, interest in matches:
            interest = interest.strip()
            if (len(interest) > 2 and 
                interest.lower() not in ['ты', 'вы', 'мне', 'тебе', 'меня'] and
                not any(word in interest.lower() for word in ['играю', 'люблю', 'нравится'])):
                
                if 'interests' not in context['user_info']:
                    context['user_info']['interests'] = []
                
                # Нормализуем интерес (убираем лишние слова)
                normalized_interest = re.sub(r'(на|в|за|под|к|по|с|со|у|о|об|от)$', '', interest.strip())
                if normalized_interest and normalized_interest not in context['user_info']['interests']:
                    context['user_info']['interests'].append(normalized_interest)
    
    # Также извлекаем существительные из сообщения как потенциальные интересы
    nouns = re.findall(r'\b([а-яА-ЯёЁ]{4,15})\b', message)
    for noun in nouns:
        if (noun.lower() not in ['гитаре', 'играю', 'люблю'] and
            len(noun) > 3 and random.random() < 0.3):
            
            if 'interests' not in context['user_info']:
                context['user_info']['interests'] = []
            
            if noun not in context['user_info']['interests']:
                context['user_info']['interests'].append(noun)

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
        
        # Проверяем и очищаем интересы
        if 'interests' in context['user_info'] and context['user_info']['interests']:
            valid_interests = []
            for interest in context['user_info']['interests']:
                # Фильтруем некорректные интересы (слишком длинные или содержащие глаголы)
                if (len(interest) <= 20 and 
                    not any(word in interest.lower() for word in ['играю', 'люблю', 'нравится', 'занимаюсь']) and
                    re.match(r'^[а-яА-ЯёЁa-zA-Z\s\-]+$', interest)):
                    valid_interests.append(interest)
            
            if valid_interests:
                interest = random.choice(valid_interests)
                question = f"{question_starter} как твои дела с {interest}?"
                return f"{response}\n\n{question}"
        
        # Проверяем и очищаем места
        if 'places' in context['user_info'] and context['user_info']['places']:
            valid_places = []
            for place in context['user_info']['places']:
                # Фильтруем некорректные места
                if (len(place) <= 25 and 
                    not any(word in place.lower() for word in ['играю', 'люблю', 'нравится']) and
                    re.match(r'^[а-яА-ЯёЁa-zA-Z\s\-]+$', place)):
                    valid_places.append(place)
            
            if valid_places:
                place = random.choice(valid_places)
                question = f"{question_starter} часто бываешь в {place}?"
                return f"{response}\n\n{question}"
        
        # Общий вопрос
        general_question = random.choice(CONVERSATION_STARTERS)
        return f"{response}\n\n{general_question}"
    
    return response

def add_emoji(response, style):
    """Добавляет эмодзи в зависимости от стиля"""
    if random.random() < 0.6:
        emoji = random.choice(EMOJIS.get(style, EMOJIS['neutral']))
        if random.random() < 0.5:
            return f"{response} {emoji}"
        else:
            return f"{emoji} {response}"
    return response

def detect_communication_style(message, user_id):
    """Определяет стиль общения на основе сообщения"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    # Проверяем на мат - приоритетный триггер для агрессивного стиля
    if any(mat_word in lower_msg for mat_word in MAT_WORDS):
        context['mat_count'] += 1
        return 'angry'
    
    # Проверяем другие триггеры
    for style, triggers in STYLE_TRIGGERS.items():
        if style == 'angry':
            continue  # Мат уже обработали
        
        for trigger in triggers:
            if trigger in lower_msg:
                return style
    
    # Учитываем историю отношений
    if context['relationship_level'] == RelationshipLevel.BEST_FRIEND:
        if random.random() < 0.4:
            return 'affectionate'
    
    # Учитываем настроение пользователя
    if context['mood'] == 'positive' and random.random() < 0.3:
        return 'friendly'
    elif context['mood'] == 'negative' and random.random() < 0.3:
        return 'caring'
    
    # Учитываем предыдущий стиль
    if context['last_style'] != 'neutral' and random.random() < 0.6:
        return context['last_style']
    
    return 'neutral'

def should_use_name(user_id):
    """Определяет, стоит ли использовать имя пользователя"""
    context = get_user_context(user_id)
    
    if not context['user_name']:
        return False
    
    # Проверяем, когда в последний раз использовали имя
    if context['last_name_usage']:
        time_since_last_use = (datetime.now() - context['last_name_usage']).total_seconds()
        if time_since_last_use < 300:  # 5 минут
            return False
    
    # Вероятность использования имени увеличивается с уровнем отношений
    probability = 0.1 + (context['relationship_level'].value * 0.15)
    
    if random.random() < probability:
        context['last_name_usage'] = datetime.now()
        context['name_used_count'] += 1
        return True
    
    return False

def personalize_response(response, user_id):
    """Персонализирует ответ с использованием информации о пользователе"""
    context = get_user_context(user_id)
    
    if should_use_name(user_id) and context['user_name']:
        name = context['user_name']
        if random.random() < 0.5:
            response = f"{name}, {response.lower()}"
        else:
            response = f"{response} {name}"
    
    return response

def get_cached_response(message, user_id):
    """Проверяет наличие закэшированного ответа"""
    cache_key = f"{user_id}_{message.lower()[:50]}"
    current_time = time.time()
    
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if current_time - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    return None

def cache_response(message, user_id, response):
    """Кэширует ответ"""
    cache_key = f"{user_id}_{message.lower()[:50]}"
    request_cache[cache_key] = {
        'response': response,
        'timestamp': time.time()
    }

async def call_yandex_gpt(message, user_id, style='neutral'):
    """Вызывает Yandex GPT API используя requests"""
    try:
        # Проверяем кэш
        cached_response = get_cached_response(message, user_id)
        if cached_response:
            return cached_response
        
        context = get_user_context(user_id)
        relationship_modifier = get_relationship_modifier(user_id)
        
        # Получаем настройки стиля
        style_settings = COMMUNICATION_STYLES[style]
        system_prompt = f"{style_settings['prompt']}\n\n{relationship_modifier}"
        
        # Добавляем историю беседы
        history_messages = []
        for msg in context['history'][-4:]:
            history_messages.append({"role": "user", "text": msg['user']})
            history_messages.append({"role": "assistant", "text": msg['bot']})
        
        # Формируем полный промпт
        full_prompt = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": style_settings['temperature'],
                "maxTokens": 1000
            },
            "messages": [
                {
                    "role": "system",
                    "text": system_prompt
                },
                *history_messages,
                {
                    "role": "user",
                    "text": message
                }
            ]
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "x-folder-id": YANDEX_FOLDER_ID
        }
        
        # Используем синхронный requests с run_in_executor для асинхронности
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(YANDEX_API_URL, json=full_prompt, headers=headers, timeout=10)
        )
        
        if response.status_code == 200:
            result = response.json()
            gpt_response = result['result']['alternatives'][0]['message']['text']
            
            # Кэшируем ответ
            cache_response(message, user_id, gpt_response)
            
            return gpt_response
        else:
            logger.error(f"Yandex GPT API error: {response.status_code} - {response.text}")
            return "Извини, у меня какие-то проблемы с подключением. Попробуй спросить позже."
    
    except requests.exceptions.Timeout:
        return "Ой, я слишком долго думала... Давай попробуем еще раз?"
    except requests.exceptions.ConnectionError:
        return "Похоже, проблемы с интернетом. Проверь соединение!"
    except Exception as e:
        logger.error(f"Error calling Yandex GPT: {e}")
        return "Ой, что-то пошло не так. Давай попробуем еще раз?"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие сообщения"""
    try:
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Извлекаем имя пользователя
        user_context = get_user_context(user_id)
        if not user_context['user_name']:
            user_context['user_name'] = update.effective_user.first_name
        
        # Обрабатываем жаргон
        processed_message = process_slang(user_message)
        
        # Определяем стиль общения
        style = detect_communication_style(processed_message, user_id)
        
        # Специальные ответы на частые вопросы
        lower_msg = processed_message.lower()
        for pattern, responses in SPECIAL_RESPONSES.items():
            if pattern in lower_msg:
                response = random.choice(responses)
                
                # Обновляем контекст
                update_conversation_context(user_id, user_message, response, style)
                
                # Симулируем печать и отправляем
                await simulate_human_typing(update.message.chat, response)
                return
        
        # Симулируем размышление
        thought = await simulate_thinking(update.message.chat)
        
        # Получаем ответ от GPT
        gpt_response = await call_yandex_gpt(processed_message, user_id, style)
        
        if not gpt_response:
            gpt_response = "Извини, я не совсем поняла. Можешь переформулировать?"
        
        # Добавляем человеческие элементы
        response = gpt_response
        response = add_human_errors(response)
        response = add_self_corrections(response)
        response = add_emotional_reaction(response, style)
        response = personalize_response(response, user_id)
        response = add_natural_question(response, user_id)
        response = add_emoji(response, style)
        
        # Обновляем контекст
        level_changed = update_conversation_context(user_id, user_message, response, style)
        
        # Если изменился уровень отношений, добавляем соответствующую фразу
        if level_changed:
            relationship_phrase = random.choice(RELATIONSHIP_PHRASES[user_context['relationship_level']])
            response = f"{relationship_phrase}\n\n{response}"
        
        # Симулируем печать и отправляем ответ
        await simulate_human_typing(update.message.chat, response)
        
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await update.message.reply_text("Ой, что-то пошло не так... Попробуй еще раз?")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ошибки"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.message:
        await update.message.reply_text(
            "Упс, что-то пошло не так... Давай попробуем еще раз?",
            reply_to_message_id=update.message.message_id
        )

def main():
    """Основная функция"""
    print("🤖 Бот Юля запускается...")
    
    try:
        # Проверяем наличие всех необходимых ключей
        required_env_vars = ['TELEGRAM_BOT_TOKEN', 'YANDEX_API_KEY', 'YANDEX_FOLDER_ID']
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_vars:
            print(f"❌ Отсутствуют переменные окружения: {', '.join(missing_vars)}")
            print("💡 Убедитесь, что вы установили все необходимые переменные:")
            print("   export TELEGRAM_BOT_TOKEN='ваш_токен'")
            print("   export YANDEX_API_KEY='ваш_ключ'")
            print("   export YANDEX_FOLDER_ID='ваш_id_каталога'")
            return
        
        # Создаем приложение
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        
        print("✅ Бот успешно запущен!")
        print("👋 Юля готова к общению!")
        print("🛑 Для остановки нажмите Ctrl+C")
        
        # Запускаем бота
        application.run_polling()
        
    except Conflict as e:
        print("❌ Конфликт: другой экземпляр бота уже запущен")
        print("💡 Остановите другие экземпляры бота перед запуском")
    except Exception as e:
        print(f"❌ Критическая ошибка при запуске: {e}")
        print("💡 Проверьте правильность токена и настроек")

if __name__ == "__main__":
    main()

