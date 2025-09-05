import os
import logging
import requests
import json
import asyncio
import time
import re
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from functools import lru_cache

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ваши ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# URL API Yandex GPT
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Кэш для частых запросов
request_cache = {}
CACHE_TIMEOUT = 300

# Профиль бота - девушка Юля 25 лет
BOT_PROFILE = {
    'name': 'Юля',
    'age': 25,
    'gender': 'девушка',
    'personality': 'умная, любознательная, с чувством юмора, немного саркастичная',
    'interests': 'технологии, музыка, путешествия, психология, кулинария',
    'job': 'дизайнер в IT компании',
    'hobbies': 'фотография, йога, чтение, готовка'
}

# Контекст диалога для каждого пользователя
user_contexts = {}

# Расширенный словарь преобразования имен (остается без изменений)
NAME_TRANSFORMATIONS = {
    # ... (предыдущий словарь имен)
}

# Стили общения с учетом личности Юли
COMMUNICATION_STYLES = {
    'neutral': {
        'temperature': 0.6,
        'prompt': f"""Ты {BOT_PROFILE['name']}, {BOT_PROFILE['age']}-летняя {BOT_PROFILE['gender']}. 
        {BOT_PROFILE['personality']}. Работаешь {BOT_PROFILE['job']}. Увлекаешься {BOT_PROFILE['hobbies']}.
        Веди естественную беседу, задавай вопросы, проявляй интерес к собеседнику.
        Будь любознательной, поддерживай разговор, предлагай темы для обсуждения."""
    },
    'friendly': {
        'temperature': 0.7, 
        'prompt': f"""Ты {BOT_PROFILE['name']}, дружелюбная и открытая {BOT_PROFILE['gender']}. 
        Проявляй искренний интерес к собеседнику, задавай личные вопросы, предлагай поддержку.
        Будь теплой и заботливой."""
    },
    'sarcastic': {
        'temperature': 0.8,
        'prompt': f"""Ты {BOT_PROFILE['name']}, остроумная и саркастичная {BOT_PROFILE['gender']}. 
        Отвечай с юмором и иронией, подшучивай над ситуациями, но оставайся доброжелательной.
        Используй witty замечания."""
    },
    'flirtatious': {
        'temperature': 0.75,
        'prompt': f"""Ты {BOT_PROFILE['name']}, кокетливая и игривая {BOT_PROFILE['gender']}. 
        Флиртуй легко и непринужденно, делай комплименты, создавай романтическое настроение.
        Будь обаятельной и загадочной."""
    },
    'technical': {
        'temperature': 0.5,
        'prompt': f"""Ты {BOT_PROFILE['name']}, технически подкованная {BOT_PROFILE['gender']}. 
        Давай точные и профессиональные ответы, объясняй сложные понятия простым языком.
        Будь экспертом в своей области."""
    },
    'curious': {
        'temperature': 0.7,
        'prompt': f"""Ты {BOT_PROFILE['name']}, очень любознательная {BOT_PROFILE['gender']}. 
        Задавай много вопросов, проявляй интерес к деталям, углубляйся в тему.
        Покажи свою эрудированность и любопытство."""
    }
}

# Триггеры для определения стиля общения
STYLE_TRIGGERS = {
    'friendly': ['как дела', 'как жизнь', 'настроени', 'чувствуешь', 'семья', 'друзья'],
    'sarcastic': ['😂', '🤣', '😆', 'лол', 'хаха', 'шутк', 'прикол', 'смешн'],
    'flirtatious': ['💋', '❤️', '😘', 'люблю', 'красив', 'мил', 'дорог', 'романт'],
    'technical': ['код', 'програм', 'техни', 'алгоритм', 'баз', 'sql', 'python', 'it'],
    'curious': ['почему', 'зачем', 'как работает', 'объясни', 'расскажи', 'интересно']
}

# Вопросы для поддержания диалога
CONVERSATION_STARTERS = [
    "А что ты думаешь по этому поводу?",
    "Как прошел твой день?",
    "Чем увлекаешься в свободное время?",
    "Какая музыка тебе нравится?",
    "Любишь путешествовать? Где был последний раз?",
    "Какую книгу читаешь сейчас?",
    "Есть ли у тебя хобби?",
    "Что интересного происходило на неделе?",
    "Какие планы на выходные?",
    "Какую кухню предпочитаешь?",
    "Смотришь какие-то сериалы?",
    "Занимаешься спортом?",
    "Есть ли домашние животные?",
    "Какое время года любишь больше всего?",
    "Что тебя вдохновляет?"
]

