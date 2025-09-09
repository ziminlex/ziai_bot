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
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
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

Ты современная девушка, понимаешь молодежный слан и жаргон, но сама говоришь достаточно культурно.
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
            'negative_interactions': 0,
            'discussed_topics': {},
            'user_preferences': {},
            'inside_jokes': [],
            'unfinished_topics': [],
            'avg_message_length': 0,
            'emoji_frequency': 0
        }
    return conversation_context[user_id]

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
            points -= 3
    
    context['relationship_score'] += points
    context['messages_count'] += 1
    
    if points > 0:
        context['positive_interactions'] += 1
    elif points < 0:
        context['negative_interactions'] += 1
    
    if context['messages_count'] > 0:
        context['trust_level'] = (context['positive_interactions'] / context['messages_count']) * 100
    
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
    
    level_changed = update_relationship_level(user_id, style, user_message)
    
    extract_user_info(user_id, user_message)
    analyze_mood(user_id, user_message)
    
    if context['first_interaction']:
        context['first_interaction'] = False
    
    return level_changed

def analyze_user_communication_style(user_id, message):
    """Анализирует стиль общения пользователя"""
    context = get_user_context(user_id)
    
    avg_length = context.get('avg_message_length', 0)
    context['avg_message_length'] = (avg_length * 0.8) + (len(message) * 0.2)
    
    emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', message))
    context['emoji_frequency'] = context.get('emoji_frequency', 0) * 0.9 + emoji_count * 0.1
    
    if context['emoji_frequency'] > 1.5 and random.random() < 0.6:
        return True
    
    return False

def create_memory_reference(user_id, current_message):
    """Создает отсылки к предыдущим разговорам"""
    context = get_user_context(user_id)
    
    if len(context['history']) < 3:
        return None
    
    current_keywords = set(re.findall(r'\b([а-яА-ЯёЁ]{4,})\b', current_message.lower()))
    
    for i, past_msg in enumerate(context['history'][-10:]):
        if i < 2:
            continue
            
        past_keywords = set(re.findall(r'\b([а-яА-ЯёЁ]{4,})\b', past_msg['user'].lower()))
        common_keywords = current_keywords.intersection(past_keywords)
        
        if len(common_keywords) >= 2:
            days_ago = (datetime.now() - past_msg['timestamp']).days
            
            if days_ago == 0:
                time_ref = "сегодня"
            elif days_ago == 1:
                time_ref = "вчера"
            elif days_ago < 7:
                time_ref = f"{days_ago} дней назад"
            else:
                continue
            
            topic = random.choice(list(common_keywords))
            return f"Кстати, помнишь, {time_ref} ты говорил про {topic}..."
    
    return None

async def handle_uncertainty(update, user_id, message):
    """Обработка ситуаций, когда бот не уверен в ответе"""
    context = get_user_context(user_id)
    
    responses = [
        "Хм, дай подумать...",
        "Интересный вопрос...",
        "Так, сейчас соображу...",
        "Давай разберемся...",
        "Мне нужно секунду подумать об этом..."
    ]
    
    if random.random() < 0.4:
        await update.message.chat.send_message(random.choice(responses))
        await asyncio.sleep(random.uniform(1, 2))
    
    if random.random() < 0.3:
        clarifying_questions = [
            "Что именно тебя интересует?",
            "Можешь подробнее объяснить?",
            "Я не совсем поняла контекст...",
            "Это вопрос из какой области?"
        ]
        return random.choice(clarifying_questions)
    
    return None

def track_discussed_topics(user_id, message, response):
    """Отслеживает обсуждаемые темы"""
    context = get_user_context(user_id)
    
    topic_keywords = re.findall(r'\b([а-яА-ЯёЁ]{4,})\b', message + " " + response)
    for topic in topic_keywords[:3]:
        if len(topic) > 3 and topic.lower() not in ['этот', 'очень', 'который', 'когда']:
            if topic in context['discussed_topics']:
                context['discussed_topics'][topic]['count'] += 1
                context['discussed_topics'][topic]['last_discussed'] = datetime.now()
            else:
                context['discussed_topics'][topic] = {
                    'count': 1,
                    'first_discussed': datetime.now(),
                    'last_discussed': datetime.now(),
                    'sentiment': 0.5
                }

