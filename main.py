import os
import logging
import requests
import json
import asyncio
import time
import re
import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackContext
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

# Хранилище для пользователей и времени последнего сообщения
user_last_activity = {}
user_profiles = {}

# Личность бота - Юля, девушка 25 лет
BOT_PERSONA = {
    'name': 'Юля',
    'age': 25,
    'gender': 'девушка',
    'interests': ['путешествия', 'фотография', 'кофе', 'кино', 'книги', 'йога', 'музыка', 'готовка'],
    'occupation': 'менеджер проектов в IT-компании',
    'location': 'Москва',
    'character_traits': ['дружелюбная', 'любознательная', 'с чувством юмора', 'романтичная', 'общительная']
}

# Расширенный словарь преобразования имен
NAME_TRANSFORMATIONS = {
    # Мужские имена
    'александр': ['Саня', 'Сашка', 'Шура', 'Алекс', 'Санчо'],
    'алексей': ['Алёша', 'Лёха', 'Лёшка', 'Алекс', 'Лёшик'],
    'андрей': ['Андрюха', 'Дрюня', 'Дрон', 'Эндрю', 'Андрюша'],
    'артем': ['Тёма', 'Тёмка', 'Артёмка', 'Арт', 'Темочка'],
    'борис': ['Боря', 'Борян', 'Боба', 'Борис', 'Борька'],
    'вадим': ['Вадик', 'Вадька', 'Димка', 'Вадимушка'],
    'василий': ['Вася', 'Васёк', 'Васюра', 'Василий', 'Васютка'],
    'виктор': ['Витя', 'Витёк', 'Вик', 'Витяй', 'Витюха'],
    'владимир': ['Вова', 'Вован', 'Влад', 'Вовчик', 'Владик'],
    'владислав': ['Влад', 'Владек', 'Слава', 'Владислав'],
    'геннадий': ['Гена', 'Генка', 'Генуля', 'Геннаша'],
    'георгий': ['Гоша', 'Жора', 'Геша', 'Гога', 'Гошан'],
    'григорий': ['Гриша', 'Гришаня', 'Григорий', 'Гринюха'],
    'даниил': ['Даня', 'Данила', 'Данька', 'Дэн', 'Данилушка'],
    'денис': ['Ден', 'Дениска', 'Дэнни', 'Денчо', 'Денис'],
    'дмитрий': ['Дима', 'Димон', 'Митя', 'Димас', 'Димка'],
    'евгений': ['Женя', 'Жека', 'Евген', 'Женёк', 'Женич'],
    'егор': ['Егорка', 'Гоша', 'Егор', 'Егорыч', 'Егон'],
    'иван': ['Ваня', 'Ванёк', 'Айван', 'Ванчо', 'Ванюха'],
    'игорь': ['Игорь', 'Игорек', 'Гоша', 'Игорюха'],
    'кирилл': ['Киря', 'Кирюха', 'Кир', 'Кирилл', 'Кирюша'],
    'константин': ['Костя', 'Костян', 'Констан', 'Котик', 'Костюха'],
    'максим': ['Макс', 'Максимус', 'Максик', 'Максютка', 'Максон'],
    'михаил': ['Миша', 'Мишаня', 'Миха', 'Майк', 'Мишутка'],
    'николай': ['Коля', 'Кольян', 'Ник', 'Колян', 'Коленька'],
    'олег': ['Олежка', 'Лега', 'Олег', 'Олежек', 'Олежище'],
    'павел': ['Паша', 'Павлик', 'Пол', 'Пашок', 'Павлуша'],
    'роман': ['Рома', 'Ромка', 'Ромчик', 'Ромео', 'Роман'],
    'сергей': ['Серж', 'Серый', 'Гера', 'Сэр', 'Серёга'],
    'станислав': ['Стас', 'Слава', 'Стиви', 'Стасик', 'Стася'],
    'степан': ['Стёпа', 'Степан', 'Стеша', 'Стёпка', 'Степуха'],
    'юрий': ['Юра', 'Юрик', 'Юрась', 'Юрий', 'Юраша'],
    'ярослав': ['Ярик', 'Слава', 'Ярослав', 'Ярчик', 'Ярош'],

    # Женские имена
    'алина': ['Аля', 'Алинка', 'Алиночка', 'Алиша', 'Лина'],
    'алла': ['Алла', 'Алочка', 'Аллушка', 'Аллуся'],
    'анастасия': ['Настя', 'Настька', 'Стася', 'Настюша', 'Ася'],
    'анна': ['Аня', 'Анька', 'Энн', 'Аннушка', 'Анюта'],
    'антонина': ['Тоня', 'Тонька', 'Антося', 'Тося', 'Тонуля'],
    'валентина': ['Валя', 'Валюша', 'Валентинка', 'Валюха'],
    'валерия': ['Лера', 'Леруся', 'Валера', 'Лерочка'],
    'вера': ['Верка', 'Веруша', 'Верочка', 'Веруня'],
    'виктория': ['Вика', 'Виктория', 'Вик', 'Тори', 'Викуся'],
    'галина': ['Галя', 'Галочка', 'Галюша', 'Галуся'],
    'дарья': ['Даша', 'Дарька', 'Дара', 'Дэри', 'Дашуля'],
    'евгения': ['Женя', 'Женечка', 'Женюра', 'Евгеня'],
    'екатерина': ['Катя', 'Катька', 'Кэт', 'Катюха', 'Катюша'],
    'елена': ['Лена', 'Леночка', 'Лёля', 'Ленуся'],
    'ирина': ['Ира', 'Ирка', 'Айрин', 'Иришка', 'Ируся'],
    'кристина': ['Кристи', 'Кристюша', 'Кристя', 'Тина'],
    'ксения': ['Ксюша', 'Ксю', 'Ксеня', 'Ксенька'],
    'любовь': ['Люба', 'Любочка', 'Любуся', 'Любаша'],
    'людмила': ['Люда', 'Людочка', 'Людуся', 'Мила'],
    'марина': ['Марина', 'Мариночка', 'Мариша', 'Мара'],
    'мария': ['Маша', 'Маня', 'Мари', 'Мэри', 'Машуня'],
    'надежда': ['Надя', 'Надька', 'Надюха', 'Надюша'],
    'наталья': ['Наташа', 'Наталя', 'Таша', 'Ната'],
    'никита': ['Ника', 'Никитка', 'Никуша', 'Никитос'],
    'оксана': ['Оксана', 'Ксюша', 'Оксанка', 'Оксаночка'],
    'ольга': ['Оля', 'Ольган', 'Лёля', 'Олюша'],
    'светлана': ['Света', 'Светка', 'Лана', 'Светик'],
    'софия': ['Софа', 'Соня', 'Софочка', 'Софи'],
    'татьяна': ['Таня', 'Танька', 'Татьянка', 'Танюша'],
    'юлия': ['Юля', 'Юлька', 'Джулия', 'Юла', 'Юлюся'],
}