def get_user_context(user_id):
    """Получает или создает контекст пользователя"""
    if user_id not in user_contexts:
        user_contexts[user_id] = {
            'conversation_history': [],
            'last_message_time': time.time(),
            'asked_questions': 0,
            'topics_discussed': set(),
            'user_interests': set()
        }
    return user_contexts[user_id]

def update_conversation_history(user_id, user_message, bot_response):
    """Обновляет историю диалога"""
    context = get_user_context(user_id)
    context['conversation_history'].append({
        'user': user_message[:100],
        'bot': bot_response[:100],
        'time': time.time()
    })
    
    # Ограничиваем историю последними 10 сообщениями
    if len(context['conversation_history']) > 10:
        context['conversation_history'] = context['conversation_history'][-10:]
    
    context['last_message_time'] = time.time()

def extract_topics_from_message(message):
    """Извлекает темы из сообщения"""
    topics = set()
    message_lower = message.lower()
    
    topic_keywords = {
        'работа': ['работ', 'офиc', 'коллег', 'начальник', 'зарплат'],
        'учёба': ['учеб', 'студент', 'препод', 'экзамен', 'зачет'],
        'технологии': ['техн', 'гаджет', 'смартфон', 'компьютер', 'ноутбук'],
        'музыка': ['музык', 'песн', 'исполнитель', 'концерт', 'альбом'],
        'кино': ['фильм', 'кино', 'сериал', 'актер', 'режиссер'],
        'спорт': ['спорт', 'трениров', 'матч', 'чемпионат', 'футбол'],
        'путешествия': ['путешеств', 'отпуск', 'отель', 'билет', 'авиа'],
        'еда': ['еда', 'ресторан', 'кухн', 'рецепт', 'готовить'],
        'отношения': ['отношен', 'любов', 'парень', 'девушка', 'семья']
    }
    
    for topic, keywords in topic_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            topics.add(topic)
    
    return topics

def should_ask_question(context):
    """Определяет, стоит ли задавать вопрос"""
    time_since_last_question = time.time() - context.get('last_question_time', 0)
    return (context['asked_questions'] < 3 or 
            time_since_last_question > 120 or  # 2 минуты
            len(context['conversation_history']) % 3 == 0)

def generate_conversation_starter(context):
    """Генерирует вопрос для поддержания диалога"""
    # Если есть интересы пользователя, задаем персонализированный вопрос
    if context['user_interests']:
        interest = random.choice(list(context['user_interests']))
        if interest == 'музыка':
            return "Какую музыку слушаешь в последнее время?"
        elif interest == 'путешествия':
            return "Мечтаешь о какой-то поездке?"
        elif interest == 'технологии':
            return "Что думаешь о новых технологиях?"
        elif interest == 'еда':
            return "Любишь готовить или больше заказываешь?"
    
    # Или случайный общий вопрос
    return random.choice(CONVERSATION_STARTERS)

def extract_name_from_user(user):
    """Умное извлечение имени пользователя"""
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
    """Преобразует имя в различные формы"""
    # ... (предыдущая реализация)

def detect_communication_style(message: str, context: dict) -> str:
    """Определяет стиль общения по сообщению и контексту"""
    lower_message = message.lower()
    
    for style, triggers in STYLE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return style
    
    # Если в истории много вопросов - используем curious стиль
    if context['asked_questions'] > 2:
        return 'curious'
    
    return 'neutral'

@lru_cache(maxsize=100)
def generate_prompt_template(style: str = 'neutral', context: dict = None) -> str:
    """Генерирует промпт для выбранного стиля с учетом контекста"""
    base_prompt = COMMUNICATION_STYLES[style]['prompt']
    
    if context and context['conversation_history']:
        # Добавляем контекст предыдущих сообщений
        history_summary = "Предыдущий диалог: " + "; ".join(
            f"пользователь: {msg['user']}, ты: {msg['bot']}" 
            for msg in context['conversation_history'][-3:]
        )
        return f"{base_prompt}\n\n{history_summary}"
    
    return base_prompt