def get_conversation_depth(user_id):
    """Определяет глубину текущей темы"""
    context = get_user_context(user_id)
    if len(context['history']) < 2:
        return 0
    
    last_messages = [msg['user'] for msg in context['history'][-3:]] + [msg['bot'] for msg in context['history'][-3:]]
    all_text = " ".join(last_messages).lower()
    
    words = re.findall(r'\b[а-яё]{3,}\b', all_text)
    unique_ratio = len(set(words)) / len(words) if words else 1
    
    return max(0, min(5, int((1 - unique_ratio) * 5)))

def extract_user_info(user_id, message):
    """Извлекает информацию о пользователе"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    places = re.findall(r'(в|из|на)\s+([А-Яа-яЁёA-Za-z\s-]{3,})', message)
    for _, place in places:
        if len(place) > 2 and place.lower() not in ['меня', 'тебя', 'себя', 'гитаре']:
            if 'places' not in context['user_info']:
                context['user_info']['places'] = []
            if place not in context['user_info']['places']:
                context['user_info']['places'].append(place)
    
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
                interest.lower() not in ['ты', 'вы', 'мне', 'тебе', 'меня', 'тебя']):
                if 'interests' not in context['user_info']:
                    context['user_info']['interests'] = []
                if interest not in context['user_info']['interests']:
                    context['user_info']['interests'].append(interest)
    
    if not context['user_name']:
        name_patterns = [
            r'(меня|зовут)\s+([А-Я][а-яё]{2,15})',
            r'(я|это)\s+([А-Я][а-яё]{2,15})',
            r'^([А-Я][а-яё]{2,15})\s*$',
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, message)
            for _, name in matches:
                if len(name) > 2:
                    context['user_name'] = name
                    break

def analyze_mood(user_id, message):
    """Анализирует настроение пользователя"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    positive_words = ['хорошо', 'отлично', 'прекрасно', 'рад', 'счастлив', 'ура', 'класс', 'супер']
    negative_words = ['плохо', 'грустно', 'печально', 'устал', 'бесит', 'раздражает', 'ненавижу', 'обидно']
    neutral_words = ['нормально', 'обычно', 'так себе', 'ничего', 'окей']
    
    positive_count = sum(1 for word in positive_words if word in lower_msg)
    negative_count = sum(1 for word in negative_words if word in lower_msg)
    neutral_count = sum(1 for word in neutral_words if word in lower_msg)
    
    if positive_count > negative_count and positive_count > neutral_count:
        context['mood'] = 'positive'
    elif negative_count > positive_count and negative_count > neutral_count:
        context['mood'] = 'negative'
    elif neutral_count > 0:
        context['mood'] = 'neutral'

def detect_mat(message):
    """Обнаружение матерных слов с учетом контекста"""
    lower_msg = message.lower()
    
    mat_detected = any(mat_word in lower_msg for mat_word in MAT_WORDS)
    
    if mat_detected:
        quote_patterns = [
            r'"[^"]*' + '|'.join(MAT_WORDS) + r'[^"]*"',
            r'как\s+говорят',
            r'так\s+сказать',
            r'извините\s+за\s+выражение',
        ]
        
        is_quote = any(re.search(pattern, lower_msg) for pattern in quote_patterns)
        
        return not is_quote
    
    return False