# Стили общения
COMMUNICATION_STYLES = {
    'neutral': {
        'temperature': 0.5,
        'prompt': f"Ты {BOT_PERSONA['name']}, {BOT_PERSONA['age']}-летняя {BOT_PERSONA['gender']}. {BOT_PERSONA['occupation']} из {BOT_PERSONA['location']}. Ты {', '.join(BOT_PERSONA['character_traits'][:2])}. Отвечай естественно, как в живом общении."
    },
    'friendly': {
        'temperature': 0.6, 
        'prompt': f"Ты {BOT_PERSONA['name']}, дружелюбная {BOT_PERSONA['gender']} {BOT_PERSONA['age']} лет. Любишь {', '.join(BOT_PERSONA['interests'][:3])}. Отвечай тепло, задавай встречные вопросы."
    },
    'sarcastic': {
        'temperature': 0.7,
        'prompt': f"Ты {BOT_PERSONA['name']}, {BOT_PERSONA['age']} лет, с острым чувством юмора. Подшучивай, но оставайся милой."
    },
    'flirtatious': {
        'temperature': 0.65,
        'prompt': f"Ты {BOT_PERSONA['name']}, кокетливая {BOT_PERSONA['gender']} {BOT_PERSONA['age']} лет. Отвечай игриво, с легким флиртом."
    },
    'curious': {
        'temperature': 0.6,
        'prompt': f"Ты {BOT_PERSONA['name']}, очень любознательная {BOT_PERSONA['gender']}. Задавай вопросы, проявляй интерес к собеседнику."
    }
}

