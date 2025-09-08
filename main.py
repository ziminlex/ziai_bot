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
MIN_TYPING_DELAY = 0.02
MAX_TYPING_DELAY = 0.08

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
    "birthday": "15 июля"
}

# Базовый системный промпт с информацией о Юле
BASE_SYSTEM_PROMPT = f"""
Ты - {JULIA_BIO['name']} ({JULIA_BIO['full_name']}), {JULIA_BIO['age']} лет, из {JULIA_BIO['city']}.
Ты {JULIA_BIO['profession']}. Образование: {JULIA_BIO['education']}.
У тебя есть {JULIA_BIO['pets']}. Ты {', '.join(JULIA_BIO['character_traits'][:2])}.
Любишь {', '.join(JULIA_BIO['hobbies'][:2])}. 

Ты современная девушка, понимаешь молодежный сленг и жаргон, но сама говоришь достаточно культурно.
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
        'prompt': BASE_SYSTEM_PROMPT + "Ты в ярости! Отвечай агрессивно и угрожающе."
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
    'angry': ['ненависть', 'убью', 'убить', 'ненавижу', 'терпеть', 'бесить', 'злость']
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

# Эмодзи для разных стилей
EMOJIS = {
    'friendly': ['😊', '🙂', '👍', '👋'],
    'sarcastic': ['😏', '😅', '🤔', '🙄'],
    'flirtatious': ['😘', '😉', '💕', '🥰'],
    'caring': ['🤗', '❤️', '💝', '☺️'],
    'neutral': ['🙂', '👍', '👌', '💭']
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
    'сру': [
        "Поняла тебя! Не задерживайся там слишком долго 😊",
        "Ясно, иди делай свои дела! Удачи в этом нелегком деле 😄",
        "Окей, поняла! Возвращайся поскорее 👍"
    ],
    'писать': [
        "Тогда беги быстрее! Не терпи 😊",
        "Понимаю, это дело не ждет! Удачи в уборной 🚽",
        "Срочно в туалет? Беги, не стесняйся! 😄"
    ],
    'туалет': [
        "Нужно в туалет? Иди, не стесняйся! 😊",
        "Поняла, туалетные дела важны! Удачи 🚽",
        "Беги быстрее, это дело не терпит! 👍"
    ],
    'по маленькому': [
        "А, понятно! Срочно в уборную? Беги 😊",
        "Маленькие дела тоже важны! Удачи 🚽",
        "Ясно, по маленькому! Не задерживайся там 👍"
    ],
    'по большому': [
        "Серьезные дела! Возьми с собой телефон почитать 😄",
        "По большому - это важно! Удачи в этом непростом деле 🚽",
        "Поняла! Не торопись, делай все качественно 😊"
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
            'typing_speed': random.uniform(0.03, 0.06)
        }
    return conversation_context[user_id]

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
    
    extract_user_info(user_id, user_message)
    analyze_mood(user_id, user_message)
    
    if context['first_interaction']:
        context['first_interaction'] = False

def extract_user_info(user_id, message):
    """Извлекает информацию о пользователе"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    places = re.findall(r'(в|из|на)\s+([А-Яа-яЁёA-Za-z\s-]{3,})', message)
    for _, place in places:
        if len(place) > 2 and place.lower() not in ['меня', 'тебя', 'себя']:
            if 'places' not in context['user_info']:
                context['user_info']['places'] = []
            if place not in context['user_info']['places']:
                context['user_info']['places'].append(place)
    
    interest_keywords = ['люблю', 'нравится', 'увлекаюсь', 'хobби', 'занимаюсь']
    for keyword in interest_keywords:
        if keyword in lower_msg:
            words = message.split()
            for i, word in enumerate(words):
                if word.lower() == keyword and i + 1 < len(words):
                    interest = words[i + 1]
                    if 'interests' not in context['user_info']:
                        context['user_info']['interests'] = []
                    if interest not in context['user_info']['interests']:
                        context['user_info']['interests'].append(interest)

def analyze_mood(user_id, message):
    """Анализирует настроение пользователя"""
    context = get_user_context(user_id)
    lower_msg = message.lower()
    
    positive_words = ['хорошо', 'отлично', 'рад', 'счастлив', 'люблю', 'нравится']
    negative_words = ['плохо', 'грустно', 'устал', 'бесит', 'ненавижу', 'злой']
    
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

def should_use_name(user_id, user_name, style):
    """Определяет, стоит ли использовать имя в ответе"""
    context = get_user_context(user_id)
    
    if context['first_interaction']:
        return True
    
    if style in ['aggressive', 'angry']:
        return False
    
    if style == 'neutral':
        return random.random() < 0.1
    
    if style in ['friendly', 'caring', 'flirtatious']:
        if context['last_name_usage']:
            time_since_last_use = datetime.now() - context['last_name_usage']
            if time_since_last_use < timedelta(minutes=5):
                return False
        return random.random() < 0.3
    
    return False