def determine_communication_style(user_id, message):
    """Определяет стиль общения на основе сообщения"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    if detect_mat(message):
        context['mat_count'] += 1
        context['last_offense'] = datetime.now()
        
        if context['relationship_level'].value >= RelationshipLevel.CLOSE_FRIEND.value:
            return 'hurt'
        else:
            return 'angry'
    
    for style, triggers in STYLE_TRIGGERS.items():
        for trigger in triggers:
            if trigger in lower_msg:
                return style
    
    if context['mood'] == 'negative':
        return 'caring'
    elif context['mood'] == 'positive' and random.random() < 0.3:
        return 'friendly'
    
    if context['relationship_level'].value >= RelationshipLevel.CLOSE_FRIEND.value:
        if random.random() < 0.4:
            return 'affectionate'
    
    if random.random() < 0.2:
        return random.choice(['friendly', 'sarcastic', 'neutral'])
    
    return context['last_style']

def naturalize_response(response, style, user_id):
    """Делает ответ более естественным"""
    context = get_user_context(user_id)
    
    thinking_words = ['хм', 'ну', 'вообще', 'знаешь', 'кстати', 'в общем']
    if random.random() < 0.2 and len(response.split()) > 5:
        thinking_word = random.choice(thinking_words)
        response = f"{thinking_word.capitalize()}... {response.lower()}"
    
    if random.random() < 0.6 and style in EMOJIS:
        emoji = random.choice(EMOJIS[style])
        if random.random() < 0.7:
            response = f"{response} {emoji}"
        else:
            response = f"{emoji} {response}"
    
    if (context['user_name'] and 
        random.random() < 0.2 and
        context['name_used_count'] < 3 and
        (context['last_name_usage'] is None or 
         (datetime.now() - context['last_name_usage']).seconds > 120)):
        
        name_positions = [
            f"{context['user_name']}, {response.lower()}",
            f"{response} {context['user_name']}",
            f"Знаешь, {context['user_name']}, {response.lower()}"
        ]
        
        response = random.choice(name_positions)
        context['name_used_count'] += 1
        context['last_name_usage'] = datetime.now()
    
    return response

def should_add_question(user_id, current_response):
    """Определяет, стоит ли добавлять вопрос к ответу"""
    context = get_user_context(user_id)
    
    # Не добавляем вопросы если:
    if len(context['history']) < 2:
        return False
        
    if context['conversation_depth'] < 2:
        return False
        
    if context['mood'] == 'negative':
        return False
        
    if context['mat_count'] > 0:
        return False
        
    if '?' in current_response:
        return False
        
    # Проверяем, был ли недавно задан вопрос
    last_messages = context['history'][-3:]
    question_recently = any('?' in msg['bot'] for msg in last_messages)
    if question_recently:
        return False
        
    # Проверяем глубину текущей темы
    current_topic_depth = get_conversation_depth(user_id)
    if current_topic_depth < 2:
        return False
        
    # 30% вероятность добавить вопрос в подходящих условиях
    return random.random() < 0.3

def get_contextual_question(user_id, current_message):
    """Возвращает вопрос, уместный в текущем контексте"""
    context = get_user_context(user_id)
    lower_msg = current_message.lower()
    
    # Анализ текущего сообщения для контекстных вопросов
    if any(word in lower_msg for word in ['гитар', 'музык', 'играть']):
        return "какую музыку любишь играть на гитаре?"
    
    if any(word in lower_msg for word in ['путешеств', 'поездк', 'ездил']):
        return "куда мечтаешь поехать в следующее путешествие?"
    
    if any(word in lower_msg for word in ['видео игр', 'гейм', 'играю']):
        return "в какие игры сейчас играешь?"
    
    if any(word in lower_msg for word in ['работ', 'дел', 'проект']):
        return "как продвигаются твои дела на работе/учебе?"
    
    if any(word in lower_msg for word in ['хобби', 'увлечен', 'занимаюсь']):
        return "а есть что-то, что давно хотел попробовать?"
    
    # Общие вопросы, но более релевантные
    general_questions = [
        "что думаешь об этом?",
        "как тебе такая идея?",
        "а у тебя было что-то подобное?",
        "как бы ты поступил на моем месте?"
    ]
    
    return random.choice(general_questions)

def create_prompt(user_id, message, style):
    """Создает промпт для Yandex GPT"""
    context = get_user_context(user_id)
    style_config = COMMUNICATION_STYLES[style]
    
    prompt = style_config['prompt']
    
    relationship_modifier = get_relationship_modifier(user_id)
    prompt += f"\n{relationship_modifier}"
    
    if context['history']:
        prompt += "\n\nКонтекст предыдущего общения:\n"
        for i, msg in enumerate(context['history'][-3:]):
            prompt += f"Пользователь: {msg['user']}\n"
            prompt += f"Ты: {msg['bot']}\n"
    
    if context['user_info']:
        prompt += "\nИнформация о пользователе:\n"
        if 'interests' in context['user_info']:
            prompt += f"Интересы: {', '.join(context['user_info']['interests'][:3])}\n"
        if 'places' in context['user_info']:
            prompt += f"Упоминаемые места: {', '.join(context['user_info']['places'][:2])}\n"
        if context['user_name']:
            prompt += f"Имя пользователя: {context['user_name']}\n"
    
    prompt += f"\nТекущее настроение пользователя: {context['mood']}"
    prompt += f"\n\nТекущее сообщение пользователя: {message}"
    prompt += "\n\nТвой ответ (естественный, человеческий, соответствующий стилю):"
    
    return prompt

async def call_yandex_gpt(prompt, temperature=0.7):
    """Вызов Yandex GPT API"""
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": 1000
        },
        "messages": [
            {
                "role": "system",
                "text": "Ты - ассистент, который помогает общаться естественно и человечно."
            },
            {
                "role": "user",
                "text": prompt
            }
        ]
    }
    
    try:
        response = requests.post(YANDEX_API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        return result['result']['alternatives'][0]['message']['text']
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при вызове Yandex GPT: {e}")
        return None
    except (KeyError, IndexError) as e:
        logger.error(f"Ошибка парсинга ответа Yandex GPT: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка в Yandex GPT: {str(e)}")
        return None

async def process_message(update, context):
    """Обработка входящего сообщения"""
    user_id = update.message.from_user.id
    message = update.message.text
    
    if not message or message.strip() == "":
        return
    
    user_context = get_user_context(user_id)
    
    style = determine_communication_style(user_id, message)
    
    special_response = enhance_special_responses(user_id, message)
    if special_response:
        response = special_response
    else:
        prompt = create_prompt(user_id, message, style)
        
        temperature = COMMUNICATION_STYLES[style]['temperature']
        
        response = await call_yandex_gpt(prompt, temperature)
        
        if not response:
            response = get_fallback_response()
    
    response = naturalize_response(response, style, user_id)
    
    # Умное добавление вопросов только в подходящих случаях
    if should_add_question(user_id, response):
        question_starter = random.choice(NATURAL_QUESTIONS)
        follow_up_question = get_contextual_question(user_id, message)
        response = f"{response} {question_starter} {follow_up_question}"
    
    level_changed = update_conversation_context(user_id, message, response, style)
    
    if level_changed:
        relationship_phrase = random.choice(RELATIONSHIP_PHRASES[user_context['relationship_level']])
        response = f"{relationship_phrase} {response}"
    
    typing_delay = user_context.get('typing_speed', random.uniform(MIN_TYPING_DELAY, MAX_TYPING_DELAY))
    await asyncio.sleep(len(response) * typing_delay)
    
    await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user_id = update.message.from_user.id
    user_context = get_user_context(user_id)
    
    welcome_messages = [
        f"Привет! Я {JULIA_BIO['name']} 😊 Рада познакомиться!",
        f"Здравствуй! Я {JULIA_BIO['name']}, всегда рада новым знакомствам!",
        f"Приветствую! {JULIA_BIO['name']} готова к общению! 💫"
    ]
    
    await update.message.reply_text(random.choice(welcome_messages))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /help"""
    help_text = """
🤖 Я - Юля, твой виртуальный собеседник!

Я могу:
💬 Общаться на разные темы
🎨 Рассказывать о дизайне и искусстве
✈️ Делиться мыслями о путешествиях
😊 Поддерживать беседу естественно

Просто напиши мне что-нибудь, и я с радостью отвечу!
    """
    await update.message.reply_text(help_text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /reset"""
    user_id = update.message.from_user.id
    if user_id in conversation_context:
        del conversation_context[user_id]
    
    await update.message.reply_text("💫 Начинаем с чистого листа! Давай познакомимся заново!")

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

def main():
    """Основная функция"""
    if not all([TELEGRAM_BOT_TOKEN, YANDEX_API_KEY, YANDEX_FOLDER_ID]):
        logger.error("Не все переменные окружения установлены!")
        logger.error("Проверьте: TELEGRAM_BOT_TOKEN, YANDEX_API_KEY, YANDEX_FOLDER_ID")
        return
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    
    # Добавляем обработчики медиа
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # Добавляем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    
    # Запускаем фоновую задачу очистки
    asyncio.get_event_loop().create_task(cleanup_old_contexts())
    
    # Запускаем бота
    logger.info("🤖 Бот запущен! Ожидаю сообщения...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