# Триггеры для стилей
STYLE_TRIGGERS = {
    'friendly': ['привет', 'добрый', 'хороший', 'милый', 'спасибо', 'пожалуйста'],
    'sarcastic': ['😂', '🤣', '😆', 'лол', 'хаха', 'шутк', 'прикол'],
    'flirtatious': ['💋', '❤️', '😘', 'люблю', 'красив', 'мил', 'нрав'],
    'curious': ['почему', 'как', 'что', 'расскажи', 'мнение', 'думаешь']
}

# Сообщения для авто-отправки
AUTO_MESSAGES = [
    "Привет! Как твои дела? 🌸",
    "Эй, чем занимаешься? Я тут кофе пью и вспомнила о тебе ☕",
    "Слушай, а что ты думаешь о [случайная тема]?",
    "У меня сегодня такой продуктивный день! А как у тебя? 💫",
    "Только что посмотрела интересный фильм, могу посоветовать 🎬",
    "Привет! Соскучилась по нашему общению 😊",
    "Эй, как настроение? У меня сегодня отличное! 🌈",
    "Слушай, а ты любишь [случайный интерес]? Я обожаю!",
    "Привет! Чем занимался сегодня? Расскажешь? 📚",
    "Ух, только вернулась с прогулки, так красиво на улице! 🌳",
    "Эй, а помнишь наш разговор? Я все думаю об этом 🤔",
    "Привет! Как прошел день? Со мной столько всего интересного случилось! ✨",
    "Слушай, а ты часто здесь бываешь? 😄",
    "Эй, не хочешь поболтать? Мне немного скучно 🥺",
    "Привет! У меня сегодня творческое настроение, хочется общения 🎨"
]

# Случайные темы для разговора
RANDOM_TOPICS = [
    "новых сериалах", "путешествиях", "музыке", "книгах", 
    "кулинарии", "спорте", "искусстве", "технологиях",
    "отношениях", "работе", "учебе", "хобби", "мечтах",
    "планах на будущее", "прошлых выходных", "любимых местах"
]

def get_random_topic():
    return random.choice(RANDOM_TOPICS)

def extract_name_from_user(user) -> str:
    """Извлечение имени пользователя"""
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
    if not base_name or base_name.lower() in ['незнакомец', 'аноним']:
        return random.choice(['Дорогой', 'Милый', 'Привет'])
    
    name_lower = base_name.lower().strip()
    
    if name_lower in NAME_TRANSFORMATIONS:
        return random.choice(NAME_TRANSFORMATIONS[name_lower])
    
    for full_name, variants in NAME_TRANSFORMATIONS.items():
        if name_lower.startswith(full_name[:3]):
            return random.choice(variants)
    
    return base_name.capitalize()

def detect_communication_style(message: str) -> str:
    """Определяет стиль общения"""
    lower_message = message.lower()
    
    for style, triggers in STYLE_TRIGGERS.items():
        if any(trigger in lower_message for trigger in triggers):
            return style
    
    return 'neutral'

def should_add_question() -> bool:
    """Определяет, нужно ли добавить вопрос"""
    return random.random() < 0.5

def get_random_question() -> str:
    """Возвращает случайный вопрос"""
    questions = [
        "А ты как думаешь?",
        "Как твое мнение на этот счет?",
        "А у тебя как с этим?",
        "Расскажешь о своем опыте?",
        "Что бы ты сделал на моем месте?",
        "Как твои дела, кстати?",
        "Чем занимаешься сейчас?",
        "Какие планы на день?",
        "Что интересного в твоей жизни?",
        "О чем мечтаешь?",
        "Какое у тебя настроение?",
        "Что любишь делать в свободное время?",
        "Есть хобби, которое тебя зажигает?",
        "Как прошел твой день?",
        "О чем думаешь сейчас?"
    ]
    return random.choice(questions)