def format_response_with_name(response, user_name, style):
    """Форматирует ответ с именем"""
    context_patterns = {
        'friendly': [
            f"{user_name}, {response}",
            f"{response}, {user_name}",
            f"Знаешь, {user_name}, {response.lower()}"
        ],
        'caring': [
            f"{user_name}, {response}",
            f"{response}, {user_name}",
            f"Понимаю, {user_name}, {response.lower()}"
        ],
        'flirtatious': [
            f"{user_name}, {response}",
            f"Милый, {response.lower()}",
            f"Знаешь, {user_name}, {response.lower()}"
        ]
    }
    
    if style in context_patterns:
        return random.choice(context_patterns[style])
    
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

async def simulate_human_typing(chat, message):
    """Симулирует человеческую печать"""
    await chat.send_action(action="typing")
    
    typing_time = len(message) * random.uniform(MIN_TYPING_DELAY, MAX_TYPING_DELAY)
    typing_time = min(typing_time, 3.0)
    
    await asyncio.sleep(typing_time)
    
    await chat.send_message(message)

def generate_conversation_starter(user_id):
    """Генерирует вопрос для поддержания беседы"""
    context = get_user_context(user_id)
    
    if not context['history']:
        return random.choice(CONVERSATION_STARTERS)
    
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

def check_special_questions(message):
    """Проверяет специальные вопросы"""
    lower_msg = message.lower().strip()
    
    for question_pattern, responses in SPECIAL_RESPONSES.items():
        if question_pattern in lower_msg:
            return random.choice(responses)
    
    for slang_word in SLANG_DICTIONARY:
        if slang_word in lower_msg:
            if slang_word in ['сру', 'писать', 'по маленькому', 'по большому', 'ссать']:
                return random.choice([
                    "Поняла тебя! Не задерживайся там слишком долго 😊",
                    "Ясно, иди делай свои дела! Удачи 👍",
                    "Окей, поняла! Возвращайся поскорее 😄"
                ])
    
    return None

def build_context_prompt(user_id, user_message, style):
    """Строит промпт с учетом контекста"""
    context = get_user_context(user_id)
    base_prompt = COMMUNICATION_STYLES[style]['prompt']
    
    context_info = ""
    if context['history']:
        context_info += "\nПредыдущие сообщения:\n"
        for msg in context['history'][-3:]:
            context_info += f"Пользователь: {msg['user']}\nТы: {msg['bot']}\n"
    
    if 'user_info' in context and context['user_info']:
        context_info += "\nИнформация о пользователе:"
        for key, value in context['user_info'].items():
            if value:
                context_info += f"\n{key}: {', '.join(value[:3])}"
    
    context_info += f"\nТекущее настроение пользователя: {context['mood']}"
    
    if not context['first_interaction']:
        context_info += "\nИмя пользователя уже известно, используй его только когда уместно."
    
    return f"{base_prompt}{context_info}\n\nТекущее сообщение: {user_message}\n\nОтветь естественно."

def detect_communication_style(message: str) -> str:
    """Определяет стиль общения"""
    lower_message = message.lower()
    
    for style, triggers in STYLE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return style
    
    if any(word in lower_message for word in ['грустн', 'плохо', 'одинок']):
        return 'caring'
    if any(word in lower_message for word in ['злой', 'бесить', 'ненависть']):
        return 'angry'
    if '?' in message and len(message) < 20:
        return 'friendly'
    
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_id = user.id
    user_message = update.message.text
    
    base_name = extract_name_from_user(user)
    transformed_name = transform_name(base_name)
    
    user_context = get_user_context(user_id)
    user_context['user_name'] = transformed_name
    
    style = detect_communication_style(user_message)
    
    await update.message.chat.send_action(action="typing")
    
    try:
        await asyncio.sleep(0.5)
        
        ai_response = await call_yandex_gpt_optimized(user_id, user_message, style)
        
        use_name = should_use_name(user_id, transformed_name, style)
        
        if use_name:
            final_response = format_response_with_name(ai_response, transformed_name, style)
            user_context['name_used_count'] += 1
            user_context['last_name_usage'] = datetime.now()
        else:
            final_response = ai_response
        
        final_response = add_human_touch(final_response, style)
        
        if should_ask_question() and style not in ['aggressive', 'angry']:
            question = generate_conversation_starter(user_id)
            final_response += f"\n\n{question}"
        
        update_conversation_context(user_id, user_message, final_response, style)
        
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
• Сообщений: {len(context_data['history'])}
• Стиль: {context_data['last_style']}
• Настроение: {context_data['mood']}
• Имя использовано: {context_data['name_used_count']} раз
"""
    await update.message.reply_text(stats_text)

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
            filters.Regex(r'^(/about|/julia|/юля|/info)$'),
            about_command
        ))
        
        print(f"🤖 {JULIA_BIO['name']} запущена и готова к общению!")
        print(f"📍 Имя: {JULIA_BIO['name']}, {JULIA_BIO['age']} лет, {JULIA_BIO['city']}")
        print("📍 Бот теперь печатает как человек!")
        print("📍 Поддержка жаргона включена!")
        
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
    print("Запуск бота Юля...")
    main()