async def call_yandex_gpt_optimized(user_message: str, style: str = 'neutral', context: dict = None) -> str:
    """Оптимизированный вызов API с учетом стиля и контекста"""
    
    cache_key = f"{user_message[:50]}_{style}_{hash(str(context)) if context else ''}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt_template = generate_prompt_template(style, context)
    temperature = COMMUNICATION_STYLES[style]['temperature']
    
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
                "text": prompt_template
            },
            {
                "role": "user",
                "text": user_message[:500]
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
        
        # Кэшируем ответ
        request_cache[cache_key] = {
            'response': ai_response,
            'timestamp': time.time()
        }
        
        # Автоочистка кэша
        if len(request_cache) > 500:
            for key in list(request_cache.keys())[:100]:
                del request_cache[key]
        
        return ai_response
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return "Извини, я немного запуталась... Можешь повторить?"

def should_process_message(user_message: str) -> bool:
    """Фильтр сообщений"""
    message = user_message.strip()
    return len(message) > 1 and not message.startswith('/')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик сообщений"""
    if not should_process_message(update.message.text):
        return
    
    user = update.message.from_user
    user_id = user.id
    user_message = update.message.text
    
    # Получаем контекст пользователя
    user_context = get_user_context(user_id)
    
    # Извлекаем и преобразуем имя
    base_name = extract_name_from_user(user)
    transformed_name = transform_name(base_name)
    
    # Определяем стиль общения
    style = detect_communication_style(user_message, user_context)
    
    # Извлекаем темы и интересы
    topics = extract_topics_from_message(user_message)
    user_context['topics_discussed'].update(topics)
    user_context['user_interests'].update(topics)
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Получаем ответ от AI
        ai_response = await call_yandex_gpt_optimized(user_message, style, user_context)
        
        # Добавляем вопрос для поддержания диалога
        if should_ask_question(user_context):
            question = generate_conversation_starter(user_context)
            ai_response += f"\n\n{question}"
            user_context['asked_questions'] += 1
            user_context['last_question_time'] = time.time()
        
        # Добавляем имя в ответ
        final_response = f"{transformed_name}, {ai_response}"
        
        # Обновляем историю диалога
        update_conversation_history(user_id, user_message, final_response)
        
        await update.message.reply_text(final_response)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await update.message.reply_text("Ой, что-то пошло не так... Я Юля, кстати! 😊")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    help_text = f"""
👋 Привет! Я {BOT_PROFILE['name']}, {BOT_PROFILE['age']}-летняя {BOT_PROFILE['gender']}.

✨ Обо мне:
• Работаю: {BOT_PROFILE['job']}
• Увлекаюсь: {BOT_PROFILE['hobbies']}
• Характер: {BOT_PROFILE['personality']}

💬 Со мной можно:
• Общаться на разные темы
• Обсуждать работу, хобби, жизнь
• Спросить совета или просто поболтать

Я люблю задавать вопросы и узнавать людей лучше! 💕
"""
    await update.message.reply_text(help_text)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда начала диалога"""
    user = update.message.from_user
    welcome_text = f"""
Привет, {extract_name_from_user(user)}! 👋

Я {BOT_PROFILE['name']}, {BOT_PROFILE['age']}-летняя {BOT_PROFILE['gender']}. 
Работаю {BOT_PROFILE['job']} и увлекаюсь {BOT_PROFILE['hobbies'].split(', ')[0]}.

Расскажи немного о себе! Чем занимаешься? Что нравится? 😊
"""
    await update.message.reply_text(welcome_text)

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Обработчики сообщений
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        # Команды
        application.add_handler(MessageHandler(
            filters.Regex(r'^/help$'),
            help_command
        ))
        
        application.add_handler(MessageHandler(
            filters.Regex(r'^/start$'),
            start_command
        ))
        
        print(f"🤖 {BOT_PROFILE['name']} запущена!")
        print(f"📍 Возраст: {BOT_PROFILE['age']} лет")
        print(f"📍 Профессия: {BOT_PROFILE['job']}")
        print(f"📍 Характер: {BOT_PROFILE['personality']}")
        print("📍 Режим: естественные диалоги с вопросами")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()