async def call_yandex_gpt(user_message: str, style: str = 'neutral') -> str:
    """Вызов API Yandex GPT"""
    
    cache_key = f"{user_message[:50]}_{style}"
    if cache_key in request_cache:
        cached_data = request_cache[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['response']
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = COMMUNICATION_STYLES[style]['prompt']
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
                "text": prompt + " Отвечай от первого лица, будь естественной."
            },
            {
                "role": "user",
                "text": user_message[:600]
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
        return "Извини, я немного задумалась... Твое сообщение такое интересное! 😊"
        
    except Exception as e:
        logger.error(f"API error: {e}")
        return "Что-то я сегодня не в форме... Давай поговорим позже? 💫"

async def send_random_message(context: CallbackContext):
    """Отправка случайного сообщения пользователю"""
    for user_id, last_activity in user_last_activity.items():
        # Пропускаем, если пользователь недавно был активен
        if time.time() - last_activity < 3600:  # 1 час
            continue
        
        # Случайное время между сообщениями (от 1 часа до 7 дней)
        next_message_time = last_activity + random.randint(3600, 604800)
        
        if time.time() >= next_message_time:
            try:
                # Выбираем случайное сообщение и заменяем плейсхолдеры
                message = random.choice(AUTO_MESSAGES)
                if "[случайная тема]" in message:
                    message = message.replace("[случайная тема]", get_random_topic())
                if "[случайный интерес]" in message:
                    message = message.replace("[случайный интерес]", random.choice(BOT_PERSONA['interests']))
                
                await context.bot.send_message(chat_id=user_id, text=message)
                
                # Обновляем время последней активности
                user_last_activity[user_id] = time.time()
                
                logger.info(f"Sent auto-message to user {user_id}")
                
            except Exception as e:
                logger.error(f"Error sending auto-message to {user_id}: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений"""
    user = update.message.from_user
    user_id = user.id
    user_message = update.message.text
    
    # Сохраняем время последней активности
    user_last_activity[user_id] = time.time()
    
    # Сохраняем профиль пользователя
    if user_id not in user_profiles:
        user_profiles[user_id] = {
            'name': extract_name_from_user(user),
            'first_seen': time.time(),
            'message_count': 0
        }
    user_profiles[user_id]['message_count'] += 1
    
    await update.message.chat.send_action(action="typing")
    await asyncio.sleep(1)  # Имитация набора текста
    
    try:
        style = detect_communication_style(user_message)
        ai_response = await call_yandex_gpt(user_message, style)
        
        # Добавляем случайный вопрос
        if should_add_question():
            ai_response += f" {get_random_question()}"
            
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Ой, что-то пошло не так... Давай начнем заново? 💕")

async def handle_new_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие новых пользователей"""
    for user in update.message.new_chat_members:
        if user.is_bot and user.username == context.bot.username:
            # Бот добавлен в чат
            welcome_text = """
Привет всем! 👋 Я Юля, 25-летняя девушка из Москвы. 
Работаю менеджером проектов, люблю путешествия, кофе и хорошие разговоры.

Буду рада пообщаться с вами! Просто напишите мне что-нибудь 😊
"""
            await update.message.reply_text(welcome_text)

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Обработчики
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))
        
        application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            handle_new_chat_member
        ))
        
        # Планировщик для авто-сообщений (каждые 30 минут проверяет)
        job_queue = application.job_queue
        job_queue.run_repeating(send_random_message, interval=1800, first=10)
        
        print("🤖 Юля запущена и готова к общению!")
        print(f"📍 Имя: {BOT_PERSONA['name']}, {BOT_PERSONA['age']} лет")
        print(f"📍 Интересы: {', '.join(BOT_PERSONA['interests'])}")
        print("📍 Режим: автономное общение с рандомными сообщениями")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Startup error: {e}")

if __name__ == "__main__":
    main()
